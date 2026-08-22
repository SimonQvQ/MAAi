#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <string>
#include <thread>
#include <vector>

#include <nlohmann/json.hpp>

namespace maai::ipc {

// 极简 TCP client: 4 字节大端长度 + JSON 帧（与 TcpServer 同一线格式）。
// 用于 iPhone 端 MAAiAgent 作为主动方拨号连接 Docker 里的 maai-server。
// 收到完整帧回调 onMessage（在接收线程里）；连接状态变化回调 onState。
class TcpClient {
 public:
  using MessageHandler = std::function<void(const nlohmann::json& msg)>;
  using StateHandler = std::function<void(bool connected)>;

  TcpClient(std::string host, uint16_t port);
  ~TcpClient();

  TcpClient(const TcpClient&) = delete;
  TcpClient& operator=(const TcpClient&) = delete;

  // 阻塞连接，超时返回 false（可重试）。
  bool connect(int timeoutMs = 5000);
  void disconnect();
  bool send(const nlohmann::json& msg);
  bool connected() const { return connected_.load(); }

  void setMessageHandler(MessageHandler handler);
  void setStateHandler(StateHandler handler);

 private:
  void receiveLoop();
  static bool readExact(int fd, uint8_t* buf, size_t n);

  std::string host_;
  uint16_t port_;
  std::atomic<bool> connected_{false};
  std::atomic<bool> stopped_{false};
  int fd_ = -1;
  std::thread recvThread_;
  MessageHandler onMessage_;
  StateHandler onState_;
};

}  // namespace maai::ipc
