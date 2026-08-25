# MAAi -- iOS 版明日方舟助手 (MAA)

MAA 的 iPhone 移植：**服务器（Docker）跑 MaaFramework + 官方资源，iPhone 上注入 dylib 负责截图/点击/浮层**，两端通过 JSON-over-TCP 通信。Web 控制台基于 **MWU**（MaaFramework WebUI）实现任务组合与调度。

[![CI](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml/badge.svg)](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml)
[![Docker Hub](https://img.shields.io/docker/pulls/simonqvq/maai-server.svg)](https://hub.docker.com/r/simonqvq/maai-server)

## 架构

```
  iPhone 侧                          Docker 服务器 (Linux)
  明日方舟 + MAAiAgent.dylib          maai-server
   - 截图/点击/输入/浮层   --17171-->  maai-bridge (agent 通道)
   - 浮层显示执行节点/状态  <--JSON--  MaaFramework 5.12.3 任务引擎
   - 浮层可点开设置服务器地址         官方 MAA v5 资源 (pipeline 等)
                                       MWU WebUI (8080)
                                        - 设备/任务/调度/组合
                                        - iPhone = MAAi 控制器
```

- 任务逻辑（识别/点击流程）来自 **官方 MAA v5.12.2 资源包**，构建时自动转换为标准 MaaFramework bundle（见 `convert_maares.py`），开箱即用。
- 不在手机上重写 MAA 逻辑 —— dylib 只负责把「手」伸到 iPhone 上，引擎在服务器。
- **MWU 集成**：新增 `MAAi` 设备类型（iPhone 自定义控制器），可组合多任务（启动/刷理智/基建/公招…）一键执行，支持定时调度。

## 快速开始

```bash
docker run -d --name maai \
  -p 17171:17171 -p 8080:8080 \
  simonqvq/maai-server:latest
```

- **Web 控制台（MWU）**：浏览器打开 `http://<服务器IP>:8080`。
  1. 设备页选 **iPhone（MAAiAgent）**，地址填 `0.0.0.0:17171`（默认）→ 连接；
  2. 选资源 **MAA**；
  3. 任务页勾选组合（如「一键长草」预设：启动→每日→基建→公招→刷理智）→ 启动。
- **Agent 端口**：`17171`，iPhone 端 dylib 拨入。
- **日志**：`docker logs -f maai`，或 WebUI 内实时日志。

## iPhone 端（dylib）

1. 在 GitHub Actions 的 **MAAiAgent-dylib** 工件里下载 `MAAiAgent.dylib`（免签名编译）。
2. 注入明日方舟进程（LiveContainer / 越狱环境均可）。
3. 打开游戏 → 浮层显示「MAAi 未连接」→ **点浮层标签**弹出设置，填 `<服务器IP>:17171` 保存并重启连接（首次运行即使未填地址也会显示浮层）。
4. 连接成功后即可在 MWU 里连接/跑任务，浮层实时显示「执行: 节点名」/「任务完成 ✅」。

> 连接地址也可用环境变量 `MAAI_SERVER_HOST` / `MAAI_SERVER_PORT` 预设（优先级高于浮层设置）。

## 常用环境变量（容器）

| 变量 | 默认 | 说明 |
|---|---|---|
| `MAAI_WEB_PORT` | `8080` | MWU Web 控制台端口 |

> agent 通道固定监听 `0.0.0.0:17171`（MWU 设备页地址默认 `0.0.0.0:17171`）；资源目录由 `interface.json` 的 resource path 决定（默认 `resource`，相对 `/opt/maai/mwu`）。

## 资源

- 默认烘焙 **官方 MAA v5.12.2** 完整资源：构建时 `fetch_official_resources.sh` 下载并提取 `resource/`，再经 `convert_maares.py` 转成 MaaFramework 5.12.3 可加载的标准 bundle（`pipeline/` 任务定义 + `image/` 模板 + `model/ocr/` 识别模型）。
- 镜像内可直接用 MWU 选资源加载；加载后任务节点（`StartUp`/`Fight`/`Award`/`Recruit`/`Infrast`…）立即可跑。

## 构建与发布

所有构建都在 **GitHub Actions** 完成（本地/群晖不编译）：

```bash
# 推 main 触发 CI：dylib 交叉编译 + Linux 运行时 + MWU Docker 镜像构建验证
git push origin main

# 打 tag 触发发布：MWU Web 前端 + Docker 镜像推到 Docker Hub (latest)
git tag v0.1.6 && git push origin v0.1.6
```

- `maai-server/mwu/`：MAAi×MWU 集成（`maa_bridge.py` 通道 + `maa_controller.py` 自定义控制器 + 前后端 patch 脚本 + `interface.json` 任务组合/预设）。
- 仓库 Secrets：`DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`（发布）、`MAAFW_URL` / `MAA5_RES_URL`（资源下载，均可选）。

## 协议（MAAi 便捷线格式）

- 帧：`4 字节大端长度 + UTF-8 JSON`，单帧 ≤ 16MB。
- 请求/响应带 `req_id`；事件上行 `{type:"event", event, data}`。
- 主要命令：`SCREENCAP`（jpeg/raw）、`CLICK`、`SWIPE`、`TOUCH_DOWN/MOVE/UP`、`PRESS_KEY`、`INPUT_TEXT`、`DISPLAY`（浮层文本）、`STATUS`。

## 已知边界

- 识别依赖屏幕内容：低分辨率/缩放异常会导致模板匹配失败（官方参数已按 1080p 优化）。
- MAA v6 / MAA-Meow 任务语法（`ClickSelf`、`#self` 锚点等）不兼容 MaaFramework 5.12.3，已由 `convert_maares.py` 转标准语法；如需 v6 资源需升级运行时。

## 相关

- [MaaFramework](https://github.com/MaaXYZ/MaaFramework) · [MAA](https://github.com/MaaAssistantArknights/MaaAssistantArknights) · [MWU](https://github.com/ravizhan/MWU) · [MAA-Meow](https://github.com/Aliothmoon/MAA-Meow) · [MaaResource](https://github.com/MaaAssistantArknights/MaaResource)
