#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// MAAiAgent 配置（全部可空/0 → 默认值）。
typedef struct MAAiAgentConfig {
  const char* server_host;    // 默认 "127.0.0.1"（真机请设为 Docker 主机 IP）
  uint16_t    server_port;    // 默认 17171
  int32_t     screenshot_fps; // 0 = 5
  int32_t     jpeg_quality;   // 0 = 70
  int32_t     touch_enabled;  // -1 = 1(开)
  int32_t     overlay_enabled;// -1 = 1(开)
  const char* display_name;   // 可选 agent 标识，随 STATUS 上报
} MAAiAgentConfig;

// 开始连接（非阻塞，后台自动重连）。返回 1 表示已受理启动。
int MAAiAgentStart(const MAAiAgentConfig* config);
int MAAiAgentStop(void);
int MAAiAgentIsRunning(void);
const char* MAAiAgentVersion(void); // "0.2.0"

#ifdef __cplusplus
}
#endif
