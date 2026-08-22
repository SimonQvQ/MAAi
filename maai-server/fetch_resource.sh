#!/usr/bin/env bash
# 自动下载最新 MAA 资源包（MaaAssistantArknights/MaaResource）并解压 resource/ 到目标目录。
# 用法: fetch_resource.sh [URL] [DEST]
#   URL   默认取 $MEOW_RESOURCE_URL，再默认官方 main.zip
#   DEST  默认 ./resource
set -euo pipefail

URL="${1:-${MEOW_RESOURCE_URL:-https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip}}"
DEST="${2:-resource}"

echo ">>> 下载 MAA 资源包: $URL"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL --retry 3 -o "$TMP/maares.zip" "$URL"

mkdir -p "$DEST"
python3 - "$TMP/maares.zip" "$DEST" <<'PY'
import os, sys, zipfile

zip_path, dest = sys.argv[1], sys.argv[2]
zf = zipfile.ZipFile(zip_path)
names = zf.namelist()

# 找到 <top>/resource/ 前缀
prefix = None
for n in names:
    parts = [p for p in n.split('/') if p]
    if len(parts) == 2 and parts[1] == 'resource':
        prefix = parts[0] + '/resource/'
        break
if not prefix:
    for n in names:
        if n.endswith('/resource/'):
            prefix = n
            break
if not prefix:
    sys.exit('未在压缩包中找到 resource/ 目录')

os.makedirs(dest, exist_ok=True)
count = 0
for n in names:
    if not n.startswith(prefix):
        continue
    rel = n[len(prefix):]
    if not rel:
        continue
    target = os.path.join(dest, rel)
    if n.endswith('/'):
        os.makedirs(target, exist_ok=True)
        continue
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'wb') as f:
        f.write(zf.read(n))
    count += 1
print(f"解压 {prefix} -> {dest}，{count} 个文件")
PY

echo ">>> 资源已就绪: $DEST"
