#!/usr/bin/env bash
# 在 GitHub 上创建 MAAi 仓库并推送（需要 GITHUB_TOKEN，repo 权限）。
#
# 用法:
#   export GITHUB_USER=你的GitHub用户名
#   export GITHUB_TOKEN=ghp_xxx
#   Scripts/push_to_github.sh [public|private]   # 默认 public
set -euo pipefail
cd "$(dirname "$0")/.."

VISIBILITY="${1:-public}"
TOKEN="${GITHUB_TOKEN:-}"
USER="${GITHUB_USER:-}"

if [[ -z "$TOKEN" ]]; then
  echo "错误: 需要 GITHUB_TOKEN (repo 权限)"; exit 1
fi

if [[ -z "$USER" ]]; then
  echo "GITHUB_USER 未设置，尝试从 API 获取…"
  USER="$(curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/user | \
    python3 -c 'import json,sys; print(json.load(sys.stdin).get("login",""))' 2>/dev/null || true)"
fi
[[ -z "$USER" ]] && { echo "错误: 无法确定 GitHub 用户名"; exit 1; }

REPO="MAAi"
echo ">>> 创建仓库 github.com/$USER/$REPO ($VISIBILITY)"
PRIVATE="false"; [[ "$VISIBILITY" == "private" ]] && PRIVATE="true"
RESP="$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"$REPO\",\"description\":\"MAAi - iOS 版明日方舟小助手\",\"private\":$PRIVATE,\"has_issues\":true,\"has_wiki\":false}")"
if echo "$RESP" | grep -q '"full_name"'; then
  echo "    仓库创建成功"
else
  echo "    创建失败或已存在，继续推送 (详情: $(echo "$RESP" | head -c 200))"
fi

git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$USER/$REPO.git"

echo ">>> 推送 main -> origin"
git push "https://${TOKEN}@github.com/${USER}/${REPO}.git" main:main

echo ""
echo "完成:"
echo "  仓库  https://github.com/$USER/$REPO"
echo "  CI    https://github.com/$USER/$REPO/actions"
