#!/usr/bin/env bash
# 下载 MaaFramework(Linux) 运行库（可选）+ 官方 MAA v5 完整资源。
#
# 用法:
#   MAAFW_URL=<直链> [MAA5_RES_URL=<直链>] [MEOW_RESOURCE_URL=<直链>] maai-server/setup.sh
# 直链来源:
#   MaaFramework: https://github.com/MaaXYZ/MaaFramework/releases  (MAA-linux-x86_64-*.zip)
#   MAA 完整资源: 默认官方 v5.28.5 https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v5.28.5/MAA-v5.28.5-win-x64.zip
#   MaaResource 数据(可选): https://github.com/MaaAssistantArknights/MaaResource main.zip
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${MAAFW_URL:-}" ]; then
  echo ">>> 下载 MaaFramework 运行库..."
  curl -fsSL --retry 3 -o /tmp/maafw.zip "$MAAFW_URL"
  rm -rf maafw /tmp/maafw_pkg && mkdir -p maafw /tmp/maafw_pkg
  unzip -q /tmp/maafw.zip -d /tmp/maafw_pkg
  cp -a /tmp/maafw_pkg/*/bin/. maafw/
  chmod +x maafw/* 2>/dev/null || true
else
  echo ">>> 跳过 MaaFramework 运行库（bridge 用 pip maafw 自带库）"
fi

echo ">>> 下载官方 MAA v5 完整资源..."
./fetch_official_resources.sh "${MAA5_RES_URL:-}" ./resource

if [ -n "${MEOW_RESOURCE_URL:-}" ]; then
  echo ">>> 叠加 MaaResource 动态数据..."
  ./fetch_resource.sh "$MEOW_RESOURCE_URL" ./resource
fi

echo ">>> 就绪: resource/ $(test -d resource && echo ok | head -1)  maafw/ $(test -d maafw && echo ok || echo skip)"
echo "下一步: docker compose up -d --build  (或见 README)"