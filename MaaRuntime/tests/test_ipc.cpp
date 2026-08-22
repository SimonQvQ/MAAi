// 测试 IPC 帧编解码与消息 JSON 结构。不依赖网络，纯内存。
#include <cassert>
#include <cstdint>
#include <iostream>

#include "core/ipc_message.h"

using namespace maai::ipc;

int main() {
  // 消息 JSON 往返
  auto req = Message::request("req-1", "START_TASK", {{"name", "Fight"}, {"repeat", 3}});
  auto json = toJson(req);
  auto parsed = fromJson(json);
  assert(parsed.has_value());
  assert(parsed->type == MsgType::Request);
  assert(parsed->reqId == "req-1");
  assert(parsed->cmd == "START_TASK");
  assert(parsed->params["name"] == "Fight");
  assert(parsed->params["repeat"] == 3);

  auto resp = Message::response("req-1", {{"task_id", "maatask-1"}});
  auto parsedResp = fromJson(toJson(resp));
  assert(parsedResp->type == MsgType::Response);
  assert(parsedResp->ok);
  assert(parsedResp->params["task_id"] == "maatask-1");

  auto err = Message::errorResponse("req-1", "boom");
  auto parsedErr = fromJson(toJson(err));
  assert(!parsedErr->ok);
  assert(parsedErr->error == "boom");

  auto ev = Message::eventMessage("LOG", {{"level", "info"}, {"message", "hi"}});
  auto parsedEv = fromJson(toJson(ev));
  assert(parsedEv->type == MsgType::Event);
  assert(parsedEv->event == "LOG");
  assert(parsedEv->params["message"] == "hi");

  // 帧编码: 4 字节大端长度 + JSON
  nlohmann::json j = {{"v", 1}, {"type", "event"}, {"event", "TASK_FINISHED"}, {"payload", nlohmann::json::object()}};
  auto frame = encodeFrame(j);
  assert(frame.size() == 4 + j.dump().size());
  size_t consumed = 0;
  nlohmann::json decoded;
  bool ok = decodeFrame(frame.data(), frame.size(), consumed, decoded);
  assert(ok);
  assert(consumed == frame.size());
  assert(decoded["event"] == "TASK_FINISHED");

  // 截断帧 / 半帧均应返回 false
  size_t c2 = 0;
  nlohmann::json j2;
  assert(!decodeFrame(frame.data(), 3, c2, j2));
  assert(!decodeFrame(frame.data(), 10, c2, j2));

  // 恶意超大长度帧
  uint8_t evil[8] = {0xFF, 0xFF, 0xFF, 0xFF, 0, 0, 0, 0};
  assert(!decodeFrame(evil, 8, c2, j2));

  std::cout << "test_ipc: all assertions passed\n";
  return 0;
}
