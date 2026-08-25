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
  // 服务端运行中对端断开（不先 stop server），触发 clientLoop 断连路径 -> closeClient(fd)
  constexpr uint16_t kPort = 28992;
  TcpServer server("127.0.0.1", kPort);
  if (!server.start()) { std::cerr << "server start failed\n"; return 1; }

  for (int round = 0; round < 3; ++round) {
    {
      TcpClient client("127.0.0.1", kPort);
      if (!client.connect(5000)) { std::cerr << "client connect failed\n"; return 1; }
    } // 析构 -> disconnect -> 对端(服务端) recv 返回 0 -> clientLoop self-cleanup
    // 等服务端清理该客户端
    for (int i = 0; i < 200 && server.clientCount() != 0; ++i)
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    if (server.clientCount() != 0) { std::cerr << "server did not drop client\n"; return 1; }
  }
  server.stop();
  std::cout << "disconnect-cleanup: OK (no crash)\n";
  return 0;
}
