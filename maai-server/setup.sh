#!/usr/bin/env bash
# 下载 MaaFramework(Linux) 运行库 + MXU 可执行文件 + MAA 资源包。
#
# 用法:
#   MAAFW_URL=<直链> MXU_URL=<直链> [MEOW_RESOURCE_URL=<直链>] maai-server/setup.sh
# 直链来源:
#   MaaFramework: https://github.com/MaaXYZ/MaaFramework/releases  (MAA-linux-x86_64-*.zip)
#   MXU:          https://github.com/MistEO/MXU/releases           (MXU-linux-x86_64-*.tar.gz)
#   MAA 资源:     默认官方 https://github.com/MaaAssistantArknights/MaaResource main.zip
set -euo pipefail
cd "$(dirname "$0")"

: "${MAAFW_URL:?'需要 MAAFW_URL (MaaFramework linux 运行库直链)'}"
: "${MXU_URL:?'需要 MXU_URL (MXU linux 可执行文件直链)'}"

echo ">>> 下载 MaaFramework..."
curl -fsSL --retry 3 -o /tmp/maafw.zip "$MAAFW_URL"
rm -rf maafw /tmp/maafw_pkg && mkdir -p maafw /tmp/maafw_pkg
unzip -q /tmp/maafw.zip -d /tmp/maafw_pkg
cp -a /tmp/maafw_pkg/*/bin/. maafw/
chmod +x maafw/* 2>/dev/null || true

echo ">>> 下载 MXU..."
curl -fsSL --retry 3 -o /tmp/mxu_pkg "$MXU_URL"
tar xzf /tmp/mxu_pkg -C /tmp
install -m 755 /tmp/mxu ./mxu

echo ">>> 下载 MAA 资源..."
./fetch_resource.sh "${MEOW_RESOURCE_URL:-}" ./resource

echo ">>> 就绪:"
echo "  maafw/     $(ls maafw | head -3)"
echo "  mxu        $(test -f mxu && echo ok)"
echo "  resource/  $(test -d resource && echo ok)"
echo "下一步: docker compose up -d --build"
