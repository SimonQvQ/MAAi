# MAAi — iOS 明日方舟小助手

> MAA-Meow 的 iOS 版：**大脑跑在 Docker，iPhone 只当眼睛和手**。

[![CI](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml/badge.svg)](https://github.com/SimonQvQ/MAAi/actions/workflows/ci.yml)
[![Docker Hub Publish](https://github.com/SimonQvQ/MAAi/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/SimonQvQ/MAAi/actions/workflows/docker-publish.yml)

- 服务器（Docker）：MaaFramework(Linux) + MXU WebUI —— 识别、决策、任务调度都在这里
- iPhone（明日方舟进程内）：MAAiAgent.dylib —— 只负责截图、触摸注入、游戏内小浮层
- 两者之间：MAAi 便捷协议（4 字节大端长度 + JSON，TCP 17171）

---

## 架构

```
[浏览器/桌面] 打开 MXU 选任务
    │
    ▼
[Docker maai-server: MXU + MaaFramework(Linux)]   ◄──── 便捷协议 TCP :17171 ────┐
    │                                            ▲                             │
    │ 识别/决策/操作流                            │ 截图流 / 状态事件             │
    ▼                                            │                             │
 MaaFramework 控制器(网络)                        └──────────►  [iPhone 明日方舟进程]
                                                                 MAAiAgent.dylib
                                                                  ├ 截图(JPEG/RGBA)
                                                                  ├ 触摸注入
                                                                  └ 浮层:连接状态+当前操作
```

## 目录

```
maai-server/           Docker 大脑：Dockerfile / docker-compose / MXU + MaaFramework + bridge
MaaRuntime/            平台无关核心(线格式/TCP Server+Client) + iOS MAAiAgent.dylib
Scripts/               build_core / fetch_maameow_resources / inject / push_to_github
.github/workflows/     ci.yml(自动编译) + docker-publish.yml(发 Docker Hub)
```

## 快速开始

### 1. 服务器（Docker）

**方式 A：直接拉 Docker Hub 镜像（推荐）**

```bash
docker run -d --name maai \
  -p 17171:17171 \
  -p 5800:5800 \
  -v /path/to/interface.json:/opt/maai/interface.json \
  simonqvq/maai-server:latest
```

> 镜像已内置最新 MAA 资源包（发布时自动从官方 `MaaAssistantArknights/MaaResource` 下载）。
> 想覆盖资源可再加 `-v /path/to/resource:/opt/maai/resource`。

**方式 B：本地构建**

```bash
cd maai-server
MAAFW_URL=... MXU_URL=... ./setup.sh          # 自动下 MaaFramework + MXU + MAA 资源包
docker compose up -d --build
```

> 资源包自动下载脚本：`maai-server/fetch_resource.sh`（本地）或 `Scripts/fetch_maameow_resources.sh`（仓库脚本）；
> 来源为官方 `MaaAssistantArknights/MaaResource`，与 MAA-Meow 同源。

### 2. iPhone（MAAiAgent.dylib）

1. 取 dylib：到仓库 Actions 里下载 **MAAiAgent-dylib** 产物（macOS 交叉编译，免签名），
   或在 macOS 上本地编：
   ```bash
   cmake -B build-ios -G Xcode \
     -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_SYSROOT=iphoneos \
     -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO \
     -DMAAI_BUILD_IOS_AGENT=ON
   cmake --build build-ios --config Release --target MAAiAgent
   ```
2. 注入明日方舟（LiveContainer 等），参考 Scripts/inject.sh 模板。
3. 设置环境变量（由注入方式决定怎么带进去）：
   - `MAAI_SERVER_HOST` —— Docker 主机 IP
   - `MAAI_SERVER_PORT` —— 默认 17171
4. 打开明日方舟，dylib 自动拨号连服务器，顶部浮层显示「已连接 + 当前操作」。

### 3. 跑任务

**自动模式（推荐）**：容器直接当任务执行器，agent 一拨入就开跑：

```bash
docker run -d --name maai \
  -p 17171:17171 -p 5800:5800 \
  -e MAAI_RUN=1 -e MAAI_ENTRY=StartUp \
  simonqvq/maai-server:latest
```

- agent 连上后自动加载内置资源跑 `StartUp`，iPhone 浮层实时显示「执行: 节点名」/ 完成状态
- 换任务：`-e MAAI_ENTRY=Fight` 等（取决于资源包里的入口名）

**MXU 界面模式**：VNC 连服务器 `5800` 端口可看到 MXU 桌面界面（xvfb 无头运行）。
MXU 尚不支持自定义网络控制器，由 bridge 直接驱动任务；MXU 只做预览/调试。

## 便捷协议

线格式：**4 字节大端长度 + UTF-8 JSON**，单帧上限 16MB。

实现（两处，保持一致）：
- C++ ：`MaaRuntime/src/core/ipc_message.h`
- Python：`maai-server/bridge/agent_bridge.py`

| 方向 | 命令 / 事件 |
| --- | --- |
| 服务器 → agent | `SCREENCAP`(jpeg/raw) `CLICK` `SWIPE` `TOUCH_DOWN/MOVE/UP` `PRESS_KEY` `INPUT_TEXT` `DISPLAY`(浮层文本) `SET_STREAM` `SET_TOUCH` `SET_OVERLAY` `STATUS` `PING` |
| agent → 服务器 | 事件 `STATUS`(连接即上报) `SCREENSHOT`(流) `LOG`；所有请求回 `response` |

## 构建 / CI

推送即自动跑（`.github/workflows/ci.yml`）：
- **Runtime Core (Linux)**：cmake + ctest
- **MAAiAgent.dylib (iOS cross)**：macOS 上交叉编译，产物上传为 artifact
- **maai-server image (Docker)**：校验 Dockerfile 可构建

本地测核心：

```bash
cmake -B build -G Ninja -DMAAI_BUILD_RUNTIME_CORE=ON -DMAAI_ENABLE_TESTS=ON
cmake --build build && ctest --test-dir build
```

## 发布到 Docker Hub

仓库需配置 secrets：

| Secret | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token（Read & Write） |
| `MAAFW_URL` | MaaFramework Linux 运行库 zip 直链 |
| `MXU_URL` | MXU Linux tar.gz 直链 |
| `MEOW_RESOURCE_URL` | MAA 资源 zip 直链（可选，默认官方 main.zip） |

触发（任选其一）：
- 打 tag：`git tag v0.1.0 && git push origin v0.1.0`
- Actions → **Docker Hub Publish** → Run workflow

产物：`simonqvq/maai-server:latest` + `:<tag>`。

## 已知边界

- **触摸注入**用私有 API（`_handleHIDEvent:`），LiveContainer/受限沙盒可能被拒；失败会返回错误让流水线重试。
- **MaaFramework 无官方 iOS 产物**，所以核心放服务器（原生支持 Linux）。bridge 已把 agent 包装成 MaaFramework v5 自定义控制器（官方 `maafw` Python 绑定），`--run` 模式可直接跑任务。
- **延迟/带宽**：截图从 iPhone 传到服务器，Wi-Fi 1080p/5fps 约几百 KB/s；4G 建议降帧率/画质。
- **MXU 是桌面 Tauri 应用**，容器内用 xvfb 无头运行，界面目前走 VNC；网页化访问是后续项。
