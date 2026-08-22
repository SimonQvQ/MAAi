#!/usr/bin/env bash
# 下载最新 MAA 资源包到 maai-server/resource（供 Docker 构建/运行使用）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/maai-server/fetch_resource.sh" "${1:-${MEOW_RESOURCE_URL:-}}" "$ROOT/maai-server/resource"
