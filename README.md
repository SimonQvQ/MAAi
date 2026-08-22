# MAAi — iOS 版明日方舟小助手（Docker 架构）

> MAA-Meow 的 iOS 版。大脑跑在 Docker（MaaFramework + MXU），
> iPhone 里的 dylib 只当 **眼睛/手/表情包**：截图、触摸、游戏内小浮层。

架构:

    [浏览器] 打开 MXU 选择任务
       |
       v
    [Docker maai-server: MXU + MaaFramework(Linux)]   <- 便捷协议 JSON-over-TCP :17171
       |                          ^
       | SCREENCAP/触摸            | 截图流/状态事件
       v                          |
    MaaFramework 决策        [iPhone 明日方舟进程]
                            MAAiAgent.dylib: 截图 + 触摸注入 + 浮层(连接状态/当前操作)

## 快速开始

1. Docker 侧（大脑）:
     cd maai-server
     MAAFW_URL=... MXU_URL=... ./setup.sh      # 下载 MaaFramework linux 包 + MXU 单文件
     # 把明日方舟资源包放 resource/，编写 interface.json(PI V2)
     docker compose up -d --build
2. iPhone 侧（MAAiAgent.dylib）: 构建后注入明日方舟（见 Scripts/inject.sh 模板），
   CI 的 agent-dylib job 会交叉编译并上传 libMAAiAgent.dylib 产物，可下载后直接注入。
   设置 MAAI_SERVER_HOST（Docker 主机 IP）、MAAI_SERVER_PORT（默认 17171）。
   dylib 自动拨号连接，游戏顶部出现小浮层显示连接状态与当前操作。
3. 访问 MXU（VNC :5800 或 MXU 自身方式），选任务开跑。

## 便捷协议（MAAi Agent Channel）

4 字节大端长度 + UTF-8 JSON（max 16MB）。线格式实现:
    C++ :  MaaRuntime/src/core/ipc_message.h
    Python: maai-server/bridge/agent_bridge.py

- 服务器 -> agent 命令: SCREENCAP(format=jpeg|raw) CLICK SWIPE TOUCH_DOWN/MOVE/UP
                       PRESS_KEY INPUT_TEXT DISPLAY(浮层文本) SET_STREAM SET_TOUCH
                       SET_OVERLAY STATUS PING
- agent -> 服务器事件: STATUS(连接即上报) SCREENSHOT(流) LOG；请求均回 response

## 仓库布局

    maai-server/    Docker 大脑：MXU + MaaFramework(Linux) + bridge + interface.json
    MaaRuntime/     核心(线格式/TCP Server+Client) + iOS MAAiAgent.dylib(截图/触摸/浮层)
    Scripts/        build_core / fetch_maameow_resources / inject 模板 / push_to_github
    .github/workflows/ CI：Linux core 测试 + macOS 交叉编译 dylib + Docker 镜像构建

## 已知边界

- 触摸注入用私有 API（_handleHIDEvent:），LiveContainer/沙盒可能被拒；失败会返回
  错误让流水线重试。
- MaaFramework 无官方 iOS 产物，核心放服务器（原生支持 Linux）。bridge 里把 agent
  包装成自定义控制器的部分（MaaFrameworkFFI）需按实际 SDK 头文件校准 v5/v4 差异。
- 延迟/带宽：截图从 iPhone 传到服务器（Wi-Fi 1080p/5fps 约几百 KB/s），4G 建议降帧率。
