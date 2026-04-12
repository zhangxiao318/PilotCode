# FileRead 工具

读取文件内容，支持分页和行范围选择。

## 作用

- 读取文本文件内容
- 查看代码文件
- 读取配置文件
- 支持大文件分页读取

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `path` | string | ✅ | 文件路径 |
| `offset` | integer | ❌ | 起始行号（从1开始） |
| `limit` | integer | ❌ | 读取行数限制 |

## 使用示例

### 读取整个文件

```python
FileRead(path="src/main.py")
```

### 读取前50行

```python
FileRead(path="src/main.py", limit=50)
```

### 读取特定行范围

```python
# 读取第100-150行
FileRead(path="src/main.py", offset=100, limit=50)
```

### 读取配置文件

```python
FileRead(path="config/settings.json")
FileRead(path="pyproject.toml")
```

## 使用场景

### 场景1：查看代码文件

```python
# 查看主入口文件
FileRead(path="src/main.py")

# 查看工具实现
FileRead(path="src/pilotcode/tools/bash_tool.py")
```

### 场景2：读取大文件时分页

```python
# 先读取前100行
FileRead(path="large_file.log", limit=100)

# 继续读取更多
FileRead(path="large_file.log", offset=101, limit=100)
```

### 场景3：查看特定函数

```python
# 先用 Grep 找到行号
Grep(pattern="def process_data", path="src/", output_mode="content")

# 然后读取该区域
FileRead(path="src/utils.py", offset=45, limit=20)
```

## 输出格式

```
/src/pilotcode/tools/bash_tool.py
═══════════════════════════════════
   1 │ """Bash tool for executing shell commands."""
   2 │ 
   3 │ import asyncio
   4 │ from pathlib import Path
   5 │ ...
```

## 错误处理

| 错误 | 说明 | 解决 |
|------|------|------|
| File not found | 文件不存在 | 检查路径 |
| Permission denied | 无权限 | 检查文件权限 |
| Binary file | 二进制文件 | 使用其他工具 |

## 注意事项

1. **默认读取整个文件**：小文件可以直接读取
2. **大文件分页**：超过 200 行建议分页读取
3. **路径支持**：支持相对路径和绝对路径
4. **编码**：自动检测文件编码（UTF-8/GBK等）

## 相关工具

- **FileWrite** - 写入文件
- **FileEdit** - 编辑文件
- **Grep** - 搜索文本定位行号
- **Glob** - 查找文件