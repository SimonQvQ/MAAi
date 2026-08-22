#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace maai::ipc {

// 与 App 侧 Swift MAAMessage.swift 完全对应的 JSON 消息结构。
//
//   request :  { "v":1, "type":"request",  "req_id":"...", "cmd":"START_TASK", "params":{...} }
//   response:  { "v":1, "type":"response", "req_id":"...", "ok":true, "result":{...}, "error":null }
//   event   :  { "v":1, "type":"event",    "event":"LOG",  "payload":{...} }

constexpr int kProtocolVersion = 1;

enum class MsgType { Request, Response, Event, Unknown };

struct Message {
  MsgType type = MsgType::Unknown;
  std::string reqId;      // request / response
  std::string cmd;        // request
  nlohmann::json params;  // request params / response result / event payload
  bool ok = true;         // response
  std::string error;      // response
  std::string event;      // event name

  static Message request(std::string reqId, std::string cmd, nlohmann::json params);
  static Message response(const std::string& reqId, nlohmann::json result);
  static Message errorResponse(const std::string& reqId, const std::string& error);
  static Message eventMessage(std::string event, nlohmann::json payload);
};

MsgType parseMsgType(const std::string& s);
std::string msgTypeToString(MsgType t);

nlohmann::json toJson(const Message& m);
// 解析失败返回 nullopt。
std::optional<Message> fromJson(const nlohmann::json& j);

// 线格式: 4 字节大端长度 + UTF-8 JSON。
std::vector<uint8_t> encodeFrame(const nlohmann::json& j);
// 成功时在 out 里得到一帧并返回 true, consumed 为这帧占用的字节数。
bool decodeFrame(const uint8_t* data, size_t size, size_t& consumed, nlohmann::json& out);

}  // namespace maai::ipc
