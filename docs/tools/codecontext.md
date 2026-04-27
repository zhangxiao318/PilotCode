# CodeContext 工具

代码上下文构建工具（RAG）。

## 作用

- 根据查询构建代码上下文
- 为 LLM 提供相关代码片段
- 支持 Token 预算管理
- **自动注入项目记忆知识库**（`.pilotcode/memory/` 中的事实、Bug、决策、Q&A，relevance_score=0.95）
- **支持分层索引子图过滤**（`subgraph` 参数聚焦特定模块）

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 查询主题 |
| `max_tokens` | integer | ❌ | Token 上限 |
| `include_related` | boolean | ❌ | 包含相关符号 |
| `subgraph` | string | ❌ | 聚焦特定子图（分层索引 drill-down） |

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

### 聚焦子图（大型项目）

```python
# 深入特定模块分析，避免全库上下文溢出
CodeContext(
    query="路由分发逻辑",
    max_tokens=4000,
    subgraph="src/router"
)
```

## 使用场景

### 场景1：理解复杂功能

```python
# 获取认证系统的完整上下文（自动注入相关记忆）
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

### 场景4：大型项目模块分析

```python
# 聚焦支付模块，避免加载整个代码库
CodeContext(
    query="退款流程",
    max_tokens=4000,
    subgraph="src/payment"
)
```

## 输出格式

```
# Code Context for: authentication flow

## Project Memory
- [Fact] Project uses asyncio everywhere (relevance: 0.95)

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

1. **项目记忆检索** — 从 `.pilotcode/memory/` 搜索相关事实/Bug/决策/Q&A（relevance=0.95）
2. **语义搜索相关代码** — 使用 numpy 批量向量相似度
3. **符号搜索精确匹配** — 利用桶索引快速定位
4. **获取相关符号**（同文件、调用关系）
5. **按 Token 预算组装** — 记忆片段优先，然后是代码片段

## 前提条件

必须先建立代码索引。超过 10 个文件的项目会自动构建分层索引，支持 `subgraph` 参数 drill-down。

## 相关工具

- **CodeIndex** - 建立索引
- **CodeSearch** - 代码搜索
