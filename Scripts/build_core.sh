#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cmake -B build -G Ninja -DMAAI_BUILD_RUNTIME_CORE=ON -DMAAI_ENABLE_TESTS=ON
cmake --build build
ctest --test-dir build --output-on-failure
