#include "core/ipc_message.h"

#include <utility>

#include "core/version.h"

namespace maai::ipc {

MsgType parseMsgType(const std::string& s) {
  if (s == "request") return MsgType::Request;
  if (s == "response") return MsgType::Response;
  if (s == "event") return MsgType::Event;
  return MsgType::Unknown;
}

std::string msgTypeToString(MsgType t) {
  switch (t) {
    case MsgType::Request: return "request";
    case MsgType::Response: return "response";
    case MsgType::Event: return "event";
    default: return "unknown";
  }
}

Message Message::request(std::string reqId, std::string cmd, nlohmann::json params) {
  Message m;
  m.type = MsgType::Request;
  m.reqId = std::move(reqId);
  m.cmd = std::move(cmd);
  m.params = std::move(params);
  return m;
}

Message Message::response(const std::string& reqId, nlohmann::json result) {
  Message m;
  m.type = MsgType::Response;
  m.reqId = reqId;
  m.ok = true;
  m.params = std::move(result);
  return m;
}

Message Message::errorResponse(const std::string& reqId, const std::string& error) {
  Message m;
  m.type = MsgType::Response;
  m.reqId = reqId;
  m.ok = false;
  m.error = error;
  m.params = nlohmann::json::object();
  return m;
}

Message Message::eventMessage(std::string event, nlohmann::json payload) {
  Message m;
  m.type = MsgType::Event;
  m.event = std::move(event);
  m.params = std::move(payload);
  return m;
}

nlohmann::json toJson(const Message& m) {
  nlohmann::json j;
  j["v"] = kProtocolVersion;
  j["type"] = msgTypeToString(m.type);
  switch (m.type) {
    case MsgType::Request:
      j["req_id"] = m.reqId;
      j["cmd"] = m.cmd;
      j["params"] = m.params.is_null() ? nlohmann::json::object() : m.params;
      break;
    case MsgType::Response:
      j["req_id"] = m.reqId;
      j["ok"] = m.ok;
      j["result"] = m.ok ? (m.params.is_null() ? nlohmann::json::object() : m.params) : nlohmann::json::object();
      if (!m.ok) j["error"] = m.error;
      break;
    case MsgType::Event:
      j["event"] = m.event;
      j["payload"] = m.params.is_null() ? nlohmann::json::object() : m.params;
      break;
    default:
      break;
  }
  return j;
}

std::optional<Message> fromJson(const nlohmann::json& j) {
  if (!j.is_object()) return std::nullopt;
  auto v = j.value("v", 0);
  if (v != kProtocolVersion) return std::nullopt;

  Message m;
  auto typeIt = j.find("type");
  if (typeIt == j.end() || !typeIt->is_string()) return std::nullopt;
  m.type = parseMsgType(typeIt->get<std::string>());

  if (m.type == MsgType::Request) {
    m.reqId = j.value("req_id", "");
    m.cmd = j.value("cmd", "");
    auto p = j.find("params");
    m.params = (p != j.end() && !p->is_null()) ? *p : nlohmann::json::object();
  } else if (m.type == MsgType::Response) {
    m.reqId = j.value("req_id", "");
    m.ok = j.value("ok", false);
    m.error = j.value("error", "");
    auto r = j.find("result");
    m.params = (r != j.end() && !r->is_null()) ? *r : nlohmann::json::object();
  } else if (m.type == MsgType::Event) {
    m.event = j.value("event", "");
    auto p = j.find("payload");
    m.params = (p != j.end() && !p->is_null()) ? *p : nlohmann::json::object();
  } else {
    return std::nullopt;
  }
  return m;
}

std::vector<uint8_t> encodeFrame(const nlohmann::json& j) {
  std::string body = j.dump();
  std::vector<uint8_t> frame;
  frame.reserve(4 + body.size());
  uint32_t len = static_cast<uint32_t>(body.size());
  frame.push_back(static_cast<uint8_t>((len >> 24) & 0xFF));
  frame.push_back(static_cast<uint8_t>((len >> 16) & 0xFF));
  frame.push_back(static_cast<uint8_t>((len >> 8) & 0xFF));
  frame.push_back(static_cast<uint8_t>(len & 0xFF));
  frame.insert(frame.end(), body.begin(), body.end());
  return frame;
}

bool decodeFrame(const uint8_t* data, size_t size, size_t& consumed, nlohmann::json& out) {
  consumed = 0;
  if (size < 4) return false;
  uint32_t len = (static_cast<uint32_t>(data[0]) << 24) |
                 (static_cast<uint32_t>(data[1]) << 16) |
                 (static_cast<uint32_t>(data[2]) << 8) |
                 static_cast<uint32_t>(data[3]);
  if (len > 16 * 1024 * 1024) return false;  // 拒绝超大帧
  if (size < 4u + len) return false;
  try {
    out = nlohmann::json::parse(data + 4, data + 4 + len);
  } catch (...) {
    return false;
  }
  consumed = 4u + len;
  return true;
}

}  // namespace maai::ipc
