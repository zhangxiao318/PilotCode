# SessionService MVC 架构

> **状态**: ✅ 核心已完成（TUI/SimpleCLI 已迁移，Web 部分迁移）
> **关联改进项**: 提取共用 Controller，消除 3 个 UI 中的重复业务逻辑
> **适用场景**: 所有 UI 模式（SimpleCLI / TUI v2 / Web）

---

## 1. 背景与问题

PilotCode 支持三种用户界面：

- **SimpleCLI**：纯文本终端（`print`/`input`）
- **TUI v2**：基于 Textual 的富文本终端界面
- **Web UI**：基于 WebSocket 的浏览器界面

重构前，每个 UI 都各自维护了一套完整的业务逻辑：

- QueryEngine 初始化与配置
- 主查询循环（流式读取 → 工具调用 → 编译验证）
- 上下文压缩触发
- 命令解析与分发
- 权限请求处理
- 会话持久化（自动保存/恢复）
- FileEdit 补偿追踪

这导致：
1. **重复代码**：同样的逻辑在 3 个文件中各写一遍，约 800–1000 行重复
2. **维护困难**：一个 bug 需修 3 处，一个功能需写 3 遍
3. **能力不均**：SimpleCLI 有上下文压缩，TUI 早期缺失；TUI 有 P-EVR，Web 缺失
4. **新增 UI 成本高**：接入新界面需复制上千行业务逻辑

---

## 2. 核心设计

将共用业务逻辑提取为 **SessionService**（Model/Service 层），通过 **UIProtocol** 三通道接口与任意 View 通信。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              View 层                                     │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  SimpleCLI  │  │  TUI SessionScreen│  │   WebServer     │             │
│  └──────┬──────┘  └────────┬────────┘  └────────┬────────┘             │
│         │                  │                     │                      │
│         ▼                  ▼                     ▼                      │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │SimpleCLIProt│  │   TUIProtocol   │  │WebSocketProtocol│             │
│  │  (Adapter)  │  │    (Adapter)    │  │    (Adapter)    │             │
│  └──────┬──────┘  └────────┬────────┘  └────────┬────────┘             │
│         │                  │                     │                      │
│         └──────────────────┼─────────────────────┘                      │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │   UIProtocol    │  ← 三通道接口契约                   │
│                   │   (Protocol)    │                                   │
│                   └────────┬────────┘                                   │
│                            │                                            │
└────────────────────────────┼────────────────────────────────────────────┘
                             ▼
                   ┌─────────────────┐
                   │  SessionService │  ← 核心 Service/Controller
                   │   (1424 行)     │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   QueryEngine   │  ← 底层 LLM 引擎
                   └─────────────────┘
```

### 2.1 三层职责

| 层 | 组件 | 职责 |
|----|------|------|
| **Model / Service** | `SessionService` | 统管所有业务逻辑：QueryEngine 初始化、会话生命周期、主查询循环、工具执行、编译验证、上下文压缩、命令分发、权限管理、自动保存 |
| **View** | `SimpleCLI` / `SessionScreen` / `WebServer` | 用户界面渲染与输入捕获 |
| **Controller (Adapter)** | `SimpleCLIProtocol` / `TUIProtocol` / `WebSocketProtocol` | 将 `UIProtocol` 事件转换为 View 特定的渲染/交互形式 |

### 2.2 UIProtocol 三通道设计

定义在 `src/pilotcode/ui/protocol.py`。

#### Channel 1: Block Events（内容流）

```python
class BlockKind(str, Enum):
    ASSISTANT = "assistant"      # LLM 流式响应
    THINKING = "thinking"        # 推理内容（DeepSeek/Qwen3）
    TOOL_CALL = "tool_call"      # 工具调用开始
    TOOL_RESULT = "tool_result"  # 工具执行结果
    SYSTEM = "system"            # 系统通知/警告
    PLAN_PROGRESS = "plan_progress"

class BlockPhase(str, Enum):
    OPEN = "open"    # 块开始
    DELTA = "delta"  # 增量更新
    CLOSE = "close"  # 块结束
```

每个 `block_id` 在 open/delta/close 之间保持一致，View 可据此实现增量更新或替换。

#### Channel 2: Status Updates（状态栏）

```python
@dataclass
class StatusUpdate:
    token_count: int = 0
    context_window: int = 0
    is_processing: bool = False
    model_name: str = ""
    thinking_mode: bool = False
