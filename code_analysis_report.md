# PilotCode 代码分析报告

## 1. Overview

本报告分析从 DeepSeek API 错误 trace 出发，追溯代码逻辑链，识别根本原因、缺失依赖和不正确用法。

**错误 trace**: `DeepSeek API error 400: "The reasoning_content in the thinking mode must be passed back to the API."`

---

## 2. 错误溯源分析

### 2.1 分析工具使用

用 `error_classifier.py` 对错误文本进行分类：

```
$ python error_classifier.py /tmp/pilotcode_message_1777174709.txt
Error Type: InvalidRequestError
Stack Trace Locations:
  (none extracted)
```

错误类型被正确识别为 `InvalidRequestError`。由于该错误是 JSON API 响应而非 Python traceback，文件行号无法提取——这是设计局限，不是 bug。

### 2.2 消息流转逻辑链

追踪 `reasoning_content` 字段在代码中的生命周期：

```
DeepSeek API 返回 assistant message (含 reasoning_content)
    ↓
query_engine.py 流式处理，累积 accumulated_reasoning
    ↓
创建 AssistantMessage(content=..., reasoning_content=...)
    ↓  存入 self.messages
    ↓
[可能触发 context compaction]
    ↓
_convert_to_api_messages() → APIMessage (含 reasoning_content)
    ↓
ModelClient._convert_messages() → api_msg["reasoning_content"]
    ↓
发送到 DeepSeek API
```

### 2.3 根本原因：reasoning_content 在压缩时丢失

**位置 1**: `src/pilotcode/query_engine.py` 第 1080 行

```python
# auto_compact_if_needed() 中的 Fallback 3
elif isinstance(msg, AssistantMessage):
    self.messages[i] = AssistantMessage(content=truncated_text)
    # BUG: reasoning_content 未保留！新 AssistantMessage 的 reasoning_content 默认为 None
```

**位置 2**: `src/pilotcode/services/intelligent_compact.py` 第 227 行

```python
# compact_messages() 中的 critical mode 截断
if isinstance(msg, UserMessage):
    msg = UserMessage(content=truncated)
else:
    msg = AssistantMessage(content=truncated)
    # BUG: reasoning_content 未保留！
```

**影响**: DeepSeek 的 thinking mode 要求每个曾经包含 `reasoning_content` 的 assistant 消息在后续请求中**必须**回传该字段。一旦 context compaction 被触发（token 超过 80% 阈值），上述代码会创建新的 `AssistantMessage` 对象，丢失 `reasoning_content` 字段。下一次 API 调用时，`ModelClient._convert_messages()` 中：

```python
# model_client.py 第 152 行
if self._is_deepseek and msg.reasoning_content and msg.role == "assistant":
    api_msg["reasoning_content"] = msg.reasoning_content
```

由于 `msg.reasoning_content` 为 `None`（falsy），条件不成立，`reasoning_content` 不会被添加到 API 请求中，导致 DeepSeek API 返回 400 错误。

**修复方案**: 创建新 `AssistantMessage` 时保留原消息的 `reasoning_content`：

```python
# query_engine.py:1080 修复
self.messages[i] = AssistantMessage(
    content=truncated_text,
    reasoning_content=getattr(msg, 'reasoning_content', None),
)

# intelligent_compact.py:233 修复
msg = AssistantMessage(
    content=truncated,
    reasoning_content=getattr(msg, 'reasoning_content', None),
)
```

---

## 3. 缺失依赖

### 3.1 `networkx`

**文件**: `error_tracing_analysis.py` 第 10 行

```python
import networkx as nx
```

**问题**: `networkx` 未在 `requirements.txt` 或 `pyproject.toml` 中声明。虽然当前系统已安装该包，但新环境部署时会因导入失败而崩溃。

**影响范围**: `ErrorTracingAnalyzer` 类使用 `networkx.DiGraph` 构建错误依赖图（第 20-21 行），并调用 `nx.simple_cycles()` 检测循环依赖（第 82 行）。缺失该依赖会导致整个 `error_tracing_analysis` 模块不可用。

**修复**: 在 `requirements.txt` 中添加 `networkx>=3.0`。

---

## 4. 不正确用法

### 4.1 error_classifier.py: `.capitalize()` 破坏错误类型名

**文件**: `error_classifier.py` 第 19 行

```python
err_type = "".join(w.capitalize() for w in re.split(r"[_ ]+", m.group(1)))
```

**问题**: Python 字符串的 `.capitalize()` 方法会将首字母大写，其余字母**全部小写**。这破坏了 CamelCase 错误名：

| 原始错误名          | 错误输出            |
|---------------------|---------------------|
| `ValueError`        | `Valueerror`        |
| `FileNotFoundError` | `Filenotfounderror` |
| `RuntimeError`      | `Runtimeerror`      |
| `TypeError`         | `Typeerror`         |

**修复**: 使用 `.title()` 或直接保留原始匹配：

```python
# 方案 A: 不处理已为 CamelCase 的错误名
err_type = m.group(1)
# 方案 B: 仅对下划线分隔的名称做转换
parts = re.split(r"[_ ]+", m.group(1))
if len(parts) > 1:
    err_type = "".join(p.capitalize() for p in parts)
else:
    err_type = parts[0]  # 保留原始 CamelCase
```

### 4.2 scan_tools.py: 过于宽泛的异常捕获

**文件**: `scan_tools.py` 第 137 行

```python
except Exception:
    pass  # 忽略无法读取的文件
```

**问题**: 这正是 `exception_analysis.py` 识别的反模式——使用 `except Exception: pass` 会隐藏所有具体错误类型（权限错误、编码错误等），使调试困难。

**修复**:

```python
except (UnicodeDecodeError, PermissionError, OSError):
    pass  # 忽略无法读取的文件
```

### 4.3 model_client.py: 通用异常消息

**文件**: `src/pilotcode/utils/model_client.py` 第 219 行

```python
raise Exception(
    f"DeepSeek API error {response.status_code}: {body.decode('utf-8', errors='replace')}\n"
    f"Payload: {json.dumps(payload, ensure_ascii=False, default=str)[:2000]}"
)
```

**问题**: 
1. 抛出不具体的 `Exception` 而非自定义异常类型（如 `ModelAPIError`）
2. 错误消息硬编码了 "DeepSeek"，实际上可能来自任何 provider
3. Payload 截断到 2000 字符，可能隐藏关键的错误上下文

---

## 5. 总结

| 严重性 | 类别         | 位置                                          | 描述                                   |
|--------|--------------|-----------------------------------------------|----------------------------------------|
| 🔴 高  | 数据丢失     | `query_engine.py:1080`                        | `reasoning_content` 在压缩时丢失       |
| 🔴 高  | 数据丢失     | `intelligent_compact.py:227`                  | `reasoning_content` 在压缩时丢失       |
| 🟡 中  | 缺失依赖     | `error_tracing_analysis.py:10`                | `networkx` 未声明为依赖                |
| 🟡 中  | 错误处理     | `error_classifier.py:19`                      | `.capitalize()` 破坏 CamelCase 错误名  |
| 🟢 低  | 反模式       | `scan_tools.py:137`                           | 过于宽泛的 `except Exception: pass`    |
| 🟢 低  | 错误处理     | `model_client.py:219`                         | 硬编码 provider 名称 + 通用异常类型    |
