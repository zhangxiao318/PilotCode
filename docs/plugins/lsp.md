# LSP - 语言服务器协议集成

LSP 模块提供 Language Server Protocol 支持，允许插件集成各种语言的 LSP 服务器，提供代码补全、跳转定义、悬停提示等功能。

---

## 模块结构

```
src/pilotcode/plugins/lsp/
├── __init__.py              # 模块导出
├── manager.py               # LSPManager
├── client.py                # LspClient
└── types.py                 # 类型定义
```

---

## LSPManager

LSP 管理器负责管理多个语言服务器。

### 获取管理器

```python
from pilotcode.plugins.lsp.manager import get_lsp_manager

manager = get_lsp_manager()
```

### 启动服务器

```python
from pilotcode.plugins.lsp.types import LspServerConfig

config = LspServerConfig(
    command="python",
    args=["-m", "pylsp"],
    extensionToLanguage={
        ".py": "python",
        ".pyi": "python"
    }
)

server = await manager.start_server("python-lsp", config)
```

### 停止服务器

```python
# 停止单个服务器
await manager.stop_server("python-lsp")

# 停止所有服务器
await manager.stop_all()
```

### 重启服务器

```python
server = await manager.restart_server("python-lsp")
```

### 获取服务器

```python
# 通过名称获取
server = manager.get_server("python-lsp")

# 通过文件路径获取
server = manager.get_server_for_file("src/main.py")

# 通过语言 ID 获取
server = manager.get_server_for_language("python")

# 列出所有服务器
servers = manager.list_servers()
```

---

## LSP 操作

### 文件操作

```python
# 打开文件
await manager.did_open(
    file_path="src/main.py",
    text="print('hello')"
)

# 文件修改
await manager.did_change(
    file_path="src/main.py",
    version=2,
    changes=[{
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 5}
        },
        "text": "console"
    }]
)
```

### 代码补全

```python
completions = await manager.get_completions(
    file_path="src/main.py",
    line=10,
    character=15
)

for item in completions:
    print(f"{item.label}: {item.detail}")
```

### 悬停提示

```python
hover = await manager.get_hover(
    file_path="src/main.py",
    line=10,
    character=15
)

if hover:
    print(hover.contents.value)
```

### 跳转到定义

```python
locations = await manager.go_to_definition(
    file_path="src/main.py",
    line=10,
    character=15
)

for loc in locations:
    print(f"{loc.uri}: {loc.range.start.line}")
```

### 格式化文档

```python
edits = await manager.format_document("src/main.py")

for edit in edits:
    print(f"Range: {edit.range}")
    print(f"New text: {edit.new_text}")
```

---

## 类型定义

### LspServerConfig

```python
from pilotcode.plugins.lsp.types import LspServerConfig

config = LspServerConfig(
    command="node",
    args=["/path/to/server.js"],
    env={"NODE_ENV": "production"},
    extensionToLanguage={
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact"
    }
)
```

### LspServer

```python
from pilotcode.plugins.lsp.types import LspServer

server = LspServer(
    name="typescript-lsp",
    config=config,
    client=lsp_client,
    initialized=True
)

# 获取文件的语言 ID
lang = server.get_language_for_file("src/main.ts")  # "typescript"
```

---

## LspClient

底层 LSP 客户端，提供原始 LSP 协议支持。

```python
from pilotcode.plugins.lsp.client import LspClient
from pilotcode.plugins.lsp.types import LspServerConfig

config = LspServerConfig(
    command="python",
    args=["-m", "pylsp"],
    extensionToLanguage={".py": "python"}
)

client = LspClient(config)

# 启动
success = await client.start()

# 初始化
await client.initialize(
    root_path="/path/to/project",
    capabilities={"textDocument": {"completion": {"dynamicRegistration": True}}}
)

# 打开文档
await client.textDocument_didOpen(
    uri="file:///path/to/file.py",
    language_id="python",
    version=1,
    text="print('hello')"
)

# 获取补全
completions = await client.textDocument_completion(
    uri="file:///path/to/file.py",
    line=0,
    character=5
)

# 停止
await client.stop()
```

---

## 插件集成

### 加载插件的 LSP 服务器

