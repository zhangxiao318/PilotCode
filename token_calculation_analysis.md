# Token Calculation Logic Analysis

## Overview
The codebase implements a sophisticated token calculation system that combines precise backend tokenization with heuristic fallbacks.

## Key Components

### 1. TokenEstimator (src/pilotcode/services/token_estimation.py)
- **Primary Interface**: Provides token estimation for text and chat messages
- **Approach**: OpenCode-style - prefer exact token counts from backend tokenizers, fall back to heuristics when necessary
- **Priority Order**:
  1. Precise backend tokenizer (llama.cpp / vLLM / Ollama / transformers / tiktoken)
  2. Heuristic estimation

### 2. PreciseTokenizer (src/pilotcode/services/precise_tokenizer.py)
- **Backend Support**:
  - llama.cpp: POST /tokenize endpoint
  - vLLM: POST /tokenize endpoint
  - Ollama: POST /api/tokenize endpoint
  - Cloud APIs: Offline fallback to tiktoken or transformers
- **Caching**: Results are cached to avoid repeated requests
- **Message Tokenization**: Supports counting tokens for chat messages with different backends

### 3. Heuristic Estimation (TokenEstimator._heuristic_estimate)
- **Character-based**: Uses ratios (CHARS_PER_TOKEN = 4.0, CODE_CHARS_PER_TOKEN = 3.5)
- **CJK Handling**: Provider-specific ratios for CJK characters
- **Word-based**: WORDS_PER_TOKEN = 0.75
- **Special Token Handling**: Counts special characters and whitespace patterns
- **Weighted Formula**: Combines character, word, and special token estimates

### 4. Context Compression (src/pilotcode/services/context_compression.py)
- **Token Usage**: Uses `estimate_tokens` function from token_estimation service
- **Strategy**: 
  1. Keep system message and recent messages
  2. Summarize middle section if needed
  3. Truncate oldest non-essential messages

## Algorithm Details

### Precise Tokenization Flow
1. Try backend-specific tokenize endpoints first
2. Fall back to transformers tokenizer for local models
3. Use tiktoken as last resort for OpenAI-compatible tokenization

### Heuristic Estimation Formula
```python
estimate = int(
    char_estimate * 0.6 + word_estimate * 0.3 + (special_tokens + whitespace_runs) * 0.1
)
```

### Token Budget Management
- Implements budget status tracking with warning thresholds
- Supports different status levels: ok, caution, warning, exceeded

## Key Features
- Multi-backend support with fallbacks
- Caching for performance
- Context-aware token counting (messages vs text)
- Priority-based message retention in compression
- CJK character handling
- Systematic approach to token estimation that balances accuracy and performance