# maai-server — Docker 大脑（MaaFramework Linux + MXU）

架构：**大脑在服务器，手机只当眼睛/手**。

```
[浏览器] 打开 MXU 网页选择要干什么
      │
      ▼
[Docker: MXU + MaaFramework(Linux)]
      │  ← MAAi 便捷协议(4字节大端+JSON, TCP 17171) ————►  [iPhone 明日方舟进程]
      ▼                                                      MAAiAgent.dylib:
   识别/决策/操作流                                            截图 → 服务器
                                                             触摸 ← 服务器
                                                             浮层:连接状态+当前操作
```

## 使用

1. 下载资源：
   ```bash
   MAAFW_URL=<MaaFramework linux 包直链> MXU_URL=<MXU linux 单文件直链> ./setup.sh
   ```
2. 放入明日方舟资源包到 `resource/`，按需编辑 `interface.json`（PI V2）
3. 启动：
   ```bash
   docker compose up -d --build
   ```
4. iPhone 上在明日方舟进程注入 MAAiAgent.dylib，设置 `MAAI_SERVER_HOST` 为 Docker 主机 IP
5. 浏览器打开 MXU（VNC :5800 可看桌面），选任务开跑

## 组件

| 文件 | 作用 |
| --- | --- |
| `bridge/agent_bridge.py` | 便捷协议最小实现：连 iPhone agent、请求截图/发触摸、接收 SCREENSHOT/STATUS 事件；并把 MaaFramework v5 自定义控制器用 ctypes 接上（TODO 按实际 SDK 校准） |
| `interface.json` | PI V2 项目定义（MXU 解析） |
| `Dockerfile`/compose | xvfb 跑无头 MXU + bridge |

## 说明

- MXU 是桌面 Tauri 应用，Docker 里用 xvfb 无头运行；界面通过 VNC(:5800) 或后续 web 化访问。
- 图片从 iPhone → 服务器，Wi-Fi 下约几百 KB/s（1080p/5fps）；4G 建议降 fps/画质。
- `bridge/agent_bridge.py` 中 `MaaFrameworkFFI` 部分需要按你实际下载的 MaaFramework 头文件逐符号校准（v5 与 v4 C API 有差异，库中注释了 TODO）。
