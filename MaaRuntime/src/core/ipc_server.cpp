#include "core/ipc_server.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstring>
#include <exception>
#include <string>
#include <utility>

#include "core/ipc_message.h"
#include "core/log.h"

namespace maai::ipc {

namespace {
constexpr size_t kMaxClientCount = 8;
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
  if (t.joinable()) t.join();
}

void TcpServer::clientLoop(int fd, const std::string& peer) {
  Log::info("client connected: " + peer);

  std::vector<uint8_t> readBuf(65536);
  while (!stopped_.load()) {
    ssize_t n = ::recv(fd, readBuf.data(), readBuf.size(), 0);
    if (n <= 0) break;

    size_t offset = 0;
    while (offset < static_cast<size_t>(n)) {
      size_t consumed = 0;
      nlohmann::json frame;
      if (!decodeFrame(readBuf.data() + offset, static_cast<size_t>(n) - offset, consumed, frame)) {
        Log::warn("incomplete frame from " + peer + ", waiting for more data");
        break;
      }
      offset += consumed;

      if (!handler_) continue;
      try {
        nlohmann::json response = handler_(frame);
        auto out = encodeFrame(response);
        size_t sent = 0;
        while (sent < out.size()) {
          ssize_t w = ::send(fd, out.data() + sent, out.size() - sent, MSG_NOSIGNAL);
          if (w <= 0) break;
          sent += static_cast<size_t>(w);
        }
      } catch (const std::exception& e) {
        nlohmann::json err = toJson(Message::errorResponse("", e.what()));
        auto out = encodeFrame(err);
        ::send(fd, out.data(), out.size(), MSG_NOSIGNAL);
      }
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
