#!/usr/bin/env bash
# 下载 MaaFramework(Linux) 运行库 + MXU 可执行文件到 maai-server 目录。
#
# 用法:
#   MAAFW_URL=<直链> MXU_URL=<直链> Scripts/fetch_maai_server.sh
# 直链可分别来自:
#   MaaFramework: https://github.com/MaaXYZ/MaaFramework/releases  (选 linux-x86_64 包)
#   MXU:          https://github.com/MistEO/MXU/releases           (选 linux-x86_64 单文件)
set -euo pipefail
cd "$(dirname "$0")"

: "${MAAFW_URL:?'需要 MAAFW_URL (MaaFramework linux 运行库直链)'}"
: "${MXU_URL:?'需要 MXU_URL (MXU linux 可执行文件直链)'}"

echo ">>> 下载 MaaFramework..."
curl -fsSL --retry 3 -o /tmp/maafw.zip "$MAAFW_URL"
rm -rf maafw && mkdir -p maafw
unzip -q /tmp/maafw.zip -d maafw
chmod +x maafw/* 2>/dev/null || true

echo ">>> 下载 MXU..."
curl -fsSL --retry 3 -o mxu "$MXU_URL"
chmod +x mxu

echo ">>> 就绪:"
echo "  maafw/  $(ls maafw | head -5)"
echo "  mxu    $(test -f mxu && echo ok)"
echo "下一步: 编辑 interface.json/resource/ 后 docker compose up -d --build"
