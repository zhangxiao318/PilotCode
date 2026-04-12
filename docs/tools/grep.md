# Grep 工具

文本搜索工具，使用正则表达式匹配。

## 作用

- 搜索文件中的文本
- 正则表达式匹配
- 查找代码模式
- 定位特定内容

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | ✅ | 正则表达式 |
| `path` | string | ❌ | 搜索路径（默认当前目录） |
| `glob` | string | ❌ | 文件模式过滤 |
| `output_mode` | string | ❌ | 输出模式 |

## Output Mode

| 模式 | 说明 |
|------|------|
| `content` | 显示匹配内容 |
| `files_with_matches` | 只显示文件名 |
| `count_matches` | 只显示匹配数 |

## 使用示例

### 基本搜索

```python
Grep(pattern="TODO", path="src/")
```

### 正则搜索

```python
Grep(pattern="def \w+", path="src/")
```

### 按文件类型过滤

```python
Grep(pattern="class", path="src/", glob="*.py")
```

### 只显示文件名

```python
Grep(pattern="import", path="src/", output_mode="files_with_matches")
```

## 使用场景

### 场景1：查找 TODO

```python
Grep(pattern="TODO|FIXME|XXX", path="src/")
```

### 场景2：查找函数定义

```python
Grep(pattern="^def \w+", path="src/")
```

### 场景3：查找类定义

```python
Grep(pattern="^class \w+", path="src/")
```

### 场景4：查找导入

```python
Grep(pattern="^from|import", path="src/", glob="*.py")
```

## 输出格式

```
src/main.py:10:def main():
src/main.py:15:def configure():
src/utils.py:5:def helper():
```

## 与 CodeSearch 的区别

| Grep | CodeSearch |
|------|------------|
| 无需索引 | 需要索引 |
| 纯文本匹配 | 语义理解 |
| 较慢（全文扫描） | 快（预建索引） |
| 适合临时搜索 | 适合频繁搜索 |

## 相关工具

- **CodeSearch** - 智能代码搜索（需索引）
- **Glob** - 文件匹配
- **FileRead** - 读取文件