```

- **SimpleCLI**：忽略（无状态栏）
- **TUI v2**：映射到 `StatusBar` 组件
- **Web**：映射为 `{"type": "context_usage", ...}` JSON

#### Channel 3: Interactive Requests（用户交互）

```python
async def request_permission(tool_name, params, risk_level) -> PermissionResult
async def request_user_input(question, options=None) -> str
```

- **SimpleCLI**：阻塞 `input()` `[Y/n]`
- **TUI v2**：内联 `InlinePermissionRequest` 异步组件
- **Web**：WebSocket `permission_request` → `permission_result` 往返，通过 `asyncio.Future` 实现

---

## 3. 重构收益

### 3.1 代码量变化

| 文件 | 重构前 | 重构后 | 变化 |
|------|--------|--------|------|
| `session_service.py` | — | **1,424 行** | 新增（共用逻辑） |
| `tui_v2/controller/controller.py` | **1,264 行** | **~730 行** | -534 行（-42%） |
| `tui/simple_cli.py` | **1,093 行** | **~438 行** | -655 行（-60%） |

> 对应提交：`49c8429 refactor(tui_v2): rewrite TUIController to use SessionService`  
> 对应提交：`d6dd4d0 refactor(tui): rewrite SimpleCLI to use SessionService`

### 3.2 职责分离对比

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| **业务逻辑位置** | 分散在 3 个 UI 文件，各 ~250–300 行重复 | 集中在 `SessionService` 一处 |
| **QueryEngine 初始化** | 每个 UI 自己实现 | `SessionService._init_engine()` 统一处理 |
| **主查询循环** | 3 处重复实现流式读取、工具调用、编译检查 | `SessionService.process_query()` 一处 |
| **上下文压缩** | 只在 SimpleCLI 中有，TUI/Web 缺失 | `SessionService` 统一处理 |
| **新增 UI 成本** | 需复制 ~1000 行业务逻辑 | 只需实现 `UIProtocol`（约 100 行 Adapter） |

### 3.3 新增 UI 的接入成本

重构后，新增一个 UI（如 VS Code 插件、桌面 GUI）只需：

1. 实现 `UIProtocol` 接口（约 100 行）
2. 创建 `SessionService(ui=your_protocol, config=session_config, ...)`
3. 调用 `service.process_query(text)`

无需再实现：QueryEngine 初始化、工具执行循环、编译验证、上下文压缩、命令分发、自动保存等。

---

## 4. SessionService 核心功能

SessionService 替代了原先分散在 3 个 UI 中的以下职责：

| 功能 | 方法 | 原先重复位置 |
|------|------|-------------|
| QueryEngine 初始化 | `_init_engine()` | `simple_cli.py`, `controller.py`, `server.py` |
| 会话创建/恢复 | `_init_session()` | `simple_cli.py`, `controller.py` |
| 主查询循环 | `process_query()` | 三处各 ~300 行 |
| 工具执行 | `_execute_tools()` | 三处各 ~150 行 |
| 编译验证 | `_verify_compilation()` | `simple_cli.py`, `controller.py` |
| 上下文压缩 | `_check_and_compress_context()` | `simple_cli.py` |
| 命令分发 | `handle_command()` | 三处各 ~200 行 |
| 权限管理 | 统一逻辑 + `UIProtocol.request_permission` | 各 UI 自行实现 |
| 自动保存 | `_auto_save()` | 三处重复 |
| CWD 检测与更新 | `_detect_and_update_cwd()` | `controller.py` |

---

## 5. Web UI 的特殊情况

Web UI 目前是 **部分迁移**（`src/pilotcode/web/server.py` 顶部注释明确说明）：

> *"Partially refactored for MVC: SessionService integration is available through WebSocketProtocol, but the main process_query function still uses the legacy approach due to the multi-session architecture."*

`WebSocketProtocol` 已经实现，但主流程尚未切到 `SessionService.process_query()`，原因是 Web 端的多会话架构（`WebSocketManager._session_contexts`）与 SessionService 的单会话模型需要进一步适配。

---

## 6. 与旧四层模型的关系

`src/pilotcode/ui/layers.py` 中的旧四层显示模型已标记为 **deprecated**，其映射关系如下：

| 旧四层模型 | 新三通道 |
|-----------|---------|
| `CONVERSATIONAL` | Channel 1 (`ASSISTANT/THINKING/TOOL_CALL/TOOL_RESULT`) |
| `SYSTEM` | Channel 1 (`kind=SYSTEM`) |
| `STATUS` | Channel 2 (`on_status_update`) |
| `INTERACTIVE` | Channel 3 (`request_permission` / `request_user_input`) |

---

## 7. 相关文件

### 核心 MVC 框架

| 文件 | 说明 |
|------|------|
| `src/pilotcode/ui/protocol.py` | **UIProtocol 三通道接口**、BlockEvent/StatusUpdate/PermissionResult |
| `src/pilotcode/ui/config.py` | **SessionConfig**（反应式配置） |
| `src/pilotcode/ui/session_service.py` | **SessionService**（共享 Controller，1,424 行） |
| `src/pilotcode/ui/layers.py` | 旧四层显示模型（deprecated） |

### View 实现

| 文件 | 说明 |
|------|------|
| `src/pilotcode/tui/simple_cli.py` | SimpleCLI + SimpleCLIProtocol（纯文本终端） |
| `src/pilotcode/tui_v2/controller/controller.py` | TUIController + TUIProtocol（Textual TUI） |
| `src/pilotcode/tui_v2/screens/session.py` | SessionScreen（Textual 主界面） |
| `src/pilotcode/web/server.py` | WebServer + WebSocketProtocol（Web UI，部分迁移） |

### 测试

| 文件 | 说明 |
|------|------|
| `tests/test_session_service.py` | SessionService 单元测试：MockUIProtocol、BlockEvent、命令处理 |
