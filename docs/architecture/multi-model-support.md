# 多模型支持架构设计

本文档描述 PilotCode 的多模型支持架构，包括如何统一接入不同 LLM Provider（OpenAI、Anthropic、DeepSeek、Qwen 等），以及如何通过三层架构将 provider-specific 的硬编码逻辑转化为可配置、可扩展的声明式系统。

## 目录

- [1. 背景与动机](#1-背景与动机)
- [2. 核心概念](#2-核心概念)
- [3. 三层架构](#3-三层架构)
  - [3.1 能力矩阵（ModelCapabilities）](#31-能力矩阵modelcapabilities)
  - [3.2 转换管道（ProtocolNormalizer）](#32-转换管道protocolnormalizer)
  - [3.3 参数生成器（ParameterGenerator）](#33-参数生成器parametergenerator)
- [4. 配置系统](#4-配置系统)
- [5. 协议抽象](#5-协议抽象)
- [6. 能力探测](#6-能力探测)
- [7. 接入新 Provider](#7-接入新-provider)
- [8. 与 opencode 架构的对比](#8-与-opencode-架构的对比)

---

## 1. 背景与动机

PilotCode 需要支持多种 LLM Provider，包括：

- **国际模型**：OpenAI GPT、Anthropic Claude、Google Gemini、xAI Grok、DeepSeek
- **国内模型**：通义千问（Qwen）、智谱清言（GLM）、Moonshot（Kimi）、Baichuan、Doubao
- **本地模型**：Ollama、vLLM、llama.cpp、TGI

这些 Provider 的 API 协议差异显著：

| 差异维度 | OpenAI 协议 | Anthropic 协议 | 自定义协议 |
|---|---|---|---|
| 端点 | `/chat/completions` | `/messages` | 各异 |
| 认证头 | `Authorization: Bearer` | `x-api-key` + `anthropic-version` | 各异 |
| 消息格式 | 统一 `messages` 数组 | `system` 提至顶层，tool → `tool_result` | 各异 |
| 工具格式 | `{type: "function", function: {...}}` | `{name, description, input_schema}` | 各异 |
| 流式响应 | SSE `choices[].delta.content` | SSE `content_block_delta` | 各异 |
| 推理内容 | `reasoning_content` 字段 | `thinking` content block | 各异 |

**早期方案的问题**：所有转换逻辑散落在 `ModelClient._build_anthropic_payload`、`_normalize_anthropic_stream` 等方法中，新增 Provider 需要修改核心客户端代码，可维护性差。

**新方案的目标**：

1. **零侵入核心调用链**：15+ 个消费文件（`query_engine.py`、`repl.py`、`adapter.py` 等）无需修改
2. **声明式配置**：Provider 差异通过 `models.json` 的 `capabilities` 声明，而非硬编码
3. **三层分离**：能力声明 → 消息转换 → 参数生成，每层可独立扩展

---

## 2. 核心概念

### 2.1 Provider vs Protocol vs Model

这三个概念必须严格分离：

| 概念 | 含义 | 示例 |
|---|---|---|
| **Provider** | 商业身份/品牌 | anthropic、deepseek、openai |
| **Protocol** | 消息格式、认证方式、端点路径 | `openai`（`/chat/completions`）、`anthropic`（`/messages`） |
| **Model** | 实际调用 API 时传递的模型 ID | `claude-3-5-sonnet-20241022`、`deepseek-v4-pro` |
| **Base URL** | API 根地址（可能已包含版本路径） | `https://api.anthropic.com/v1`、`https://api.deepseek.com` |

**关键规则**：

- `endpoint` 是相对于 `base_url` 的路径。Anthropic 的 `base_url` 以 `/v1` 结尾，所以 endpoint 是 `/messages` 而非 `/v1/messages`
- DeepSeek 的 `/anthropic` 兼容端点：协议为 `anthropic`，`base_url` 为 `https://api.deepseek.com`，实际 endpoint 拼接后为 `/anthropic/v1/messages`（由代理层处理）

### 2.2 API 协议推断

`infer_api_protocol()` 按优先级解析协议：

```
1. 用户显式覆盖（settings.json model_overrides.api_protocol）
2. models.json 显式配置（model_info.api_protocol）
3. URL 路径启发式（/messages → anthropic，/chat/completions → openai）
4. 模型名启发式（claude-* → anthropic，gpt-* → openai）
5. Provider 枚举回退（anthropic → anthropic，其他 → openai）
6. 默认 openai
```

---

## 3. 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    ModelClient (HTTP 编排层)                  │
│  - 维护 httpx.AsyncClient                                    │
│  - 调用三层架构生成 payload 并发送请求                         │
│  - 15+ 消费文件保持完全不变                                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  能力矩阵      │   │   转换管道       │   │  参数生成器      │
│ ModelCapabilities│  │ ProtocolNormalizer│  │ ParameterGenerator│
├───────────────┤   ├─────────────────┤   ├─────────────────┤
│ 声明模型能做什么│   │ 消息/响应格式转换 │   │ 生成请求参数     │
│ - reasoning   │   │ - 系统提取       │   │ - auth headers  │
│ - tool_call   │   │ - tool 转换      │   │ - endpoint      │
│ - image_input │   │ - ID scrubbing   │   │ - temperature   │
│ - temperature │   │ - 序列修复       │   │ - max_tokens    │
│ - interleaved │   │ - 空内容过滤     │   │ - tool_choice   │
└───────────────┘   └─────────────────┘   └─────────────────┘
```

### 3.1 能力矩阵（ModelCapabilities）

**文件**：`src/pilotcode/utils/model_capabilities.py`

**设计灵感**：opencode 的 `models.dev` API schema。

```python
@dataclass
class ModelCapabilities:
    temperature: bool = True          # 是否支持 temperature 参数
    reasoning: bool = False           # 是否支持 thinking/reasoning
    tool_call: bool = True            # 是否支持工具调用
    attachment: bool = False          # 是否支持文件上传
    image_input: bool = False         # 是否支持图片输入
    audio_input: bool = False         # 是否支持音频输入
    video_input: bool = False         # 是否支持视频输入
    pdf_input: bool = False           # 是否支持 PDF 输入
    text_output: bool = True          # 是否支持文本输出
    interleaved: bool | dict = False  # 是否支持交织内容，或指定字段名
    requires_tool_choice_explicit: bool = False  # 是否必须显式发送 tool_choice
    reasoning_content_field: bool = False        # 是否使用 reasoning_content 字段
```

**加载方式**：

```json
{
  "models": {
    "anthropic": {
      "capabilities": {
        "tool_call": true,
        "image_input": true,
        "pdf_input": true,
        "reasoning": true,
        "requires_tool_choice_explicit": true
      }
    }
  }
}
```

支持 **modalities 快捷方式**（opencode 风格）：

```json
{
  "capabilities": {
    "modalities": {
      "input": ["text", "image", "pdf"],
      "output": ["text"]
    }
  }
}
```

**向后兼容**：旧字段 `supports_tools`、`supports_vision`、`supports_tool_choice`、`reasoning_content` 自动映射到新能力矩阵的对应字段。

### 3.2 转换管道（ProtocolNormalizer）

**文件**：`src/pilotcode/utils/protocol_normalizer.py`

#### MessageNormalizer

将内部 `Message` 对象转换为 provider-native 格式。执行以下管道步骤：

```python
def normalize(self, messages) -> tuple[list[dict], str | None]:
    msgs = self._ensure_dicts(messages)          # dataclass → dict
    msgs = self._filter_empty_content(msgs)      # Anthropic 拒绝空内容
    msgs = self._scrub_tool_call_ids(msgs)       # ID 格式清洗
    msgs = self._fix_message_sequences(msgs)     # 消息序列修复
    if self.api_protocol == "anthropic":
        return self._normalize_for_anthropic(msgs)
    return self._normalize_for_openai(msgs)
```

**各步骤详解**：

| 步骤 | OpenAI | Anthropic | Mistral |
|---|---|---|---|
| `_ensure_dicts` | Message dataclass → dict | 同上 | 同上 |
| `_filter_empty_content` | 无操作 | 过滤空字符串消息；保留带 tool_calls 的空 assistant | 无操作 |
| `_scrub_tool_call_ids` | 无操作 | 非法字符 → `_` | 截断至 9 位 alphanumeric，补 `0` |
| `_fix_message_sequences` | 无操作 | 无操作 | tool → user 之间插入 dummy assistant |
| `_normalize_for_anthropic` | — | 提取 system；tool→user+tool_result；tool_calls→tool_use | — |
| `_normalize_for_openai` | reasoning_content 前置排序；确保 content 存在 | — | — |

#### ResponseNormalizer

将 provider-native 响应转换为统一的 OpenAI-style chunk：

```python
# Anthropic SSE 事件 → OpenAI delta chunk
"content_block_delta" + "text_delta"      → {"delta": {"content": "..."}}
"content_block_delta" + "thinking_delta"  → {"delta": {"reasoning_content": "..."}}
"content_block_start" + "tool_use"        → {"delta": {"tool_calls": [{"index": 0, "id": "...", ...}]}}
"content_block_delta" + "input_json_delta" → {"delta": {"tool_calls": [{"function": {"arguments": "..."}}]}}
"message_delta"                           → {"delta": {}, "finish_reason": "stop", "usage": {...}}
```

### 3.3 参数生成器（ParameterGenerator）

**文件**：`src/pilotcode/utils/parameter_generator.py`

根据 `api_protocol` 和 `model_info` 生成请求参数：

```python
class ParameterGenerator:
    def get_auth_headers(self, api_key) -> dict       # x-api-key vs Bearer
    def get_endpoint(self) -> str                     # /messages vs /chat/completions
    def get_temperature(self, t: float) -> float|None # Claude → None, Qwen → 0.55
    def get_max_tokens(self, n: int|None) -> int      # DeepSeek 最小 8192
    def get_stream_options(self, stream: bool) -> dict|None  # include_usage
    def get_tool_params(self, tools) -> dict          # tool_choice 策略
    def build_payload(self, ...) -> dict[str, Any]    # 完整请求体组装
```

**temperature 策略**（opencode 风格）：

| 模型 | temperature |
|---|---|
| Claude | `None`（省略） |
| Qwen | `0.55` |
| Gemini | `1.0` |
| Kimi K2.5 | `1.0` |
| 其他 | 透传用户输入 |

**max_tokens 回退链**：

```
用户显式值
  → DeepSeek 最小值修正（<4096 时强制 8192）
    → model_info.max_tokens
      → 默认 4096
```

**tool_choice 策略**：

```python
if api_protocol == "anthropic":
    return {"type": "auto"}           # Anthropic 始终需要显式 tool_choice
else:
    supports = model_info.supports_tool_choice if model_info else True
    return "auto" if supports else None  # OpenAI-compatible 按能力决定
```

---

## 4. 配置系统

配置按优先级合并：

```
1. models.json 静态配置（基础定义、capabilities）
2. settings.json 用户配置（model_overrides、api_protocol、base_url）
3. 环境变量（PILOTCODE_API_KEY、PILOTCODE_API_PROTOCOL 等）
4. 运行时探测（llama.cpp /props、Ollama /api/show、/v1/models）
```

### 4.1 models.json 结构

```json
{
  "models": {
    "anthropic": {
      "name": "anthropic",
      "display_name": "Anthropic Claude",
      "provider": "anthropic",
      "api_protocol": "anthropic",
      "base_url": "https://api.anthropic.com/v1",
      "default_model": "claude-3-5-sonnet-20241022",
      "max_tokens": 8192,
      "context_window": 200000,
      "env_key": "ANTHROPIC_API_KEY",
      "capabilities": {
        "tool_call": true,
        "image_input": true,
        "pdf_input": true,
        "reasoning": true,
        "requires_tool_choice_explicit": true
      }
    }
  }
}
```

### 4.2 用户覆盖（settings.json）

```json
{
  "default_model": "anthropic",
  "api_key": "sk-xxx",
  "api_protocol": "anthropic",
  "model_overrides": {
    "deepseek": {
      "api_key": "sk-yyy",
      "base_url": "https://api.deepseek.com/anthropic",
      "api_protocol": "anthropic"
    }
  }
}
```

---

## 5. 协议抽象

### 5.1 消息格式差异

**OpenAI 协议**（内部统一格式）：

```json
[
  {"role": "system", "content": "Be helpful"},
  {"role": "user", "content": "Run ls"},
  {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "Bash", "arguments": "{\"command\": \"ls\"}"}}]},
  {"role": "tool", "content": "file.txt", "tool_call_id": "call_1"}
]
```

**Anthropic 协议**（转换后）：

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "system": "Be helpful",
  "messages": [
    {"role": "user", "content": "Run ls"},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "call_1", "name": "Bash", "input": {"command": "ls"}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "file.txt"}]}
  ]
}
```

### 5.2 流式响应差异

**OpenAI 流**：

```
data: {"choices": [{"delta": {"content": "Hello"}}]}
data: {"choices": [{"delta": {"content": " world"}}]}
data: [DONE]
```

**Anthropic 流**（经 `ResponseNormalizer` 转换后对外呈现为 OpenAI 格式）：

```
event: message_start
data: {"type": "message_start", "message": {"usage": {"input_tokens": 5}}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}}
```

### 5.3 Thinking / Reasoning 差异

| Provider | 协议 | 响应中的推理内容 |
|---|---|---|
| DeepSeek (OpenAI) | `openai` | `choices[0].delta.reasoning_content` |
| Anthropic (native) | `anthropic` | `content[].type == "thinking"` → `thinking` 字段 |
| DeepSeek (/anthropic) | `anthropic` | `content[].type == "thinking"` → 经 normalizer 映射为 `reasoning_content` |

---

## 6. 能力探测

`fetch_model_capabilities()` 按以下顺序探测后端能力：

```
1. llama.cpp /props              → n_ctx, max_tokens, vision
2. Ollama /api/show              → context_length, capabilities
3. LiteLLM /model/info           → max_input_tokens, max_output_tokens
4. OpenAI / Anthropic /v1/models → context_window, max_tokens, supports_vision
5. models.json 静态回退          → 所有字段
6. Capability matrix 回退        → capabilities.reasoning, image_input 等
```

Anthropic 协议后端跳过步骤 1-3（本地后端探测），直接尝试 `/v1/models` 或 `/models`。

---

## 7. 接入新 Provider

接入一个新 Provider（例如 Cohere）只需三步：

### 步骤 1：在 models.json 中声明

```json
{
  "cohere": {
    "name": "cohere",
    "display_name": "Cohere Command",
    "provider": "custom",
    "base_url": "https://api.cohere.ai/v1",
    "default_model": "command-r-plus",
    "max_tokens": 4096,
    "context_window": 128000,
    "env_key": "COHERE_API_KEY",
    "capabilities": {
      "tool_call": true,
      "image_input": false,
      "reasoning": false
    }
  }
}
```

### 步骤 2：如果协议与 OpenAI/Anthropic 不同

- 在 `infer_api_protocol()` 中添加 URL/模型名启发式规则
- 在 `MessageNormalizer` 中添加 `_normalize_for_cohere()` 方法
- 在 `ResponseNormalizer` 中添加 Cohere 响应转换
- 在 `ParameterGenerator` 中添加 Cohere 特定的参数生成逻辑

### 步骤 3：如果存在已知的 edge cases

- `MessageNormalizer._scrub_tool_call_ids`：添加 Cohere 的 ID 清洗规则
- `MessageNormalizer._fix_message_sequences`：添加 Cohere 的消息序列约束
- `ParameterGenerator.get_temperature`：添加 Cohere 的 temperature 策略

**无需修改 `ModelClient.chat_completion()` 或任何消费文件。**

---

## 8. 与 opencode 架构的对比

| 维度 | opencode (TypeScript) | PilotCode (Python) |
|---|---|---|
| **协议抽象** | 依赖 Vercel AI SDK（`@ai-sdk/*` 包） | 自建 normalization 层（`ProtocolNormalizer`） |
| **模型数据库** | 远程 `models.dev`（自动刷新） | 静态 `models.json`（可扩展为远程） |
| **能力定义** | `modalities`、`interleaved`、`cost`、`limit` | `ModelCapabilities`（简化版，可扩展） |
| **消息转换** | `ProviderTransform.message()` 集中处理 | `MessageNormalizer` 管道处理 |
| **参数生成** | `ProviderTransform.options()`、`temperature()`、`topP()` | `ParameterGenerator` 统一处理 |
| **变体支持** | `variants`（reasoning effort low/medium/high/max） | 当前未实现，可在 `ParameterGenerator` 中扩展 |
| **插件钩子** | `chat.params`、`chat.headers`、`experimental.chat.system.transform` | 当前未实现，可在 `ModelClient` 中扩展 |

**PilotCode 选择自建 normalization 的原因**：

1. Python 生态没有统一、轻量的 `ai` SDK 等价物（LiteLLM 依赖过重，Pydantic AI 较新）
2. CLI 工具对依赖体积敏感，自建层更可控
3. 不需要等待 SDK 更新即可支持新 Provider 的 edge case

---

## 附录：文件清单

| 文件 | 说明 |
|---|---|
| `src/pilotcode/utils/model_capabilities.py` | 能力矩阵定义 |
| `src/pilotcode/utils/protocol_normalizer.py` | 转换管道（MessageNormalizer + ResponseNormalizer） |
| `src/pilotcode/utils/parameter_generator.py` | 参数生成器 |
| `src/pilotcode/utils/models_config.py` | 模型配置加载（含 capabilities 解析） |
| `src/pilotcode/utils/model_client.py` | HTTP 客户端（委托三层架构） |
| `config/models.json` | 静态模型注册表 |
| `tests/unit/utils/test_model_capabilities.py` | 能力矩阵测试 |
| `tests/unit/utils/test_protocol_normalizer.py` | 转换管道测试 |
| `tests/unit/utils/test_parameter_generator.py` | 参数生成器测试 |
