#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <thread>

#include <nlohmann/json.hpp>

namespace maai::ipc {

// 极简 localhost TCP server: 4 字节大端长度 + JSON 帧。
// 支持多客户端，收到 request 调用 handler，broadcast 向所有客户端推送事件。
class TcpServer {
 public:
  using MessageHandler = std::function<nlohmann::json(const nlohmann::json& request)>;
  using ErrorHandler = std::function<void(const std::string& message)>;

  explicit TcpServer(std::string host, uint16_t port);
  ~TcpServer();

  TcpServer(const TcpServer&) = delete;
  TcpServer& operator=(const TcpServer&) = delete;

  bool start(ErrorHandler onError = {});
  void stop();
  bool running() const { return running_.load(); }
  uint16_t port() const { return port_; }

  void setMessageHandler(MessageHandler handler);
  void broadcast(const nlohmann::json& payload);

  size_t clientCount() const;

 private:
  void acceptLoop();
  void clientLoop(int fd, const std::string& peer);
  void closeClient(int fd);

  std::string host_;
  uint16_t port_;
  std::atomic<bool> running_{false};
  std::atomic<bool> stopped_{false};
  int listenFd_ = -1;
  std::thread acceptThread_;
  MessageHandler handler_;
  ErrorHandler errorHandler_;

  mutable std::mutex clientsMutex_;
  std::map<int, std::thread> clients_;
};

}  // namespace maai::ipc
