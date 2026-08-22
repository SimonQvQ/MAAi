#!/usr/bin/env bash
# 下载 MAA-Meow 资源包。可用环境变量 MAA_MEOW_RESOURCE_URL 指定直链。
set -euo pipefail
URL="${MAA_MEOW_RESOURCE_URL:-}"
if [[ -z "$URL" ]]; then
  echo "未设置 MAA_MEOW_RESOURCE_URL；请从 https://github.com/Aliothmoon/MAA-Meow/releases 复制资源直链"
  echo "例如: MAA_MEOW_RESOURCE_URL=https://.../res.zip $0"
  exit 1
fi
OUT="resources-download"
mkdir -p "$OUT"
curl -L --fail --retry 3 -o "$OUT/resource.zip" "$URL"
unzip -o -q "$OUT/resource.zip" -d "$OUT/maameow_resource"
echo "已解压到 $OUT/maameow_resource（把含 pipeline/ 的资源目录放到 maai-server/resource/ 即可）"
