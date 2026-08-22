#!/usr/bin/env bash
set -e
ARGS=""
if [ "${MAAI_RUN:-1}" = "1" ]; then ARGS="--run"; fi
echo "[entry] webui http://0.0.0.0:${MAAI_WEB_PORT:-8080} | agent 端口 ${MAAI_BRIDGE_PORT:-17171} | run=${MAAI_RUN:-1}"
exec python3 /opt/maai/bridge/agent_bridge.py \
  --host "${MAAI_BRIDGE_HOST:-0.0.0.0}" \
  --port "${MAAI_BRIDGE_PORT:-17171}" \
  ${ARGS}
