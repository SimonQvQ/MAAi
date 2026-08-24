// TCP 分帧回归测试：覆盖历史上出现过的三类真实 bug。
//   1) 跨多次 send 的大帧（>64KB 读缓冲）服务端必须能重组，不能丢帧；
//   2) 坏 JSON 帧（长度前缀合法、内容非法）必须被跳过且流不失步——服务端与客户端两侧；
//   3) 声明超长的帧头必须立即断开连接；
//   4) 客户端断开（服务端主动丢弃 + 正常关闭两条路径）后服务端必须存活并回收会话
//      （closeClient 曾 join 自己导致 terminate）。
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string>
#include <thread>

#include "core/ipc_client.h"
#include "core/ipc_server.h"
#include "core/ipc_message.h"

using namespace maai::ipc;

namespace {

bool sendRaw(int fd, const uint8_t* data, size_t n) {
  size_t sent = 0;
  while (sent < n) {
    ssize_t w = ::send(fd, data + sent, n - sent, MSG_NOSIGNAL);
    if (w <= 0) return false;
    sent += static_cast<size_t>(w);
  }
  return true;
}

void waitMs(int ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }

// 等待 cond 为 true，最多 timeoutMs 毫秒。
template <typename F>
bool waitFor(F cond, int timeoutMs) {
  for (int i = 0; i < timeoutMs / 10; ++i) {
    if (cond()) return true;
    waitMs(10);
  }
  return cond();
}

// 直连 TcpServer 的裸 TCP 客户端（不走 TcpClient，方便注入原始字节）。
int rawConnect(uint16_t port) {
  int fd = ::socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(port);
  ::inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
  if (::connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
    ::close(fd);
    return -1;
  }
  return fd;
}

void appendFrame(std::vector<uint8_t>& out, const std::string& body) {
  uint32_t len = static_cast<uint32_t>(body.size());
  out.push_back(static_cast<uint8_t>(len >> 24));
  out.push_back(static_cast<uint8_t>(len >> 16));
  out.push_back(static_cast<uint8_t>(len >> 8));
  out.push_back(static_cast<uint8_t>(len));
  out.insert(out.end(), body.begin(), body.end());
}

}  // namespace

