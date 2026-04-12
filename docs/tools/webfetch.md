# WebFetch 工具

网页内容获取工具。

## 作用

- 获取网页内容
- 读取文档页面
- 提取文章内容

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `url` | string | ✅ | 网页 URL |

## 使用示例

### 获取文档

```python
WebFetch(url="https://docs.python.org/3/library/asyncio.html")
```

### 获取文章

```python
WebFetch(url="https://example.com/article")
```

## 使用场景

### 场景1：读取文档

```python
# 先用 WebSearch 找到文档链接
WebSearch(query="Python dataclasses documentation")

# 然后获取具体内容
WebFetch(url="https://docs.python.org/3/library/dataclasses.html")
```

### 场景2：获取参考内容

```python
WebFetch(url="https://example.com/api-reference")
```

## 输出格式

```
Title: asyncio — Asynchronous I/O
URL: https://docs.python.org/3/library/asyncio.html

Content:
==============
asyncio is a library to write concurrent code using the async/await syntax.
...
```

## 注意事项

1. **需要网络连接**
2. **可能失败**：网站可能拒绝访问
3. **内容长度**：长页面可能被截断

## 与 WebSearch 的配合

```python
# 1. 搜索
WebSearch(query="Python asyncio best practices")

# 2. 获取感兴趣的结果
WebFetch(url="https://realpython.com/async-io-python/")
```

## 相关工具

- **WebSearch** - 搜索网页
- **Bash** - 使用 curl 获取