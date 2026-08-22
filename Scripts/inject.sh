#!/usr/bin/env bash
# MAAiAgent.dylib 注入模板（骨架，具体取决于签名/LiveContainer 方案）
set -euo pipefail
DYLIB="$1"
IPA="$2"
OUT="${3:-Payload-resigned}"
echo "模板脚本：请按你的工具链补充："
echo "  1. dylib 放入 Payload/<App>.app/"
echo "  2. Mach-O 增加 LC_LOAD_DYLIB 指向 @executable_path/libMAAiAgent.dylib"
echo "  3. 重签名（dylib + 主程序 + entitlements）"
echo "  4. 安装到 LiveContainer 或直接安装"
echo "  5. 通过环境变量 MAAI_SERVER_HOST/MAAI_SERVER_PORT 指定 Docker 服务器地址"
exit 0
