#!/usr/bin/env bash
set -euo pipefail
# 在 GitHub Actions 里构建 MWU 前端 + 应用 MAAi patch。
# 用法: bash build_mwu_web.sh <maai_mwu_dir> <mwu_src_dir>
#   maai_mwu_dir : MAAi 仓库 maai-server/mwu（含 patch 脚本/maa_bridge/maa_controller）
#   mwu_src_dir  : MWU 源码目录（已 clone；构建后 page/ 输出到其中）
MAI_MWU="$(cd "$(dirname "${1:?maai mwu dir required}")" && pwd)/$(basename "$1")"
MWU_SRC="$(cd "${2:?mwu src dir required}" && pwd)"

cd "$MWU_SRC"

echo "[build_mwu_web] apply MAAi patches..."
python3 "$MAI_MWU/patch_backend.py" "$MWU_SRC" "$MAI_MWU"
python3 "$MAI_MWU/patch_frontend.py" "$MWU_SRC"

echo "[build_mwu_web] build frontend (vite -> ../page)..."
cd "$MWU_SRC/front"
pnpm config set registry https://registry.npmmirror.com >/dev/null 2>&1 || true
pnpm install --frozen-lockfile
pnpm build

echo "[build_mwu_web] page -> $MWU_SRC/page"
ls -la "$MWU_SRC/page" | head -5