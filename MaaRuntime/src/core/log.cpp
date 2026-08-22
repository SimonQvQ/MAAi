#include "core/log.h"

#include <cstdio>
#include <utility>

namespace maai {

Log& Log::instance() {
  static Log s_instance;
  return s_instance;
}

void Log::setLevel(LogLevel level) { level_ = level; }
LogLevel Log::level() const { return level_; }

void Log::setSink(Sink sink) { sink_ = std::move(sink); }

void Log::write(LogLevel level, const std::string& message) {
  if (level < level_) return;
  if (sink_) {
    sink_(level, message);
    return;
  }
  const char* tag = level == LogLevel::Debug ? "D" :
                    level == LogLevel::Info  ? "I" :
                    level == LogLevel::Warn  ? "W" : "E";
  std::fprintf(stderr, "[maai][%s] %s\n", tag, message.c_str());
}

}  // namespace maai
