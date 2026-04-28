# 四层显示框架（Display Layer Framework）

PilotCode 支持多种 UI 模式：REPL、Simple CLI、TUI v2、Web。为了避免各 UI 各自为战、输出逻辑散落各处，我们引入了一套统一的**四层显示框架**，让所有 UI 按同一套语义分层渲染信息。

---

## 为什么需要四层框架

在重构之前，各 UI 的输出逻辑是完全独立的：

| UI 模式 | 助手回复 | 工具通知 | 系统警告 | 状态展示 |
|---------|---------|---------|---------|---------|
| REPL | `console.print(Markdown(...))` | `console.print("[dim][T] ...")` | `console.print("[yellow]...")` | ❌ 无 |
| Simple CLI | `print("📝 Response:")` | `print("🔧 Tool...")` | `print("⚠️ ...")` | ❌ 无 |
| TUI v2 | `yield UIMessage(ASSISTANT, ...)` | `yield UIMessage(TOOL_USE, ...)` | `yield UIMessage(SYSTEM, ...)` | StatusBar widget |
| Web | `send_to_client({type:"streaming_chunk"})` | `send_to_client({type:"tool_call"})` | `send_to_client({type:"system"})` | ❌ 无 |

问题很明显：
- **同样的语义，四种写法** — 新增功能时要在 4 个文件里各抄一遍
- **系统通知污染对话流** — Web 端曾把 `max_iterations` 提示伪装成 `streaming_chunk`
- **状态信息无处可放** — Token 用量、模型名称等没有统一的展示入口

---

## 四层架构

```
┌─────────────────────────────────────────────┐
│  1. Status Layer（状态层）                    │
│     - Token 使用量 / 上下文预算               │
│     - 当前模型、会话时长                      │
│     - Git 分支、工作目录                      │
│     - 渲染位置：顶部/底部状态栏               │
├─────────────────────────────────────────────┤
│  2. Conversational Layer（对话层）            │
│     - 用户输入                                │
│     - 助手回复（流式/完整）                   │
│     - 思考过程（thinking）                    │
│     - 工具调用请求、工具执行结果              │
│     - 渲染位置：时间轴聊天流                  │
├─────────────────────────────────────────────┤
│  3. System Layer（系统层）                    │
│     - 通知（上下文自动压缩完成）              │
│     - 警告（轮次即将耗尽、上下文超标）        │
│     - 错误（网络断开、执行异常）              │
│     - 进度（索引进度、规划进度）              │
│     - 渲染位置：横幅 / Toast / 系统消息       │
├─────────────────────────────────────────────┤
│  4. Interactive Layer（交互层）               │
│     - 权限请求（是否允许执行工具）            │
│     - 用户问题（多选一、确认框）              │
│     - 渲染位置：模态弹窗 / 内联提示           │
└─────────────────────────────────────────────┘
```

**核心原则：**
- **对话层**的消息会进入 LLM 的上下文历史（或用户可见的聊天记录）
- **系统层**的消息只展示给用户，**不进入** LLM 上下文
- **状态层**是持续可见的，不需要用户主动触发
- **交互层**会**阻塞**流程，等待用户输入

---

## 共享类型定义

源码：`src/pilotcode/ui/layers.py`

```python
class DisplayLayer(str, Enum):
    STATUS = "status"
    CONVERSATIONAL = "conversational"
    SYSTEM = "system"
    INTERACTIVE = "interactive"

@dataclass
class DisplayEvent:
    layer: DisplayLayer
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
```

工厂函数：
- `make_conversational(type, content, ...)` — 对话层事件
- `make_system(type, content, ...)` — 系统层事件
- `make_interactive(type, prompt, ...)` — 交互层事件
- `make_status(type, ...)` — 状态层事件

---

## 各 UI 模式的对应方法

### REPL（`src/pilotcode/components/repl.py`）

```python
class REPL:
    def _render_status(self, event_type: str, **kwargs) -> None:
        """状态层：目前为占位符，未来可接入底部状态栏。"""
        pass

    def _render_conversational_assistant(self, content: str, is_complete: bool) -> None:
        """对话层：助手回复，用 Markdown 渲染。"""
        self.console.print(Markdown(content))

    def _render_conversational_tool_use(self, tool_name, tool_input, iteration, max_iterations, ...) -> None:
        """对话层：工具调用通知。"""
        self.console.print(f"\n[dim][T] {tool_progress} {tool_name}[/dim]")

    def _render_conversational_tool_result(self, tool_name: str, success: bool, message: str) -> None:
        """对话层：工具执行结果。"""
        if success:
            self.console.print(f"[dim]✓ {tool_name} completed[/dim]")
        else:
            self.console.print(f"[red]✗ {message}[/red]")

    def _render_system(self, event_type: str, **payload) -> None:
        """系统层：委托给统一的 _notify_user。"""
        self._notify_user(event_type, payload)
```

