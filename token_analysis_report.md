# Unified Token Analysis Report for PilotCode

## Overview
This report combines the token calculation and display mechanisms implemented in PilotCode, providing a comprehensive view of how token counting is performed and presented to users.

## Token Calculation System

### Core Components
1. **TokenEstimator** (src/pilotcode/services/token_estimation.py)
   - Primary interface for token estimation with OpenCode-style approach
   - Prioritizes exact token counts from backend tokenizers over heuristic estimates
   - Supports multiple backends: llama.cpp, vLLM, Ollama, cloud APIs, transformers, and tiktoken

2. **PreciseTokenizer** (src/pilotcode/services/precise_tokenizer.py)
   - Implements exact token counting for various backends
   - Caches results to improve performance
   - Provides message tokenization with different backend support

3. **Heuristic Estimation**
   - Character-based estimation using CHARS_PER_TOKEN = 4.0 and CODE_CHARS_PER_TOKEN = 3.5
   - Word-based estimation with WORDS_PER_TOKEN = 0.75
   - Special token handling with weighted formula combining estimates

### Algorithm Details
- Precise tokenization flow: backend endpoints → transformers → tiktoken fallback
- Heuristic formula: int(char_estimate * 0.6 + word_estimate * 0.3 + (special_tokens + whitespace_runs) * 0.1)
- Budget management with status tracking (ok, caution, warning, exceeded)

## Token Display System

### User Interface Components
1. **Status Bar** (src/pilotcode/tui_v2/components/status/bar.py)
   - Real-time token usage display in bottom status bar
   - Shows context window percentage (e.g., "context: 56.3% (147.5k/262.1k)")
   - Displays session ID and processing status
   - Uses Rich Table for three-column layout

2. **Session Screen Integration** (src/pilotcode/tui_v2/screens/session.py)
   - Updates token counts during conversation
   - Integrates with controller's get_token_info() method
   - Provides real-time feedback on token usage

### Key Features
- Real-time monitoring of token usage during conversation
- Context window awareness with percentage display
- Multiple backend support with fallback mechanisms
- Visual feedback through status bar processing state
- Integration with context compression service

## System Integration
The token calculation service seamlessly integrates with the display system through:
- Context compression service using estimate_tokens function
- Real-time updates in session screen
- Status bar component that reacts to token count changes
- Controller interface for token information access

## Implementation Benefits
- Accurate token estimation through precise backend tokenizers
- Performance optimization via caching
- User-friendly interface with real-time feedback
- Robust fallback mechanisms for unsupported backends
- Context-aware token management