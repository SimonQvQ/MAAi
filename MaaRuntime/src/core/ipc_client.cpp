#include "ipc_client.h"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>

#include "ipc_message.h"

namespace maai::ipc {

TcpClient::TcpClient(std::string host, uint16_t port) : host_(std::move(host)), port_(port) {}

TcpClient::~TcpClient() { disconnect(); }

void TcpClient::setMessageHandler(MessageHandler handler) { onMessage_ = std::move(handler); }
void TcpClient::setStateHandler(StateHandler handler) { onState_ = std::move(handler); }

bool TcpClient::connect(int timeoutMs) {
  if (connected_.load()) return true;
  if (stopped_.load()) stopped_.store(false);

  struct addrinfo hints {};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  struct addrinfo* res = nullptr;
  const std::string portStr = std::to_string(port_);
  int rc = ::getaddrinfo(host_.c_str(), portStr.c_str(), &hints, &res);
  if (rc != 0 || !res) return false;

  int fd = -1;
  for (struct addrinfo* ai = res; ai; ai = ai->ai_next) {
    fd = ::socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    if (fd < 0) continue;
    // 非阻塞 + poll 实现超时
    int flags = ::fcntl(fd, F_GETFL, 0);
    ::fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    int c = ::connect(fd, ai->ai_addr, ai->ai_addrlen);
    if (c == 0) break;
    if (errno == EINPROGRESS) {
      struct pollfd pfd { fd, POLLOUT, 0 };
      int pr = ::poll(&pfd, 1, timeoutMs);
      if (pr > 0 && (pfd.revents & POLLOUT)) {
        int err = 0;
        socklen_t elen = sizeof(err);
        ::getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &elen);
        if (err == 0) break;
      }
    }
    ::close(fd);
    fd = -1;
  }
  ::freeaddrinfo(res);
  if (fd < 0) return false;

  int flags = ::fcntl(fd, F_GETFL, 0);
  ::fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);

  fd_ = fd;
  connected_.store(true);
  if (recvThread_.joinable()) recvThread_.join();
  recvThread_ = std::thread([this] { receiveLoop(); });
  if (onState_) onState_(true);
  return true;
}

void TcpClient::disconnect() {
  stopped_.store(true);
  if (fd_ >= 0) { ::shutdown(fd_, SHUT_RDWR); ::close(fd_); fd_ = -1; }
  if (connected_.exchange(false) && onState_) onState_(false);
  if (recvThread_.joinable()) recvThread_.join();
  stopped_.store(false);
}

bool TcpClient::readExact(int fd, uint8_t* buf, size_t n) {
  size_t got = 0;
  while (got < n) {
    ssize_t r = ::recv(fd, buf + got, n - got, 0);
    if (r > 0) { got += static_cast<size_t>(r); continue; }
    if (r < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    return false;
  }
  return true;
}

void TcpClient::receiveLoop() {
  std::vector<uint8_t> pending;
  while (!stopped_.load() && fd_ >= 0) {
    uint8_t hdr[4];
    if (!readExact(fd_, hdr, 4)) break;
    uint32_t len = (static_cast<uint32_t>(hdr[0]) << 24) | (static_cast<uint32_t>(hdr[1]) << 16) |
                   (static_cast<uint32_t>(hdr[2]) << 8) | static_cast<uint32_t>(hdr[3]);
    if (len == 0 || len > 16 * 1024 * 1024) break;
    std::vector<uint8_t> frame(len);
    if (!readExact(fd_, frame.data(), len)) break;
    // decodeFrame 要求数据以 4 字节大端长度头开头，必须把头一并保留
    pending.insert(pending.end(), hdr, hdr + 4);
    pending.insert(pending.end(), frame.begin(), frame.end());
    size_t consumed = 0;
    nlohmann::json out;
    while (decodeFrame(pending.data(), pending.size(), consumed, out)) {
      if (onMessage_) onMessage_(out);
      if (consumed >= pending.size()) { pending.clear(); break; }
      std::vector<uint8_t> rest(pending.begin() + static_cast<long>(consumed), pending.end());
      pending = std::move(rest);
      consumed = 0;
    }
  }
  // 连接断开
  if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
  if (connected_.exchange(false) && onState_) onState_(false);
}

bool TcpClient::send(const nlohmann::json& msg) {
  if (!connected_.load() || fd_ < 0) return false;
  std::vector<uint8_t> frame = encodeFrame(msg);
  size_t sent = 0;
  while (sent < frame.size()) {
    ssize_t r = ::send(fd_, frame.data() + sent, frame.size() - sent, MSG_NOSIGNAL);
    if (r > 0) { sent += static_cast<size_t>(r); continue; }
    if (r < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
    return false;
  }
  return true;
}

}  // namespace maai::ipc
