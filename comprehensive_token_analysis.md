# Comprehensive Token Calculation and Display Analysis for PilotCode

## Overview
PilotCode implements a sophisticated token management system that combines precise backend tokenization with heuristic fallbacks for accurate token estimation, while providing comprehensive display mechanisms to monitor context window usage.

## Token Calculation Logic

### Core Components
1. **TokenEstimator** (`src/pilotcode/services/token_estimation.py`)
   - Primary interface for token estimation of text and chat messages
   - OpenCode-style approach: prefer exact token counts from backend tokenizers, fall back to heuristics when necessary
   - Priority order:
     1. Precise backend tokenizer (llama.cpp / vLLM / Ollama / transformers / tiktoken)
     2. Heuristic estimation

2. **PreciseTokenizer** (`src/pilotcode/services/precise_tokenizer.py`)
   - Backend support:
     - llama.cpp: POST /tokenize endpoint
     - vLLM: POST /tokenize endpoint
     - Ollama: POST /api/tokenize endpoint
     - Cloud APIs: Offline fallback to tiktoken or transformers
   - Caching for performance optimization
   - Message tokenization for chat messages with different backends

3. **Heuristic Estimation**
   - Character-based estimation using ratios (CHARS_PER_TOKEN = 4.0, CODE_CHARS_PER_TOKEN = 3.5)
   - CJK character handling with provider-specific ratios
   - Word-based estimation (WORDS_PER_TOKEN = 0.75)
   - Special token handling for counting special characters and whitespace patterns
   - Weighted formula combining character, word, and special token estimates

### Algorithm Details
- **Precise Tokenization Flow**: Try backend-specific endpoints first, fall back to transformers, use tiktoken as last resort
- **Heuristic Estimation Formula**:
```python
estimate = int(
    char_estimate * 0.6 + word_estimate * 0.3 + (special_tokens + whitespace_runs) * 0.1
)
```
- **Token Budget Management**: Implements budget status tracking with warning thresholds (ok, caution, warning, exceeded)

## Token Display Mechanisms

### Core Services
1. **Token Estimation Service**: Provides `get_budget_status()` for contextual token usage reporting
2. **Precise Tokenizer Service**: Supports multiple backends with caching for performance

### User Interface Display
1. **Status Bar Component** (`src/pilotcode/tui_v2/components/status/bar.py`)
   - Real-time token usage display in bottom status bar
   - Context window usage percentage (e.g., "context: 56.3% (147.5k/262.1k)")
   - Session ID for conversation tracking
   - Processing status indicators

2. **Token Display Integration** (`src/pilotcode/tui_v2/screens/session.py`)
   - Real-time updates during conversation
   - Integration with controller's `get_token_info()` method
   - Context information updates when messages change

### Key Features
- **Real-time Monitoring**: Continuous token count updates during conversation
- **Context Window Awareness**: Shows percentage usage of available context window
- **Multiple Backend Support**: Uses exact token counts from backend APIs when possible
- **Fallback Mechanisms**: Heuristic estimation when precise tokenization isn't available
- **Visual Feedback**: Processing state changes visual appearance of status bar

## Integration and Usage
- Token counts updated on every message exchange
- Context window information displayed alongside token usage
- Session identifiers shown for tracking conversations
- Processing state indicated visually in the status bar
- Integrates with query engine's token counting functions through controller interface