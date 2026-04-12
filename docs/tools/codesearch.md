# CodeSearch 工具

智能代码搜索工具。

## 作用

- 语义搜索（自然语言）
- 符号搜索（类、函数名）
- 正则搜索
- 文件搜索

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 搜索查询 |
| `search_type` | string | ✅ | 搜索类型 |
| `max_results` | integer | ❌ | 最大结果数 |

## Search Type

| 类型 | 说明 | 示例 |
|------|------|------|
| `semantic` | 语义搜索 | `"authentication logic"` |
| `symbol` | 符号搜索 | `"UserModel"` |
| `regex` | 正则搜索 | `"class.*"` |
| `file` | 文件搜索 | `"*.py"` |

## 使用示例

### 语义搜索

```python
CodeSearch(
    query="authentication middleware",
    search_type="semantic"
)
```

### 符号搜索

```python
CodeSearch(
    query="UserModel",
    search_type="symbol"
)
```

### 正则搜索

```python
CodeSearch(
    query="class.*Controller",
    search_type="regex"
)
```

### 文件搜索

```python
CodeSearch(
    query="*test*.py",
    search_type="file"
)
```

## 使用场景

### 场景1：查找功能实现

```python
# 语义搜索更直观
CodeSearch(
    query="password hashing",
    search_type="semantic"
)
```

### 场景2：精确定位

```python
# 知道类名时快速定位
CodeSearch(
    query="AuthManager",
    search_type="symbol"
)
```

### 场景3：模式查找

```python
# 查找所有控制器
CodeSearch(
    query="class.*Controller",
    search_type="regex"
)
```

## 输出格式

```
Found 5 results for 'authentication':

1. src/auth/middleware.py:15 (class AuthMiddleware)
   Relevance: 0.95
   ```python
   class AuthMiddleware:
       def process_request(self, request):
   ```
```

## 前提条件

必须先使用 `CodeIndex` 或 `/index` 建立索引。

## 相关工具

- **CodeIndex** - 建立索引
- **CodeContext** - 构建上下文

## 对应的命令

- `/search` - 更方便的搜索命令