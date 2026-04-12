# WebSearch 工具

网页搜索工具。

## 作用

- 搜索网络内容
- 查找文档
- 获取最新信息

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 搜索查询 |

## 使用示例

### 搜索文档

```python
WebSearch(query="Python asyncio tutorial")
```

### 查找 API

```python
WebSearch(query="OpenAI API documentation")
```

### 获取最新信息

```python
WebSearch(query="Python 3.12 new features")
```

## 使用场景

### 场景1：查找文档

```python
WebSearch(query="requests library documentation")
```

### 场景2：解决问题

```python
WebSearch(query="Python ImportError No module named")
```

### 场景3：学习新技术

```python
WebSearch(query="fastapi getting started")
```

## 输出格式

```
Search results for "Python asyncio":

1. asyncio — Asynchronous I/O - Python documentation
   https://docs.python.org/3/library/asyncio.html
   
2. Async IO in Python: A Complete Walkthrough - Real Python
   https://realpython.com/async-io-python/
   
3. Python Asyncio: The Complete Guide
   https://superfastpython.com/python-asyncio/
```

## 注意事项

1. **需要网络连接**
2. **搜索可能较慢**（1-3秒）
3. **结果准确性**取决于搜索引擎

## 与 WebFetch 的区别

| WebSearch | WebFetch |
|-----------|----------|
| 搜索关键词 | 获取特定 URL |
| 返回多个结果 | 返回单个页面 |
| 发现内容 | 读取内容 |

## 相关工具

- **WebFetch** - 获取网页内容
- **Bash** - 使用 curl/wget