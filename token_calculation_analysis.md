# Token Calculation Methods in PilotCode

This document summarizes all token calculation methods, their parameters, return values, and usage patterns found in the PilotCode codebase.

## 1. Token Estimation Service

### `TokenEstimator` Class

**Purpose**: Provides token estimation with preference for exact counts from backend tokenizers.

**Key Methods**:

#### `estimate(text: str, is_code: bool = False, provider: str = "") -> int`
- **Parameters**:
  - `text`: Text string to estimate tokens for
  - `is_code`: Boolean flag indicating if text is code (affects heuristic calculation)
  - `provider`: Cloud provider name for CJK token ratio adjustments
- **Return Value**: Estimated token count (int)
- **Usage Pattern**: Tries precise backend tokenizer first, falls back to heuristic estimation

#### `estimate_messages(messages: list[dict[str, Any]]) -> int`
- **Parameters**:
  - `messages`: List of message dictionaries
- **Return Value**: Estimated token count for all messages (int)
- **Usage Pattern**: Tries backend message tokenization first, falls back to text rendering + overhead

#### `get_budget_status(current_tokens: int, max_tokens: int, warning_threshold: float = 0.8) -> dict[str, Any]`
- **Parameters**:
  - `current_tokens`: Current token usage
  - `max_tokens`: Maximum allowed tokens
  - `warning_threshold`: Threshold for warning status (default 0.8)
- **Return Value**: Dictionary with budget status information
- **Usage Pattern**: Provides token budget status with different status levels (ok, caution, warning, exceeded)

### Global Functions

#### `get_token_estimator(base_url: str = "", model_name: str = "") -> TokenEstimator`
- **Parameters**:
  - `base_url`: Backend base URL for precise tokenization
  - `model_name`: Model name for backend-specific tokenization
- **Return Value**: Global TokenEstimator instance
- **Usage Pattern**: Singleton pattern for accessing token estimator

#### `estimate_tokens(text: str, is_code: bool = False) -> int`
- **Parameters**:
  - `text`: Text string to estimate tokens for
  - `is_code`: Boolean flag indicating if text is code
- **Return Value**: Quick estimated token count
- **Usage Pattern**: Convenience function for quick token estimation

## 2. Precise Tokenizer Service

### `PreciseTokenizer` Class

**Purpose**: Provides exact token counting using backend tokenizers.

**Key Methods**:

#### `count_text(text: str) -> int | None`
- **Parameters**:
  - `text`: Text string to count tokens for
- **Return Value**: Exact token count or None if no backend succeeds
- **Usage Pattern**: Tries llama.cpp, vLLM, Ollama, transformers, and tiktoken backends in order

#### `count_messages(messages: list[dict[str, Any]]) -> int | None`
- **Parameters**:
  - `messages`: List of message dictionaries
- **Return Value**: Exact token count or None if no backend succeeds
- **Usage Pattern**: Handles message tokenization with different backend approaches

#### `count_messages_with_tools(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int | None`
- **Parameters**:
  - `messages`: List of message dictionaries
  - `tools`: Optional list of tool definitions
- **Return Value**: Exact token count or None if no backend succeeds
- **Usage Pattern**: Handles messages with tool schemas, particularly for vLLM and llama.cpp backends

### Backend-Specific Methods

The precise tokenizer implements methods for:
- **llama.cpp**: `_try_llamacpp_tokenize`, `_try_llamacpp_count_messages`
- **vLLM**: `_try_vllm_tokenize`, `_try_vllm_count_messages`
- **Ollama**: `_try_ollama_tokenize`, `_try_ollama_count_messages`
- **Offline fallbacks**: `_try_transformers`, `_try_tiktoken`

## 3. Query Engine Token Usage

### `QueryEngine` Class Methods

#### `count_tokens() -> int`
- **Parameters**: None
- **Return Value**: Total token count for current conversation
- **Usage Pattern**: Uses OpenCode-style priority:
  1. API-reported usage (ground truth)
  2. Precise backend tokenizer
  3. Heuristic estimation

#### `is_overflow() -> bool`
- **Parameters**: None
- **Return Value**: Boolean indicating if context overflow occurred
- **Usage Pattern**: Checks against usable context window

#### `get_token_budget() -> dict[str, Any]`
- **Parameters**: None
- **Return Value**: Token budget status information
- **Usage Pattern**: Returns current budget status using `TokenEstimator.get_budget_status`

## 4. Usage Patterns

### Priority Order for Token Counting:
1. **API-reported usage** (most authoritative)
2. **Precise backend tokenizer** (llama.cpp, vLLM, Ollama, transformers, tiktoken)
3. **Heuristic estimation** (fallback)

### Token Calculation Context:
- **System prompt**: Always counted
- **Conversation messages**: Counted individually
- **Tool definitions**: Counted when tools are enabled
- **Message overhead**: Added for each message

## 5. Token Estimation Heuristics

The heuristic estimation uses a weighted combination of:
- Character count (adjusted for code vs regular text)
- Word count
- Special character count
- Whitespace patterns
- CJK (Chinese, Japanese, Korean) character handling with provider-specific ratios

## 6. Token Budget Management

The system tracks token usage against context windows and provides:
- Real-time budget status
- Overflow detection
- Auto-compaction triggers based on token thresholds