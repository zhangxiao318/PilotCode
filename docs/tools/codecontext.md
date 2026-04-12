# CodeContext 工具

代码上下文构建工具（RAG）。

## 作用

- 根据查询构建代码上下文
- 为 LLM 提供相关代码片段
- 支持 Token 预算管理

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 查询主题 |
| `max_tokens` | integer | ❌ | Token 上限 |
| `include_related` | boolean | ❌ | 包含相关符号 |

## 使用示例

### 基本用法

```python
CodeContext(
    query="How does authentication work?",
    max_tokens=4000
)
```

### 包含相关符号

```python
CodeContext(
    query="database connection pool",
    max_tokens=3000,
    include_related=True
)
```

## 使用场景

### 场景1：理解复杂功能

```python
# 获取认证系统的完整上下文
CodeContext(
    query="authentication flow",
    max_tokens=4000
)
```

### 场景2：代码审查

```python
# 获取相关代码片段
CodeContext(
    query="error handling in payment processing",
    max_tokens=3000
)
```

### 场景3：重构准备

```python
# 了解模块依赖
CodeContext(
    query="UserService dependencies",
    max_tokens=2000
)
```

## 输出格式

```
# Code Context for: authentication flow

## Retrieved Code Snippets

### src/auth/middleware.py:15 (class AuthMiddleware)
```python
class AuthMiddleware:
    def process_request(self, request):
        # Check authentication
        pass
```

### src/auth/service.py:42 (function authenticate)
```python
def authenticate_user(username, password):
    # Validate credentials
    pass
```

Coverage: 3 files, ~500 tokens
```

## 工作原理

1. 语义搜索相关代码
2. 符号搜索精确匹配
3. 获取相关符号（同文件、调用关系）
4. 按 Token 预算组装

## 前提条件

必须先建立代码索引。

## 相关工具

- **CodeIndex** - 建立索引
- **CodeSearch** - 代码搜索