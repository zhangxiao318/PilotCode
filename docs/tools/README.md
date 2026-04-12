# PilotCode 工具文档

本目录包含 PilotCode 核心工具的详细说明。

## 工具分类

### 文件操作
| 工具 | 说明 | 文档 |
|------|------|------|
| **FileRead** | 读取文件内容 | [fileread.md](fileread.md) |
| **FileWrite** | 写入文件 | [filewrite.md](filewrite.md) |
| **FileEdit** | 编辑文件 | [fileedit.md](fileedit.md) |

### Shell 执行
| 工具 | 说明 | 文档 |
|------|------|------|
| **Bash** | 执行 Bash 命令 | [bash.md](bash.md) |
| **PowerShell** | 执行 PowerShell 命令 | [powershell.md](powershell.md) |

### 代码搜索与索引
| 工具 | 说明 | 文档 |
|------|------|------|
| **CodeIndex** | 代码库索引 | [codeindex.md](codeindex.md) |
| **CodeSearch** | 智能代码搜索 | [codesearch.md](codesearch.md) |
| **CodeContext** | 代码上下文构建 | [codecontext.md](codecontext.md) |
| **Grep** | 文本搜索 | [grep.md](grep.md) |
| **Glob** | 文件匹配 | [glob.md](glob.md) |

### Web 工具
| 工具 | 说明 | 文档 |
|------|------|------|
| **WebSearch** | 网页搜索 | [websearch.md](websearch.md) |
| **WebFetch** | 获取网页内容 | [webfetch.md](webfetch.md) |

### 开发工具
| 工具 | 说明 | 文档 |
|------|------|------|
| **LSP** | 语言服务器协议 | [lsp.md](lsp.md) |
| **Git** | Git 操作 | [git.md](git.md) |
| **Agent** | 子 Agent | [agent.md](agent.md) |
| **Task** | 任务管理 | [task.md](task.md) |
| **Todo** | 待办事项 | [todo.md](todo.md) |

## 快速参考

### 文件操作
```python
# 读取文件
FileRead(path="src/main.py")

# 写入文件
FileWrite(path="output.txt", content="Hello")

# 编辑文件
FileEdit(path="main.py", old_string="def old():", new_string="def new():")
```

### 代码搜索
```python
# 索引代码库
CodeIndex(action="index")

# 语义搜索
CodeSearch(query="authentication", search_type="semantic")

# 符号搜索
CodeSearch(query="UserModel", search_type="symbol")

# 文本搜索
Grep(pattern="TODO", path="src/")
```

### Shell 执行
```python
# 执行命令
Bash(command="ls -la")

# 执行并捕获输出
Bash(command="python test.py")
```

## 工具使用原则

1. **优先使用专用工具**：如 `/search` 比 `Grep` 更高效（已索引时）
2. **组合使用**：先用 `Glob` 找文件，再用 `FileRead` 读取
3. **注意权限**：部分工具需要用户确认（如 `Bash` 的写入操作）
4. **错误处理**：工具返回结果中包含 `error` 字段

## 添加新工具

参考 [../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) 的"扩展点"章节。

## 相关文档

- [../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) - 架构文档
- [../commands/README.md](../commands/README.md) - 命令文档