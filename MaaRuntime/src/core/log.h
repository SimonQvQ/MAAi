#pragma once
#include <functional>
#include <string>

namespace maai {

enum class LogLevel { Debug = 0, Info = 1, Warn = 2, Error = 3 };

// 可重定向的日志器。iOS 层会接到 maai_log_ios 之类的回调。
class Log {
 public:
  static Log& instance();

  using Sink = std::function<void(LogLevel, const std::string& message)>;

  void setLevel(LogLevel level);
  LogLevel level() const;
  void setSink(Sink sink);

  void write(LogLevel level, const std::string& message);

  static void debug(const std::string& msg) { instance().write(LogLevel::Debug, msg); }
  static void info(const std::string& msg)  { instance().write(LogLevel::Info, msg); }
  static void warn(const std::string& msg)  { instance().write(LogLevel::Warn, msg); }
  static void error(const std::string& msg) { instance().write(LogLevel::Error, msg); }

 private:
  Log() = default;
  LogLevel level_ = LogLevel::Info;
  Sink sink_;
};

}  // namespace maai
