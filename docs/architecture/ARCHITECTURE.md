# PilotCode Python - Architecture

This document describes the architecture of the Python rewrite of Claude Code, mapping TypeScript concepts to Python implementations.

## Directory Structure

```
pilotcode_py/
├── src/pilotcode/           # Main source code
│   ├── types/                # Type definitions (Pydantic models)
│   ├── tools/                # Tool implementations
│   ├── commands/             # Slash command implementations
│   ├── components/           # TUI components
│   ├── state/                # State management
│   ├── utils/                # Utility functions
│   ├── services/             # External services (MCP, API)
│   ├── context/              # Application context
│   ├── cli.py                # CLI entry point
│   ├── main.py               # Main module
│   └── query_engine.py       # Query engine
├── src/tests/                # Test files
├── config/                   # Configuration templates
├── pyproject.toml            # Project configuration
└── requirements.txt          # Dependencies
```

## TypeScript to Python Mapping

### Types

| TypeScript | Python |
|------------|--------|
| `type X = Y` | `TypeAlias = Y` |
| `interface X { }` | `class X(BaseModel)` or `@dataclass` |
| `string` | `str` |
| `number` | `int` / `float` |
| `boolean` | `bool` |
| `undefined` | `None` |
| `null` | `None` |
| `X \| Y` (union) | `X \| Y` (Python 3.10+) |
| `Array<X>` | `list[X]` |
| `Record<K, V>` | `dict[K, V]` |
| `Promise<T>` | `Awaitable[T]` or coroutine |
| `async function` | `async def` |
| `export type` | Type alias with `__all__` export |

### Core Components

#### Tool System

**TypeScript (`src/Tool.ts`)**:
```typescript
type Tool<Input, Output, Progress> = {
  name: string
  description: string | (input, options) => Promise<string>
  inputSchema: z.ZodType<Input>
  call: (input, context, canUseTool, ...) => Promise<ToolResult<Output>>
  isReadOnly: (input) => boolean
  isConcurrencySafe: (input) => boolean
  // ...
}
```

**Python (`src/pilotcode/tools/base.py`)**:
```python
class Tool:
    def __init__(
        self,
        name: str,
        description: str | Callable[[Input, dict], Awaitable[str]],
        input_schema: type[BaseModel],
        call: ToolCallFn,
        is_read_only: Callable[[Input], bool],
        is_concurrency_safe: Callable[[Input], bool],
        # ...
    )
```

#### State Management

**TypeScript**: Uses React Context + Zustand-like store
**Python**: Custom `Store` class with subscriber pattern

```python
class Store:
    def get_state(self) -> AppState
    def set_state(self, updater: Callable[[AppState], AppState]) -> None
    def subscribe(self, listener: Callable[[AppState], None]) -> Callable
```

#### Query Engine

**TypeScript**: `QueryEngine.ts` + `query.ts`
**Python**: `query_engine.py` with async generators

```python
class QueryEngine:
    async def submit_message(
        self, prompt: str, options: dict
    ) -> AsyncIterator[QueryResult]:
        # Streams messages and tool results
```

#### Configuration

**TypeScript**: `utils/config.ts`
**Python**: `utils/config.py` using `platformdirs` and Pydantic

### Tools Implemented

| Tool | TypeScript | Python | Status |
|------|------------|--------|--------|
| BashTool | `tools/BashTool/BashTool.tsx` | `tools/bash_tool.py` | ✅ |
| FileReadTool | `tools/FileReadTool/FileReadTool.ts` | `tools/file_read_tool.py` | ✅ |
| FileWriteTool | `tools/FileWriteTool/FileWriteTool.ts` | `tools/file_write_tool.py` | ✅ |
| FileEditTool | `tools/FileEditTool/FileEditTool.ts` | `tools/file_edit_tool.py` | ✅ |
| GlobTool | `tools/GlobTool/GlobTool.ts` | `tools/glob_tool.py` | ✅ |
| GrepTool | `tools/GrepTool/GrepTool.ts` | `tools/grep_tool.py` | ✅ |
| AskUserQuestionTool | `tools/AskUserQuestionTool/...` | `tools/ask_user_tool.py` | ✅ |
| TodoWriteTool | `tools/TodoWriteTool/...` | `tools/todo_tool.py` | ✅ |
| WebSearchTool | `tools/WebSearchTool/...` | `tools/web_search_tool.py` | ✅ |
| WebFetchTool | `tools/WebFetchTool/...` | `tools/web_fetch_tool.py` | ✅ |

### Commands

**TypeScript**: `commands.ts` + `commands/` directory
**Python**: `commands/base.py` with command registry

### TUI

**TypeScript**: Ink (React for Terminal)
**Python**: Rich + Prompt Toolkit

Components:
- `REPL` - Main interactive loop (replaces `App.tsx`)
- Rich `Panel` for layout (replaces Ink components)
- `PromptSession` for input (replaces custom input handling)
- `Live` display for streaming output

### LLM Client

**TypeScript**: Anthropic SDK
**Python**: Custom client using `httpx` with OpenAI-compatible API

Configuration from `openclaw.json`:
```json
{
  "models": {
    "local": {
      "baseUrl": "http://172.19.201.40:3509/v1",
      "apiKey": "sk-..."
    }
  }
}
```

Mapped to Python `utils/model_client.py`.

## Key Design Decisions

### 1. Type Safety
- Use Pydantic for data validation (equivalent to Zod in TypeScript)
- Use dataclasses for simple structures
- Type hints throughout (mypy compatible)

### 2. Concurrency
- Use `asyncio` for async operations (equivalent to JavaScript promises)
- Tool execution supports concurrent read-only operations
- Async generators for streaming responses

### 3. Tool Registration
- Tools self-register on import
- Global registry pattern similar to TypeScript
- Support for aliases

### 4. Error Handling
- Use exceptions (Pythonic) instead of Result types
- Tool results include error field for graceful degradation

### 5. State Management
- Simpler than React - no hooks needed
- Direct state access through store
- Subscription pattern for UI updates

## Running the Application

### Development
```bash
cd /home/zx/mycc/pilotcode_py
python3 demo.py  # Run demo
```

### Installation
```bash
./install.sh  # Creates venv and installs dependencies
```

### Usage
```bash
./pilotcode.sh        # Run with shell script (Linux/macOS)
.\pilotcode.cmd       # Run with batch script (Windows)
python3 -m pilotcode main  # Run as module
```

## Testing

```bash
python3 run_tests.py  # Run all tests
pytest src/tests/     # Using pytest directly
```

## Future Enhancements

1. **More Tools**: AgentTool, LSPTool, NotebookEditTool, etc.
2. **Skills System**: Load custom skills from directories
3. **Advanced TUI**: More sophisticated terminal UI with Textual
4. **MCP Full Support**: Complete MCP client implementation
5. **Permissions**: Full permission system with UI prompts
6. **Context Compaction**: Auto-compact long conversations
7. **Background Tasks**: Support for background agent execution
8. **Sessions**: Save and resume sessions
