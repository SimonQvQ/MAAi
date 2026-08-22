# MaaRuntime —— iOS 端 agent 终端 "MAAiAgent.dylib" + 平台无关核心
#
#   src/core/   线格式 / TCP Server+Client / 命令分发   -> maai_core（Linux 可测）
#   src/ios/    截图 / 触摸 / 浮层 / agent 运行时       -> MAAiAgent.dylib（Apple 工具链）

set(MAAI_CORE_SOURCES
  src/core/ipc_message.cpp
  src/core/ipc_server.cpp
  src/core/ipc_client.cpp
  src/core/log.cpp)

# nlohmann/json：优先系统包，没有则 FetchContent 拉单头文件（CI/iOS 场景）
find_package(nlohmann_json 3.11 CONFIG QUIET)
if(NOT nlohmann_json_FOUND)
  message(STATUS "nlohmann_json not found via find_package, fetching single header")
  include(FetchContent)
  FetchContent_Declare(nlohmann_json
    URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
    URL_HASH SHA256=d6c65aca6b1ed68e7a182f4757257b107ae403032760ed6ef121c9d55e81757d)
  FetchContent_MakeAvailable(nlohmann_json)
endif()

add_library(maai_core STATIC ${MAAI_CORE_SOURCES})
target_include_directories(maai_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(maai_core PUBLIC nlohmann_json::nlohmann_json)
target_compile_definitions(maai_core PUBLIC MAAI_CORE_STATIC=1)

if(MAAI_ENABLE_TESTS)
  add_subdirectory(tests)
endif()

# ---- iOS: MAAiAgent.dylib（无需 MaaFramework SDK，macOS 上可直接交叉编译）----
if(MAAI_BUILD_IOS_AGENT AND APPLE)
  enable_language(OBJCXX)

  add_library(MAAiAgent SHARED
    src/ios/MAAiAgent.mm
    src/ios/MAOverlay.mm
    src/ios/MAAScreenCapture.mm
    src/ios/MAATouchInjector.mm)

  target_include_directories(MAAiAgent PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
  target_link_libraries(MAAiAgent PRIVATE
    maai_core
    "-framework Foundation"
    "-framework UIKit"
    "-framework IOKit"
    "-framework CoreGraphics")

  # dylib 内使用私有 API（触摸注入），放宽编译检查
  target_compile_options(MAAiAgent PRIVATE -fobjc-arc -Wno-deprecated-declarations -Wno-undeclared-selector)

  set_target_properties(MAAiAgent PROPERTIES
    OUTPUT_NAME "MAAiAgent"
    PREFIX "lib")
endif()
