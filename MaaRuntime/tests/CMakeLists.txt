set(MAAI_TEST_SOURCES
  test_ipc.cpp
  test_tcp_roundtrip.cpp
  test_tcp_framing.cpp)

foreach(src ${MAAI_TEST_SOURCES})
  get_filename_component(name ${src} NAME_WE)
  add_executable(${name} ${src})
  target_link_libraries(${name} PRIVATE maai_core)
  add_test(NAME ${name} COMMAND ${name})
  # socket 测试挂起时快速失败，避免拖满 ctest 默认 1500s 超时
  set_tests_properties(${name} PROPERTIES TIMEOUT 30)
endforeach()
