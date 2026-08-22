# MAAi -- iOS 版明日方舟助手 (MAA)

MAA 的 iPhone 移植：**服务器（Docker）跑 MaaFramework + 官方资源，iPhone 上注入 dylib 负责截图/点击/浮层**，两端通过 JSON-over-TCP 通信。

[![CI](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml/badge.svg)](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml)
[![Docker Hub](https://img.shields.io/docker/pulls/simonqvq/maai-server.svg)](https://hub.docker.com/r/simonqvq/maai-server)

## 架构

```
  iPhone 侧                          Docker 服务器 (Linux)
  明日方舟 + MAAiAgent.dylib          maai-server
   - 截图/点击/输入/浮层   --17171-->  maai-bridge (agent 通道)
   - 浮层显示执行节点/状态  <--JSON--  MaaFramework 5.12.3 任务引擎
   - 浮层可点开设置服务器地址         官方 MAA v5 资源 (pipeline 等)
                                      Web 控制台 (8080，替代 VNC)
```

- 任务逻辑（识别/点击流程）来自 **官方 MAA v5.28.5 资源包**，已烘焙进镜像，开箱即用。
- 不在手机上重写 MAA 逻辑 —— dylib 只负责把「手」伸到 iPhone 上，引擎在服务器。

## 快速开始

```bash
docker run -d --name maai \
  -p 17171:17171 -p 8080:8080 \
  simonqvq/maai-server:latest
```

- **Web 控制台**：浏览器打开 `http://<服务器IP>:8080` —— 看 agent 连接状态、实时截图、任务进度，可开始/停止任务（默认自动跑 `StartUp`）。
- **Agent 端口**：`17171`，iPhone 端 dylib 拨入。
- **日志**：`docker logs -f maai`。

## iPhone 端（dylib）

1. 在 GitHub Actions 的 **MAAiAgent-dylib** 工件里下载 `MAAiAgent.dylib`（免签名编译）。
2. 注入明日方舟进程（LiveContainer / 越狱环境均可）。
3. 打开游戏 → 浮层显示「MAAi 未连接」→ **点浮层标签**弹出设置，填 `<服务器IP>:17171` 保存并重启连接。
4. 连接成功后自动开始跑任务，浮层实时显示「执行: 节点名」/「任务完成 ✅」。

> 连接地址也可用环境变量 `MAAI_SERVER_HOST` / `MAAI_SERVER_PORT` 预设（优先级高于浮层设置）。

## 常用环境变量（容器）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MAAI_RUN` | `1` | `1` 时 agent 拨入自动跑任务；`0` 仅监听 agent 通道 |
| `MAAI_ENTRY` | `StartUp` | 任务入口名（pipeline 节点名） |
| `MAAI_RESOURCE` | `/opt/maai/resource` | MaaFramework 资源包目录 |
| `MAAI_WEB_PORT` | `8080` | Web 控制台端口 |
| `MAAI_BRIDGE_HOST` / `MAAI_BRIDGE_PORT` | `0.0.0.0` / `17171` | agent 通道监听 |

换任务：`docker run ... -e MAAI_ENTRY=Fight simonqvq/maai-server:latest`（取决于资源包里的节点名，如 `StartUp`/`Fight`/`Award`…）。

## 资源

- 默认烘焙 **官方 MAA v5.28.5** 完整资源（`pipeline/` 任务定义 + `template/` 模板图 + OCR 模型 + 数据），与 MaaFramework 5.12.3 完全兼容。
- 可选叠加官方 MaaResource 动态数据（新活动地图/公招数据）：构建时传 `MEOW_RESOURCE_URL`。

## 构建与发布

```bash
docker build -t maai-server maai-server

git tag v0.1.5 && git push origin v0.1.5   # 触发 CI 自动发布 Docker Hub
```

仓库 Secrets：`DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`（发布）、`MAAFW_URL` / `MAA5_RES_URL` / `MEOW_RESOURCE_URL`（资源下载，均可选）。

## 协议（MAAi 便捷线格式）

- 帧：`4 字节大端长度 + UTF-8 JSON`，单帧 ≤ 16MB。
- 请求/响应带 `req_id`；事件上行 `{type:"event", event, data}`。
- 主要命令：`SCREENCAP`（jpeg/raw）、`CLICK`、`SWIPE`、`TOUCH_DOWN/MOVE/UP`、`PRESS_KEY`、`INPUT_TEXT`、`DISPLAY`（浮层文本）、`STATUS`。

## 已知边界

- 识别依赖屏幕内容：低分辨率/缩放异常会导致模板匹配失败（官方参数已按 1080p 优化）。
- 本仓库内置 `MaaResource` 数据包仅含数据；**任务定义**来自官方 MAA v5 完整资源（已烘焙）。
- MAA v6（官方新版/MAA-Meow）任务语法不兼容当前 MaaFramework 5.12.3，如需 v6 资源需升级运行时（见 `fetch_official_resources.sh` 说明）。
- 目前是 bridge 直接驱动任务；MXU（桌面 GUI 客户端）暂未接入，Web 控制台已覆盖其「看状态/截图」用途。

## 相关

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework) · [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights) · [MAA-Meow](https://github.com/Aliothmoon/MAA-Meow) · [MaaResource](https://github.com/MaaAssistantArknights/MaaResource) · [MXU](https://github.com/MistEO/MXU)