int main() {
  constexpr uint16_t kPort = 28995;

  // ---------- 场景 1: 跨 send 边界的大帧 ----------
  TcpServer server("127.0.0.1", kPort);
  std::atomic<int> bigFrameResult{0};  // 1=匹配 0=未到 -1=损坏
  std::atomic<int> afterBadCount{0};
  const std::string bigPayload(300000, 'x');  // 300KB，远超 64KB 读缓冲

  server.setMessageHandler([&](const nlohmann::json& req) {
    std::string cmd = req.value("cmd", "");
    if (cmd == "BIG") {
      std::string data = req.value("params", nlohmann::json::object()).value("data", "");
      bigFrameResult.store(data == bigPayload ? 1 : -1);
    } else if (cmd == "AFTER_BAD") {
      afterBadCount.fetch_add(1);
    }
    return nlohmann::json{{"v", 1}, {"type", "response"}, {"ok", true}};
  });
  if (!server.start()) { std::cerr << "server start failed\n"; return 1; }

  int fd = rawConnect(kPort);
  assert(fd >= 0);
  assert(waitFor([&] { return server.clientCount() == 1; }, 2000));

  std::vector<uint8_t> frame = encodeFrame(
      nlohmann::json{{"v", 1}, {"type", "request"}, {"req_id", "r1"},
                     {"cmd", "BIG"}, {"params", {{"data", bigPayload}}}});
  // 故意按 4096 字节一片发送，保证帧被拆到多次 recv
  for (size_t i = 0; i < frame.size(); i += 4096)
    assert(sendRaw(fd, frame.data() + i, std::min<size_t>(4096, frame.size() - i)));
  assert(waitFor([&] { return bigFrameResult.load() != 0; }, 5000));
  assert(bigFrameResult.load() == 1 && "server lost/damaged a frame split across recv() calls");
  std::cout << "[1] server reassembles 300KB frame split into 4096B chunks: OK\n";

  // ---------- 场景 2a: 服务端跳过坏 JSON 帧 ----------
  std::vector<uint8_t> bad;
  appendFrame(bad, "not json at all");  // 长度合法、内容非法
  assert(sendRaw(fd, bad.data(), bad.size()));
  frame = encodeFrame(nlohmann::json{{"v", 1}, {"type", "request"},
                                     {"req_id", "r2"}, {"cmd", "AFTER_BAD"}});
  assert(sendRaw(fd, frame.data(), frame.size()));
  assert(waitFor([&] { return afterBadCount.load() > 0; }, 5000) &&
         "server stalled after a malformed JSON frame");
  std::cout << "[2] server skips malformed frame, stream stays in sync: OK\n";

  // ---------- 场景 3: 超长帧头立即断开 ----------
  uint8_t evil[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0};
  assert(sendRaw(fd, evil, sizeof(evil)));
  assert(waitFor([&] { return server.clientCount() == 0; }, 5000) &&
         "server kept a connection that declared an oversized frame");
  ::close(fd);
  std::cout << "[3] server drops connection on oversized frame length: OK\n";

  // ---------- 场景 2b: TcpClient 跳过坏帧 ----------
  // 用裸 listener 精确控制发给客户端的字节。
  constexpr uint16_t kPort2 = 28996;
  int lfd = ::socket(AF_INET, SOCK_STREAM, 0);
  int one = 1;
  ::setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  sockaddr_in laddr{};
  laddr.sin_family = AF_INET;
  laddr.sin_port = htons(kPort2);
  ::inet_pton(AF_INET, "127.0.0.1", &laddr.sin_addr);
  assert(::bind(lfd, reinterpret_cast<sockaddr*>(&laddr), sizeof(laddr)) == 0);
  assert(::listen(lfd, 1) == 0);

  std::atomic<int> clientReceived{0};
  TcpClient client("127.0.0.1", kPort2);
  client.setMessageHandler([&](const nlohmann::json&) { clientReceived.fetch_add(1); });
  assert(client.connect(5000));

  int cfd = ::accept(lfd, nullptr, nullptr);
  assert(cfd >= 0);
  assert(sendRaw(cfd, bad.data(), bad.size()));  // 先发坏帧
  auto good = encodeFrame(nlohmann::json{{"v", 1}, {"type", "event"},
                                         {"event", "GOOD1"}});
  assert(sendRaw(cfd, good.data(), good.size()));
  good = encodeFrame(nlohmann::json{{"v", 1}, {"type", "event"}, {"event", "GOOD2"}});
  assert(sendRaw(cfd, good.data(), good.size()));
  assert(waitFor([&] { return clientReceived.load() >= 2; }, 5000) &&
         "client stalled after a malformed frame");
  std::cout << "[4] client skips malformed frame, receives following frames: OK\n";

  // ---------- 场景 4: 客户端正常断开（recv 返回 0），服务端存活并回收 ----------
  client.disconnect();
  ::close(cfd);
  ::close(lfd);

  // 场景 3 走的是"服务端主动丢弃"路径；这里补"客户端正常关闭"路径，
  // 两者都经由 clientLoop -> closeClient（历史上 join 自己导致 terminate 的入口）。
  int fd2 = rawConnect(kPort);
  assert(fd2 >= 0);
  assert(waitFor([&] { return server.clientCount() == 1; }, 2000));
  ::close(fd2);  // 正常关闭连接
  assert(waitFor([&] { return server.clientCount() == 0; }, 5000) &&
         "server did not reap normally-disconnected client (or crashed)");
  std::cout << "[5] server survives normal disconnect, reaps session: OK\n";

  server.stop();
  std::cout << "test_tcp_framing: all assertions passed\n";
  return 0;
}
