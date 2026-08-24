#include "core/ipc_server.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <exception>
#include <string>
#include <utility>
#include <vector>

#include "core/ipc_message.h"
#include "core/log.h"

namespace maai::ipc {

namespace {
constexpr size_t kMaxClientCount = 8;

// 循环发送一整个帧；对端关闭/出错返回 false。
bool sendAll(int fd, const std::vector<uint8_t>& data) {
  size_t sent = 0;
  while (sent < data.size()) {
    ssize_t w = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
    if (w < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    if (w <= 0) return false;
    sent += static_cast<size_t>(w);
  }
  return true;
}
}

TcpServer::TcpServer(std::string host, uint16_t port)
    : host_(std::move(host)), port_(port) {}

TcpServer::~TcpServer() { stop(); }

bool TcpServer::start(ErrorHandler onError) {
  if (running_.load()) return true;
  errorHandler_ = std::move(onError);

  listenFd_ = ::socket(AF_INET, SOCK_STREAM, 0);
  if (listenFd_ < 0) {
    Log::error("socket() failed: " + std::string(std::strerror(errno)));
    return false;
  }

  int one = 1;
  ::setsockopt(listenFd_, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(port_);
  if (::inet_pton(AF_INET, host_.c_str(), &addr.sin_addr) != 1) {
    Log::warn("invalid ipc host '" + host_ + "', fallback to 127.0.0.1");
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  }

  if (::bind(listenFd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
    Log::error("bind " + host_ + ":" + std::to_string(port_) + " failed: " + std::strerror(errno));
    ::close(listenFd_);
    listenFd_ = -1;
    return false;
  }
  if (::listen(listenFd_, 8) < 0) {
    Log::error("listen failed: " + std::string(std::strerror(errno)));
    ::close(listenFd_);
    listenFd_ = -1;
    return false;
  }

  running_.store(true);
  stopped_.store(false);
  acceptThread_ = std::thread([this] { acceptLoop(); });
  Log::info("IPC server listening on " + host_ + ":" + std::to_string(port_));
  return true;
}

void TcpServer::stop() {
  if (stopped_.exchange(true)) return;
  running_.store(false);

  if (listenFd_ >= 0) {
    ::shutdown(listenFd_, SHUT_RDWR);
    ::close(listenFd_);
    listenFd_ = -1;
  }
  if (acceptThread_.joinable()) acceptThread_.join();

  std::vector<int> fds;
  {
    std::lock_guard<std::mutex> lock(clientsMutex_);
    for (auto& [fd, t] : clients_) fds.push_back(fd);
  }
  for (int fd : fds) {
    ::shutdown(fd, SHUT_RDWR);
    ::close(fd);
  }
  std::vector<std::thread> threads;
  {
    std::lock_guard<std::mutex> lock(clientsMutex_);
    for (auto& [fd, t] : clients_) threads.push_back(std::move(t));
    clients_.clear();
  }
  for (auto& t : threads)
    if (t.joinable()) t.join();
}

void TcpServer::setMessageHandler(MessageHandler handler) { handler_ = std::move(handler); }

size_t TcpServer::clientCount() const {
  std::lock_guard<std::mutex> lock(clientsMutex_);
  return clients_.size();
}

void TcpServer::acceptLoop() {
  while (!stopped_.load()) {
    sockaddr_in peer{};
    socklen_t len = sizeof(peer);
    int fd = ::accept(listenFd_, reinterpret_cast<sockaddr*>(&peer), &len);
    if (fd < 0) {
      if (stopped_.load()) break;
      Log::debug("accept failed: " + std::string(std::strerror(errno)));
      continue;
    }

    std::lock_guard<std::mutex> lock(clientsMutex_);
    if (clients_.size() >= kMaxClientCount) {
      ::close(fd);
      continue;
    }
    char buf[INET_ADDRSTRLEN] = {};
    ::inet_ntop(AF_INET, &peer.sin_addr, buf, sizeof(buf));
    std::string peerName = std::string(buf) + ":" + std::to_string(ntohs(peer.sin_port));
    clients_[fd] = std::thread([this, fd, peerName] { clientLoop(fd, peerName); });
  }
}

void TcpServer::closeClient(int fd) {
  std::thread t;
  {
    std::lock_guard<std::mutex> lock(clientsMutex_);
    auto it = clients_.find(fd);
    if (it == clients_.end()) return;
    t = std::move(it->second);
    clients_.erase(it);
  }
  ::shutdown(fd, SHUT_RDWR);
  ::close(fd);
  // closeClient 只会由 clientLoop 在自己的线程里调用，join 自己会抛
  // system_error(resource_deadlock_would_occur) 进而导致进程终止，必须 detach。
  if (t.joinable()) t.detach();
}

void TcpServer::clientLoop(int fd, const std::string& peer) {
  Log::info("client connected: " + peer);

  // 帧可跨多次 recv 到达（上限 16MB，远超单次 64KB 读缓冲），
  // 半帧留在 buf 里等后续数据，不能丢弃，否则流永久失步。
  std::vector<uint8_t> buf;
  std::vector<uint8_t> tmp(65536);
  while (!stopped_.load()) {
    ssize_t n = ::recv(fd, tmp.data(), tmp.size(), 0);
    if (n <= 0) break;
    buf.insert(buf.end(), tmp.data(), tmp.data() + n);

    size_t consumed = 0;
    nlohmann::json frame;
    while (decodeFrame(buf.data(), buf.size(), consumed, frame)) {
      buf.erase(buf.begin(), buf.begin() + static_cast<long>(consumed));

      if (!handler_) continue;
      try {
        sendAll(fd, encodeFrame(handler_(frame)));
      } catch (const std::exception& e) {
        sendAll(fd, encodeFrame(toJson(Message::errorResponse("", e.what()))));
      }
    }
    // decodeFrame 返回 false = 帧不完整或超长。不完整等下一次 recv；
    // 超长/损坏流则 buf 无界增长，超过上限直接断开。
    if (buf.size() > kMaxFrameBytes + 4) {
      Log::warn("oversized/corrupt stream from " + peer + ", dropping connection");
      break;
    }
  }

  Log::info("client disconnected: " + peer);
  closeClient(fd);
}

void TcpServer::broadcast(const nlohmann::json& payload) {
  if (clientCount() == 0) return;
  auto frame = encodeFrame(payload);
  std::vector<int> fds;
  {
    std::lock_guard<std::mutex> lock(clientsMutex_);
    for (auto& [fd, t] : clients_) fds.push_back(fd);
  }
  for (int fd : fds) {
    ::send(fd, frame.data(), frame.size(), MSG_NOSIGNAL);
  }
}

}  // namespace maai::ipc