```python
# 插件提供 LSP 配置
lsp_servers = {
    "python-lsp": LspServerConfig(
        command="python",
        args=["-m", "pylsp"],
        extensionToLanguage={".py": "python"}
    ),
    "typescript-lsp": LspServerConfig(
        command="typescript-language-server",
        args=["--stdio"],
        extensionToLanguage={
            ".ts": "typescript",
            ".tsx": "typescriptreact"
        }
    )
}

# 加载所有服务器
results = await manager.load_plugin_servers(lsp_servers)
# Returns: {"python-lsp": True, "typescript-lsp": False}
```

### 插件配置示例

```json
{
  "name": "python-plugin",
  "lspServers": {
    "python-lsp": {
      "command": "python",
      "args": ["-m", "pylsp"],
      "env": {},
      "extensionToLanguage": {
        ".py": "python",
        ".pyi": "python"
      }
    }
  }
}
```

---

## 常见 LSP 服务器

### Python

```python
config = LspServerConfig(
    command="python",
    args=["-m", "pylsp"],
    extensionToLanguage={".py": "python", ".pyi": "python"}
)
```

或

```python
config = LspServerConfig(
    command="pyright-langserver",
    args=["--stdio"],
    extensionToLanguage={".py": "python"}
)
```

### TypeScript/JavaScript

```python
config = LspServerConfig(
    command="typescript-language-server",
    args=["--stdio"],
    extensionToLanguage={
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".js": "javascript",
        ".jsx": "javascriptreact"
    }
)
```

### Rust

```python
config = LspServerConfig(
    command="rust-analyzer",
    args=[],
    extensionToLanguage={".rs": "rust"}
)
```

### Go

```python
config = LspServerConfig(
    command="gopls",
    args=[],
    extensionToLanguage={".go": "go"}
)
```

### C/C++

```python
config = LspServerConfig(
    command="clangd",
    args=["--background-index"],
    extensionToLanguage={
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp"
    }
)
```

---

## 完整示例

### 智能代码补全

```python
import asyncio
from pilotcode.plugins.lsp.manager import get_lsp_manager
from pilotcode.plugins.lsp.types import LspServerConfig

async def setup_completion():
    manager = get_lsp_manager()
    
    # 启动 Python LSP
    config = LspServerConfig(
        command="python",
        args=["-m", "pylsp"],
        extensionToLanguage={".py": "python"}
    )
    
    server = await manager.start_server("python", config)
    print(f"LSP server started: {server.name}")
    
    # 打开文件
    code = '''
import os
os.
'''
    await manager.did_open("test.py", code)
    
    # 获取补全（在 os. 后）
    completions = await manager.get_completions("test.py", line=2, character=3)
    
    print(f"Found {len(completions)} completions:")
    for item in completions[:10]:
        print(f"  - {item.label}: {item.detail}")
    
    # 清理
    await manager.stop_all()

if __name__ == "__main__":
    asyncio.run(setup_completion())
```

### 跳转到定义

```python
async def goto_definition():
    manager = get_lsp_manager()
    
    # 假设 LSP 已启动
    code = '''
def hello():
    return "world"

result = hello()
'''
    await manager.did_open("test.py", code)
    
    # 在 hello() 调用处获取定义
    locations = await manager.go_to_definition("test.py", line=4, character=10)
    
    for loc in locations:
        print(f"Definition at: {loc.uri}")
        print(f"Line: {loc.range.start.line}")
        print(f"Character: {loc.range.start.character}")

# asyncio.run(goto_definition())
```

### 悬停文档

```python
async def show_hover():
    manager = get_lsp_manager()
    
    code = '''
def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    return a + b

result = calculate_sum(1, 2)
'''
    await manager.did_open("test.py", code)
    
    # 在 calculate_sum 上获取悬停信息
    hover = await manager.get_hover("test.py", line=5, character=10)
    
    if hover:
        print("Hover information:")
        print(hover.contents.value)
```

---

## 错误处理

```python
from pilotcode.plugins.lsp.manager import LspError

try:
    server = await manager.start_server("python", config)
except LspError as e:
    print(f"Failed to start LSP server: {e}")

# 处理操作错误
try:
    completions = await manager.get_completions("file.py", 0, 0)
except Exception as e:
    print(f"Failed to get completions: {e}")
    completions = []
```

---

## 相关文档

- [插件核心管理](./core.md)
