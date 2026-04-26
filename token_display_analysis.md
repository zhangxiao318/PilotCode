# Token Display Mechanisms in PilotCode

## Overview
PilotCode implements comprehensive token counting and display mechanisms to help users monitor context window usage. The system uses both precise backend tokenizers and heuristic fallbacks for accurate token estimation.

## Core Token Services

### 1. Token Estimation Service (`src/pilotcode/services/token_estimation.py`)
- Implements `TokenEstimator` class for estimating token counts
- Uses precise backend tokenizers when available (llama.cpp, vLLM, Ollama, cloud APIs)
- Falls back to heuristic estimation for unsupported backends
- Provides `get_budget_status()` for contextual token usage reporting

### 2. Precise Tokenizer Service (`src/pilotcode/services/precise_tokenizer.py`)
- Implements `PreciseTokenizer` class for exact token counting
- Supports multiple backends including:
  - llama.cpp with `/tokenize` endpoint
  - vLLM with `/tokenize` endpoint
  - Ollama with `/api/tokenize` endpoint
  - Transformers and tiktoken for offline fallbacks
- Caches results to avoid repeated requests

## User Interface Display

### Status Bar Component (`src/pilotcode/tui_v2/components/status/bar.py`)
- Displays real-time token usage in the bottom status bar
- Shows context window usage percentage (e.g., "context: 56.3% (147.5k/262.1k)")
- Displays session ID for reference
- Shows processing status when active
- Uses Rich Table for proper three-column layout (left, center, right)

### Token Display Integration (`src/pilotcode/tui_v2/screens/session.py`)
- Updates token count in real-time during conversation
- Integrates with controller's `get_token_info()` method
- Displays token usage in status bar during message processing
- Updates context information when messages are added or removed

## Key Features
1. **Real-time Monitoring**: Token count updates continuously during conversation
2. **Context Window Awareness**: Shows percentage usage of available context window
3. **Multiple Backend Support**: Uses exact token counts from backend APIs when possible
4. **Fallback Mechanisms**: Heuristic estimation when precise tokenization isn't available
5. **Visual Feedback**: Processing state changes visual appearance of status bar

## Usage Patterns
- Token counts are updated on every message exchange
- Context window information is displayed alongside token usage
- Session identifiers are shown for tracking conversations
- Processing state is indicated visually in the status bar

## Implementation Details
The token display system integrates with the query engine's token counting functions and is updated through the controller's token information interface. The status bar component reacts to changes in token count, processing state, and context information to provide real-time feedback to users.