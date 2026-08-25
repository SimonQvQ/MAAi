set(MAAI_TEST_SOURCES
  test_ipc.cpp
  test_tcp_roundtrip.cpp
  test_disconnect_cleanup.cpp)

foreach(src ${MAAI_TEST_SOURCES})
  get_filename_component(name ${src} NAME_WE)
  add_executable(${name} ${src})
  target_link_libraries(${name} PRIVATE maai_core)
  add_test(NAME ${name} COMMAND ${name})
endforeach()
