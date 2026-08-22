#!/usr/bin/env bash
set -e
BRIDGE_ARGS=""
if [ "${MAAI_RUN:-0}" = "1" ]; then
  BRIDGE_ARGS="--run --entry ${MAAI_ENTRY:-StartUp} --resource ${MAAI_RESOURCE:-/opt/maai/resource}"
  echo "[entry] bridge 任务模式: ${BRIDGE_ARGS}"
fi
echo "[entry] 启动 maai-bridge (17171) ..."
nohup python3 /opt/maai/bridge/agent_bridge.py \
  --host "${MAAI_BRIDGE_HOST:-0.0.0.0}" \
  --port "${MAAI_BRIDGE_PORT:-17171}" \
  ${BRIDGE_ARGS} \
  > /opt/maai/debug/bridge.log 2>&1 &

echo "[entry] 启动 Xvfb + VNC (5800) + MXU ..."
Xvfb :99 -screen 0 1280x800x24 > /opt/maai/debug/xvfb.log 2>&1 &
sleep 2
nohup x11vnc -forever -shared -nopw -display :99 -rfbport 5800 \
  > /opt/maai/debug/x11vnc.log 2>&1 &
exec /opt/maai/mxu "$@" || tail -f /dev/null
