// 端到端收包回归测试：真实 TcpServer -> TcpClient 全链路（覆盖 receiveLoop + decodeFrame）。
// 回归保护: 若 receiveLoop 把 4 字节长度头抽走再喂 decodeFrame，客户端永远收不到帧，此测试会挂。
#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <thread>

#include "core/ipc_client.h"
#include "core/ipc_server.h"
#include "core/ipc_message.h"

using namespace maai::ipc;

int main() {
  constexpr uint16_t kPort = 28991;
  TcpServer server("127.0.0.1", kPort);
  if (!server.start()) { std::cerr << "server start failed\n"; return 1; }

  TcpClient client("127.0.0.1", kPort);
  std::atomic<bool> got{false};
  nlohmann::json received;
  client.setMessageHandler([&](const nlohmann::json& msg) { received = msg; got.store(true); });

  if (!client.connect(5000)) { std::cerr << "client connect failed\n"; return 1; }
  // 等服务端 accept 该客户端
  for (int i = 0; i < 50 && server.clientCount() == 0; ++i)
    std::this_thread::sleep_for(std::chrono::milliseconds(20));

  nlohmann::json ev = {{"v", 1}, {"type", "event"}, {"event", "TASK_FINISHED"}, {"params", {{"ok", true}}}};
  server.broadcast(ev);

  for (int i = 0; i < 100 && !got.load(); ++i)
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  assert(got.load() && "client never received a frame (receiveLoop/decodeFrame regression)");
  assert(received["event"] == "TASK_FINISHED");

  client.disconnect();
  server.stop();
  std::cout << "test_tcp_roundtrip: end-to-end frame receive OK\n";
  return 0;
}