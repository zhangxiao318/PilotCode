# Token 计算体系架构

> **状态**: ✅ 已重构完成
> **关联改进项**: 消除 TokenUsage 重复定义、统一 magic number、PreciseTokenizer 依赖注入
> **适用场景**: 所有对话模式（DIRECT / P-EVR / Web / TUI）

---

## 1. 背景与问题

PilotCode 需要在多个场景下精确或近似地计算 token 消耗：

- **API 流式响应**：从 chunk 中解析 `usage` 字段获取真实 token 数
- **上下文压缩**：在触发压缩前估算当前对话的 token 量
- **工具结果截断**：根据剩余可用上下文动态截断过长的 tool result
- **基线测量**：新会话启动时估算 system prompt + tool definitions 占用的 token
- **溢出检测**：判断当前对话是否接近或超过模型上下文窗口

早期实现中，这些功能分散在 5 个文件中，存在以下问题：

1. **TokenUsage dataclass 重复定义**：`query_engine.py` 和 `query/token_manager.py` 各有一份，维护时容易遗漏同步
2. **magic number 分散**：`+12/msg`、`+4/tool`、`×1.08`、`×1.5` 等修正因子散落在 `TokenManager` 的多个私有方法中
3. **PreciseTokenizer 被双重持有**：`TokenManager` 和 `TokenEstimator` 各自懒加载一个实例，可能产生两份独立的 HTTP 探测结果和缓存
4. **`token_utils.py` 半废弃**：直接调用 `tiktoken`，但核心体系已迁移到 `PreciseTokenizer` + `TokenEstimator`

---

## 2. 核心设计

Token 计算体系采用 **三层架构 + 基线测量**：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         调用方（QueryEngine / SessionService）            │
│                              只认 TokenManager                            │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────┐
│                    TokenManager（策略协调层）                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  count_tokens()  →  四层回退策略 + 状态哈希缓存                    │   │
│  │  is_overflow()   →  阈值判断                                       │   │
│  │  get_token_budget() → 预算状态 + 基线信息                         │   │
│  │  measure_baseline() → 委托 TokenBaselineMeasurer                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                         │ 委托                                          │
┌─────────────────────────▼─────────────────────────────────────────────┐
│              TokenEstimator（统一估算层）                                 │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  estimate(text)          → 精确或启发式单文本估算                │  │
│  │  estimate_message()      → 单消息估算（含 MESSAGE_OVERHEAD）     │  │
│  │  estimate_messages()     → 消息列表估算                          │  │
│  │  estimate_tools()        → tool schema 估算（含 TOOL_OVERHEAD）  │  │
│  │  estimate_conversation() → 完整对话（system + messages + tools） │  │
│  │  get_budget_status()     → 预算状态（ok/caution/warning/exceeded）│  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                         │ 优先尝试                                      │
┌─────────────────────────▼─────────────────────────────────────────────┐
│           PreciseTokenizer（精确计数层）                                  │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  count_text() / count_messages() / count_messages_with_tools()  │  │
│  │  五级回退：vLLM → llama.cpp → Ollama → transformers → tiktoken   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
        ▲
        │ 使用
┌───────┴─────────────────────────────────────────────────────────────────┐
│           TokenBaselineMeasurer（基线测量层）                             │
│  调用 TokenEstimator.estimate() 测量 system + tools 基线                  │
│  结果按 session 缓存，供 TokenManager.get_token_budget() 合并展示         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 四层回退策略（TokenManager.count_tokens）

`TokenManager.count_tokens()` 是项目内所有 token 计数的统一入口，采用四层优先级回退：

```
count_tokens()
│
├─► 计算当前状态 MD5 哈希 (system + messages + tools)
│
├─► P1: API Usage 缓存命中？
│     条件: _last_api_usage 存在 AND hash == _last_api_usage_hash
│     返回: _last_api_usage.total_tokens  ← "地面真相"
│
├─► P2: Precise Tokenizer
│     条件: hash == _last_precise_count_hash（快速路径）
│     或: 调用 PreciseTokenizer.count_messages_with_tools()
│           ├── vLLM 端点 (原生 messages+tools)
│           ├── llama.cpp 端点 (ChatML + 单独 tools JSON)
│           ├── Ollama 端点
│           └── 文本拼接 + count_text() 回退
│     保存结果到缓存和 _exact_prompt_base
│
├─► P3: Exact Base + Delta
│     条件: _exact_prompt_base > 0
│     计算: 对 _exact_base_message_count 之后的新消息
│           逐条调用 TokenEstimator.estimate_message()
│     返回: base + delta
│
└─► P4: Full Heuristic Fallback
      计算: TokenEstimator.estimate_conversation()
            包含 SYSTEM_OVERHEAD + MESSAGE_OVERHEAD + TOOLS_OVERHEAD
            + HEURISTIC_CORRECTION (×1.08)
            + CLOUD_API_CORRECTION (×1.5, 云 API 时)
```

---

## 4. 模块职责

### 4.1 PreciseTokenizer (`services/precise_tokenizer.py`)