REPL 的 `process_response()` 核心循环现在按层分段：
```python
while iteration < self.max_iterations:
    # -- Status Layer: processing spinner --
    with Status(status_text, console=self.console, spinner="dots"):
        async for result in self.query_engine.submit_message(prompt):
            # -- Conversational Layer --
            ...
    # -- System Layer: loop detection --
    ...
    # -- Interactive Layer: tool execution --
    ...
```

### Simple CLI（`src/pilotcode/tui/simple_cli.py`）

方法与 REPL 同名同语义，只是渲染载体从 `console.print` 换成了 `print`：

```python
def _render_conversational_assistant(self, content: str, is_complete: bool) -> None:
    print("📝 Response:")
    print(content)

def _render_conversational_tool_use(self, tool_name: str, tool_input: dict) -> None:
    print(f"🔧 Tool requested: {tool_name}({preview})")

def _render_system(self, event_type: str, **payload) -> None:
    if event_type == "max_iterations_reached":
        print(f"\n⏹️  Reached maximum tool iterations ...")
    elif event_type == "error":
        print(f"❌ Error: {payload['content']}")
```

### TUI v2（`src/pilotcode/tui_v2/controller/controller.py`）

TUI v2 的特殊之处在于它使用 `yield UIMessage` 生成器模式。`_render_*` 方法**返回** `UIMessage` 对象，由核心循环 `yield`：

```python
def _render_conversational_assistant(self, content: str, is_streaming: bool, is_complete: bool) -> UIMessage:
    return UIMessage(
        type=UIMessageType.ASSISTANT,
        content=content,
        is_streaming=is_streaming,
        is_complete=is_complete,
    )

def _render_conversational_tool_use(self, tool_name, tool_input, tool_use_id, iteration, tool_idx, total_tools) -> UIMessage:
    return UIMessage(
        type=UIMessageType.TOOL_USE,
        content=f"{tool_name}",
        metadata={"tool_name": tool_name, "tool_input": tool_input, ...},
    )

def _render_system(self, event_type: str, content: str = "", **kwargs) -> UIMessage:
    return UIMessage(type=UIMessageType.SYSTEM, content=content, is_complete=True)
```

核心循环：
```python
async for result in self.query_engine.submit_message(current_prompt):
    if isinstance(msg, AssistantMessage):
        yield self._render_conversational_assistant(accumulated_content, ...)
    elif isinstance(msg, ToolUseMessage):
        yield self._render_conversational_tool_use(msg.name, msg.input, ...)
```

### Web（`src/pilotcode/web/server.py`）

Web 端在 `process_query()` 内部定义了局部 `_render_*` 闭包，直接操作 `websocket` 和 `stream_id`：

```python
async def _render_conversational_chunk(chunk: str):
    await self.send_to_client(
        websocket, {"type": "streaming_chunk", "stream_id": stream_id, "chunk": chunk}
    )

async def _render_conversational_tool_call(tool_name: str, tool_input: dict):
    await self.send_to_client(
        websocket, {"type": "tool_call", "stream_id": stream_id, "tool_name": tool_name, ...}
    )

async def _render_system(content: str):
    await self.send_to_client(
        websocket, {"type": "system", "stream_id": stream_id, "content": content}
    )

async def _render_error(content: str):
    await self.send_to_client(
        websocket, {"type": "streaming_error", "stream_id": stream_id, "error": content}
    )
```

**重要修复：** `max_iterations` 耗尽时，Web 端不再把提示伪装成 `streaming_chunk`，而是走 `_render_system()`，前端收到 `type: "system"` 后可以渲染为横幅提示，不会污染模型输出。

---

## 如何扩展

### 添加新的系统通知

在 `QueryEngine` 中触发：
```python
if self.config.on_notify:
    self.config.on_notify("context_warning", {"usage_pct": 82})
```

在各 UI 的 `_render_system()` 中处理：
```python
def _render_system(self, event_type: str, **payload):
    if event_type == "context_warning":
        usage = payload["usage_pct"]
        # REPL
        self.console.print(f"[yellow]⚠️ Context at {usage}%[/yellow]")
        # Simple CLI
        print(f"⚠️ Context at {usage}%")
        # TUI v2
        yield UIMessage(type=SYSTEM, content=f"⚠️ Context at {usage}%")
        # Web
        await _render_system(f"⚠️ Context at {usage}%")
```

### 添加状态层展示

状态层目前为占位符。当 `StatusProvider` 实现后：

```python
def _render_status(self, event_type: str, **kwargs):
    if event_type == "token_update":
        self.status_bar.set_token_count(kwargs["tokens"])
```

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/pilotcode/ui/layers.py` | 共享类型：`DisplayLayer`, `DisplayEvent`, 工厂函数 |
| `src/pilotcode/components/repl.py` | REPL 渲染实现 |
| `src/pilotcode/tui/simple_cli.py` | Simple CLI 渲染实现 |
| `src/pilotcode/tui_v2/controller/controller.py` | TUI v2 渲染实现 |
| `src/pilotcode/web/server.py` | Web 渲染实现 |
