# MAAi 代码审查与优化报告

> 审查范围：`MaaRuntime`（C++ IPC 核心 + iOS Agent）与 `maai-server`（Python Bridge）
> 日期：2026-08-24
> 结果：发现并修复 **14 个问题**（4 个严重 bug），新增 5 场景回归测试，全部验证通过

---

## 一、严重 Bug（C++ IPC 核心，均已复现并验证修复）

### 1. 服务端客户端断开即崩溃
**位置**：`MaaRuntime/src/core/ipc_server.cpp` — `closeClient()`

`clientLoop` 在客户端断开时调用 `closeClient`，而它会 `join` 当前正在执行的线程自身 → 抛出 `system_error(resource_deadlock_would_occur)` → 未捕获 → `std::terminate` 终止整个进程。**任何一个客户端正常断开都会杀死整个 server。**

修复：改为 `detach()`。

### 2. 大帧丢失 + 流永久失步
**位置**：`MaaRuntime/src/core/ipc_server.cpp` — `clientLoop()`

旧代码对跨 `recv()` 边界的半帧直接丢弃（日志写着 "waiting for more data"，实际行为是丢弃）。协议允许 16MB 帧，base64 截图轻松超过 64KB 读缓冲，**必然丢帧且之后流永久错乱**。

修复：持久缓冲区逐帧解析。实测 300KB 帧拆成 4096B 分片发送：旧代码丢帧断言失败，新代码完整重组。

### 3. 客户端坏帧卡死 + 内存泄漏
**位置**：`MaaRuntime/src/core/ipc_client.cpp` — `receiveLoop()`

JSON 解析失败的帧永远卡在 `pending` 缓冲区头部，之后**所有消息收不到**、缓冲区无限增长。

修复：直接按长度前缀逐帧解析，坏帧跳过（实测坏帧后仍能连续收到后续帧）。

### 4. 服务端坏 JSON 帧毒化缓冲区（复查时在首轮修复代码中发现）
**位置**：`MaaRuntime/src/core/ipc_server.cpp` — `clientLoop()`

`decodeFrame` 返回 `false` 同时表示「半帧」和「JSON 解析失败的完整帧」。坏 JSON 帧会永远卡在缓冲区头部——后续好帧全部无法解析。另外超长帧头（如 `0xFFFFFFFF`）时缓冲区只有几字节，`buf.size() > 16MB` 的兜底**永远触发不了**，等于不设防。

修复：区分三种情况——半帧等待后续数据、坏帧按长度跳过（流可恢复）、非法帧长立即断开连接。

---

## 二、iOS 修复（`MAAiAgent.mm`）

| 问题 | 修复 |
|---|---|
| `stop()` 后幽灵重连：已调度的 3 秒重试不取消，停止后自动重连 | 增加 `_started` 标志，串行队列上检查 |
| raw 截图白做一次 JPEG 渲染后才丢弃 | 先判断格式再采集 |
| `respond:` 里 `ok ? "response" : "response"` 两分支相同 | 删除无意义三目 |

---

## 三、Python 修复（`bridge/` 与 `mwu/` 同步）

| 问题 | 修复 |
|---|---|
| 协议失步静默错乱：非法帧长时清空缓冲继续瞎解析，之后永远解不出帧 | 抛 `ProtocolError` → 断开让 agent 重连（实测生效） |
| `request()` 在 socket 已死时 `sendall` 裸抛异常，与超时返回 dict 的约定不一致 | 捕获 `OSError`，返回 `{"ok": False}` |
| `bind` 失败在 daemon 线程里裸抛堆栈 | 记录日志并返回 |
| `first_agent` 返回已断开的会话 | 只返回 `connected` 的会话 |
| webui 用 `getattr` 戳私有 `_lock` 绕路访问 server 内部 | 直接委托 `server.first_agent()`（-11 行） |
| `cv2` 每次 `screencap()` 都尝试 import | 模块级 try-import |
| `run_agent_task` 不检查 `post_connection` 结果，agent 已断仍加载资源 | 先校验，失败提前返回 |
| 未使用的 `import base64`/`dataclass`；`convert_maares.py` 重复的 `tasks/tasks.json` 特判；过时文档（声称支持 PIL 解码） | 清理 |

---

## 四、测试体系改进

**新增 `test_tcp_framing.cpp`**（177 行，5 场景，固化进 CI）：

1. 300KB 帧拆 4096B 分片 → 服务端完整重组
2. 坏 JSON 帧 → 服务端跳过且流不失步
3. 超长帧头（`0xFFFFFFFF`）→ 立即断开
4. 坏 JSON 帧 → TcpClient 跳过并收到后续帧
5. 客户端正常关闭（`recv=0` 路径）→ 服务端存活并回收会话（自 join 崩溃的原始触发路径）

**测试自身加固**：
- 修复数据竞争：`lastCmd` 跨线程读写改为 `atomic` 计数
- 所有测试加 `TIMEOUT 30`，挂起时快速失败（原 ctest 默认 1500s 会拖死 CI）
- 清理未使用 include

**其他统一**：16MB 帧上限原本在 3 个文件各写一遍魔法数字，收敛到 `ipc_message.h` 的 `kMaxFrameBytes`。

---

## 五、验证结果

| 验证项 | 结果 |
|---|---|
| C++ 单元 + 回归测试（ctest，3 个测试） | 全部通过 |
| `test_tcp_framing` 连续 5 次运行 | 全部通过（无抖动） |
| 旧代码对照实验（git stash 后跑同场景） | 场景 1 即断言失败，证实 bug 真实 |
| Python `py_compile`（6 个文件） | 通过 |
| Python 端到端冒烟：帧编解码单测 / 真实 socket 请求往返 / 失步断开 / bind 冲突 / 断开会话过滤 | 全部通过 |
| `convert_maares` 转换逻辑（`tasks/` 布局 + 动作映射 + 引用清理） | 通过 |

---

## 六、提交记录

| 提交 | 内容 |
|---|---|
| `25ffda9` | 第一轮：3 个 C++ 严重 bug、iOS 3 项、Python 7 项（11 文件） |
| `8bec059` | 第二轮：服务端坏帧毒化 + 超长帧头不设防、新增分帧回归测试、`post_connection` 校验（5 文件） |
| `81fb4f8` | 第三轮：测试加固（数据竞争修复、正常断开路径、TIMEOUT） |

合计 **13 个文件，+344 / -99 行**。

---

## 七、遗留事项（评估后判断可接受，未改动）

1. **`TcpClient::send` 与接收线程对 `fd_` 的理论竞态**：由于 ObjC 层每次重连都新建 `TcpClient` 对象，fd 复用错发场景实际不会发生，最坏情况是 `EBADF` 返回 false，无害。
2. **`bridge/` 与 `mwu/` 的代码重复**：有意为之——mwu 文件要被 `patch_backend.py` 单独拷贝进 MWU 仓库，必须自包含，不建议合并。
3. **`TcpServer::stop()` 与 `closeClient` 的线程回收顺序**：依赖 `detach` + shutdown 唤醒，当前规模（≤8 客户端）下无问题；若未来客户端数量级增长需重构为事件驱动。