- **定位**：后端精确 tokenizer 的抽象层
- **核心功能**：通过 HTTP 调用本地后端的 `/tokenize` 端点获取真实 token 数
- **五级回退**：vLLM → llama.cpp → Ollama → transformers → tiktoken
- **全局缓存**：`get_precise_tokenizer()` 工厂按 `(base_url, model_name)` 缓存实例

### 4.2 TokenEstimator (`services/token_estimation.py`)

- **定位**：统一估算入口，所有启发式计算和修正因子集中在此处
- **核心常量**：
  | 常量 | 值 | 说明 |
  |------|-----|------|
  | `MESSAGE_OVERHEAD` | 12 | 单条消息的 role/format 开销 |
  | `SYSTEM_OVERHEAD` | 12 | system prompt 的格式开销 |
  | `TOOLS_OVERHEAD` | 12 | tool definitions 的总开销 |
  | `TOOL_SCHEMA_OVERHEAD` | 4 | 单个 tool schema 的结构开销 |
  | `HEURISTIC_CORRECTION` | 1.08 | 启发式估算的全局修正 |
  | `CLOUD_API_CORRECTION` | 1.5 | 云 API 的额外 overhead |
- **CJK 支持**：按 provider 自动检测并应用不同的 chars-per-token 比率

### 4.3 TokenManager (`query/token_manager.py`)

- **定位**：策略协调层，管理缓存和回退策略
- **核心功能**：
  - `count_tokens()` — 四层回退
  - `is_overflow()` — 溢出检测（预留 `min(20_000, max_output_tokens)`）
  - `record_api_usage()` — 从 API chunk 解析 usage 并保存为 ground truth
  - `measure_baseline()` — 测量新会话基线
  - `reset_cache()` — 状态变更时清空缓存
- **不再负责**：具体的估算公式（已下沉到 TokenEstimator）

### 4.4 TokenBaselineMeasurer (`services/token_baseline.py`)

- **定位**：测量"还没开始对话就消耗了多少 token"
- **测量项**：system prompt + tool definitions + runtime context
- **缓存**：按 session_id 全局缓存，避免重复测量

---

## 5. 重构后的关键改进

### 5.1 PreciseTokenizer 依赖注入

**重构前**：`TokenEstimator` 内部通过 `_get_precise()` 懒加载自己的 `PreciseTokenizer`

**重构后**：`TokenManager` 创建 `PreciseTokenizer` 实例，通过构造函数注入给 `TokenEstimator`

```python
# 重构后
self._precise_tokenizer = get_precise_tokenizer(base_url=base_url, model_name=model_name)
self._token_estimator = TokenEstimator(
    base_url=base_url,
    model_name=model_name,
    precise_tokenizer=self._precise_tokenizer,
)
```

好处：
- 只有一个 `PreciseTokenizer` 实例，HTTP 探测结果和缓存全局一致
- `TokenEstimator` 不依赖 `base_url` 来创建 tokenizer，职责更纯粹

### 5.2 Magic Number 集中

**重构前**：`+12`、`+4`、`×1.08`、`×1.5` 分散在 `TokenManager._heuristic_count_tokens()` 和 `_estimate_messages_delta()`

**重构后**：全部提升为 `TokenEstimator` 的类常量，并在 `estimate_conversation()` 中统一应用

```python
# TokenManager 不再需要手写这些逻辑
def _heuristic_count_tokens(self) -> int:
    is_cloud_api = bool(self._precise_tokenizer and self._precise_tokenizer.base_url)
    system_msg = self._build_system_message()
    return self._token_estimator.estimate_conversation(
        system_msg=system_msg.content,
        messages=self.messages,
        tools=self.tools,
        is_cloud_api=is_cloud_api,
    )
```

### 5.3 TokenUsage 统一

**重构前**：`query_engine.py` 和 `query/token_manager.py` 各定义一份 `TokenUsage`

**重构后**：`query_engine.py` 的 `TokenUsage` 已删除，改为从 `token_manager` 导入

```python
from .query.token_manager import TokenManager, TokenUsage
```

---

## 6. 相关文件

| 文件 | 职责 |
|------|------|
| `src/pilotcode/query/token_manager.py` | 策略协调层：四层回退、缓存、溢出检测 |
| `src/pilotcode/services/token_estimation.py` | 统一估算层：启发式算法、修正因子、预算状态 |
| `src/pilotcode/services/precise_tokenizer.py` | 精确计数层：后端 `/tokenize` 调用 |
| `src/pilotcode/services/token_baseline.py` | 基线测量层：system + tools 基线 |
| `src/pilotcode/query_engine.py` | 入口层：委托 TokenManager，不再定义 TokenUsage |
| `src/pilotcode/utils/token_utils.py` | 遗留 API（半废弃），未接入核心体系 |

---

## 7. 未来改进方向

1. **废弃 `token_utils.py`**：将其公开 API 迁移为 `TokenEstimator` 的兼容 shim，最终删除文件
2. **`estimate_conversation()` 支持 vision 内容**：对多模态 message 中的 image block 进行 token 估算
3. **PreciseTokenizer 支持更多后端**：如 Gemini 的 `countTokens` API、OpenAI 的 `tokenize` 接口
