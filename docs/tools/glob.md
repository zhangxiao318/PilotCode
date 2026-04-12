# Glob 工具

文件模式匹配工具。

## 作用

- 查找匹配模式的文件
- 批量选择文件
- 项目结构浏览

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | ✅ | 文件模式 |
| `path` | string | ❌ | 搜索路径 |

## 模式语法

| 模式 | 说明 | 示例 |
|------|------|------|
| `*` | 匹配任意字符 | `*.py` |
| `**` | 递归匹配 | `src/**/*.py` |
| `?` | 匹配单个字符 | `file?.txt` |
| `[abc]` | 匹配括号内字符 | `file[0-9].txt` |

## 使用示例

### 查找 Python 文件

```python
Glob(pattern="*.py")
Glob(pattern="src/**/*.py")
```

### 查找测试文件

```python
Glob(pattern="*test*.py")
Glob(pattern="tests/**/*.py")
```

### 查找配置文件

```python
Glob(pattern="*.json")
Glob(pattern="*.yaml")
Glob(pattern="*.toml")
```

### 递归查找

```python
Glob(pattern="**/*.md")
```

## 使用场景

### 场景1：查找源代码

```python
Glob(pattern="src/**/*.py")
```

### 场景2：查找文档

```python
Glob(pattern="docs/**/*.md")
```

### 场景3：批量选择文件

```python
# 查找所有测试文件
Glob(pattern="tests/**/test_*.py")
```

## 输出格式

```
Found 15 files matching '*.py':
- src/main.py
- src/utils.py
- src/config.py
- src/tools/base.py
- src/tools/bash_tool.py
...
```

## 与 Grep 配合使用

```python
# 1. 查找所有 Python 文件
files = Glob(pattern="src/**/*.py")

# 2. 在文件中搜索内容
Grep(pattern="TODO", path="src/", glob="*.py")
```

## 相关工具

- **Grep** - 文本搜索
- **FileRead** - 读取文件
- **CodeSearch** - 代码搜索