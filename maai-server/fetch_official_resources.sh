#!/usr/bin/env bash
set -euo pipefail
# 下载官方 MAA v5.12.2 资源并转换为标准 MaaFramework bundle（pipeline/ + image/ + model/ocr/）。
# 用法: bash fetch_official_resources.sh [MAA5_RES_URL] [DEST]
#   GH_PROXY 环境变量可给 GitHub 直链加代理前缀（如 https://gh-proxy.com/）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAA5_RES_URL="${1:-https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/v5.12.2/MAA-v5.12.2-win-x64.zip}"
DEST="${2:-./resource}"
GH_PROXY="${GH_PROXY:-}"
URL="$MAA5_RES_URL"
if [ -n "$GH_PROXY" ]; then URL="${GH_PROXY}${URL}"; fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[fetch] download ${URL}"
curl -sL --retry 3 -o "$TMP/maa.zip" "$URL"

echo "[fetch] extract resource/"
python3 - "$TMP/maa.zip" "$TMP/res" <<PYEOF
import sys, zipfile, os
zp, dest = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zp)
names = z.namelist()
pref = None
for n in names:
    parts = n.split("/")
    if len(parts) >= 2 and parts[-2] == "resource" and not n.endswith("/"):
        pref = n[: n.rindex("resource/") + len("resource/")]
        break
if not pref:
    print("ERROR: no resource/ in zip", file=sys.stderr); sys.exit(1)
os.makedirs(dest, exist_ok=True)
cnt = 0
for n in names:
    if not n.startswith(pref) or n.endswith("/"):
        continue
    rel = n[len(pref):]
    if not rel: continue
    target = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f: f.write(z.read(n))
    cnt += 1
print(f"[fetch] extracted {cnt} files")
PYEOF

echo "[fetch] 转换为标准 MaaFramework bundle"
rm -rf "$DEST"
python3 "$SCRIPT_DIR/convert_maares.py" "$TMP/res" "$DEST"

echo "[fetch] done -> $DEST"