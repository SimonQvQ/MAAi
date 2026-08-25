cmake_minimum_required(VERSION 3.20)
project(MAAi LANGUAGES CXX)  # 版本号统一由 src/core/version.h 的 MAAI_VERSION 定义（当前 0.01b）

# MAAi —— iOS 版明日方舟小助手（Docker 架构）
#
#   maai-server : Docker 里跑 MaaFramework(Linux) + MXU WebUI，大脑在服务器
#   MAAiAgent.dylib : 注入明日方舟进程，只做 截图/触摸/浮层，走便捷 JSON-over-TCP 连 server
#
# 构建目标:
#   - maai_core    : 平台无关核心（线格式 / TCP Server+Client / 命令分发），Linux CI 可测
#   - MAAiAgent.dylib : iOS 端 agent（需要 Apple 工具链，macOS runner 可直接交叉编译）
#
# 常用:
#   cmake -B build -DMAAI_BUILD_RUNTIME_CORE=ON
#   cmake --build build && ctest --test-dir build

option(MAAI_BUILD_RUNTIME_CORE "Build the platform-independent runtime core" ON)
option(MAAI_BUILD_IOS_AGENT "Build the iOS MAAiAgent.dylib (requires Apple toolchain)" OFF)
option(MAAI_ENABLE_TESTS "Enable tests" ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MAAI_ENABLE_TESTS)
  enable_testing()
endif()

add_subdirectory(MaaRuntime)
