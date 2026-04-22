# Model Configuration & Capability Verification

PilotCode supports managing model parameters through an external JSON configuration file, and can automatically probe the actual capabilities of local models at runtime (context window, tool support, vision support, etc.).

---

## Configuration File

All preset model static configurations are stored in `config/models.json` at the repository root:

```json
{
  "models": {
    "deepseek": {
      "name": "deepseek",
      "display_name": "DeepSeek",
      "provider": "deepseek",
      "base_url": "https://api.deepseek.com/v1",
      "default_model": "deepseek-chat",
      "description": "DeepSeek V3.2 - Strong coding capabilities",
      "supports_tools": true,
      "supports_vision": false,
      "max_tokens": 8192,
      "context_window": 128000,
      "env_key": "DEEPSEEK_API_KEY"
    }
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Model identifier, used by `--model` and config files |
| `display_name` | string | Human-readable name shown during startup verification |
| `provider` | string | Provider category: `openai`, `anthropic`, `deepseek`, `qwen`, `custom`, etc. |
| `base_url` | string | API base URL; may be empty for local models |
| `default_model` | string | Actual model ID sent in API requests (e.g. `deepseek-chat`) |
| `description` | string | Short description |
| `supports_tools` | bool | Whether Function Calling / tool use is supported |
| `supports_vision` | bool | Whether image / multimodal input is supported |
| `max_tokens` | int | Maximum output tokens per request |
| `context_window` | int | Total context size (input + output) |
| `env_key` | string | Default environment variable name for this model |

---

## Modifying Model Parameters

### 1. Edit an Existing Model

Edit `config/models.json` directly. For example, update DeepSeek's context window:

```json
{
  "deepseek": {
    "context_window": 256000,
    "max_tokens": 16384
  }
}
```

Changes take effect immediately without restart. PilotCode reloads this file on every startup and every `config --list` invocation.

### 2. Add a New Model

Add a new key under the `models` object:

```json
{
  "models": {
    "my-local-llm": {
      "name": "my-local-llm",
      "display_name": "My Local LLM",
      "provider": "custom",
      "base_url": "http://localhost:8080/v1",
      "default_model": "default",
      "description": "Custom local deployment",
      "supports_tools": true,
      "supports_vision": false,
      "max_tokens": 4096,
      "context_window": 32768,
      "env_key": ""
    }
  }
}
```

After adding, select it via the interactive wizard or CLI:

```bash
python3 -m pilotcode configure --model my-local-llm
```

### 3. Modify Runtime Parameters via Config Command

In addition to editing the JSON file, you can use the `config` command:

```bash
# View full current config (including model capabilities)
python3 -m pilotcode config --list

# Change default model
python3 -m pilotcode config --set default_model --value qwen

# Override base URL (useful for local models or proxies)
python3 -m pilotcode config --set base_url --value http://localhost:11434/v1

# Enable/disable auto-compaction
python3 -m pilotcode config --set auto_compact --value true
```

---

## `config --list` Command

`config --list` displays not only user settings, but also the current model's static capabilities and runtime-probed values:

```bash
$ python3 -m pilotcode config --list

Global Configuration:
  Theme: default
  Verbose: False
  Auto Compact: True
  Default Model: deepseek
  Model Provider: deepseek
  Base URL: Default
  API Key: ***set***

Model Capability (Static Config):
  Display Name: DeepSeek
  API Model:    deepseek-chat
  Provider:     deepseek
  Context:      128K
  Max Tokens:   8K
  Tools:        ✓
  Vision:       ✗
  Source: static

Config file: /home/user/.config/pilotcode/settings.json
```

### Runtime Probing for Local Models

If the configured model uses a local address (e.g. `localhost`, `127.0.0.1`, `:11434`, `192.168.x.x`), PilotCode automatically probes the backend for actual capabilities:

```bash
$ python3 -m pilotcode config --list
...

Probing local model runtime info...
Model Capability (Runtime Detected):
  Context:      128K
  Max Tokens:   8K
  Tools:        ✓
  Vision:       ✗
  Backend:      llama-server
```

#### Supported Backends for Probing

| Backend | Endpoint | Extracted Field |
|---------|----------|-----------------|
| **llama.cpp / llama-server** | `/props` | `default_generation_settings.n_ctx` |
| **Ollama** | `/api/show` | `model_info.*.context_length` |
| **LiteLLM** | `/model/info` | `max_input_tokens` |
| **OpenAI-compatible** | `/v1/models` | Model list (no detailed capabilities) |

Probing proceeds in priority order and stops once `context_window` is successfully extracted. If probing fails, the static value from `config/models.json` is used as fallback.

---

## Dynamic Context Window Application

The `context_window` in model configuration is not just for display — it is dynamically read by multiple core modules as the hard upper limit for context management:

### Auto-Compaction Threshold

All context management modules uniformly use **80%** as the auto-compaction trigger threshold:

| Module | Threshold Source | Behavior |
|--------|-----------------|----------|
| `query_engine` | `get_model_context_window()` | Triggers `auto_compact_if_needed()` at 80% |
| `context_manager` | `ContextConfig.max_tokens` | Warns at 75%, triggers `auto_compact` at 80% |
| `intelligent_compact` | Runtime `ctx * 0.80` | ClaudeCode-style compaction |
| `context_compression` | Runtime `ctx * 0.70` | Target token count for summarization |
| `simple_cli` | `get_model_context_window()` | Token usage check |

This means: when you change `context_window` from 128K to 256K, all module thresholds automatically scale — no code changes required.

### Interactive Inspection

During a conversation, use these commands to inspect and control context:

```
> /model
Current Model: deepseek (DeepSeek)
  Context Window: 128K
  Max Output:     8K
  Tools:          ✓
  Vision:         ✗

> /status
Conversation Context:
  Messages:   12
  Tokens:     3240 / 128000 (2%)
  Remaining:  124760
  [░░░░░░░░░░░░░░░░░░░░] 2%

> /compact
Context compacted:
  Messages:  24 -> 10 (14 removed)
  Tokens:    89000 -> 42000 (47000 saved)
  Usage:     69% -> 32%
```

---

## Configuration Precedence

When the same parameter exists in multiple sources, the following priority applies (highest to lowest):

1. **Command-line arguments** (e.g. `--model`, `--base-url`)
2. **Environment variables** (e.g. `DEEPSEEK_API_KEY`, `PILOTCODE_MODEL`)
3. **User config file** (`~/.config/pilotcode/settings.json`)
4. **Static model config** (`config/models.json`)
5. **Built-in defaults**

---

## Related Documents

- [Configuration Guide](../guides/llm-setup.md) - LLM setup and API key configuration
- [Quick Start](../../QUICKSTART_EN.md) - Interactive wizard usage
- [Context Compaction](./context-compaction.md) - Smart compaction mechanism details
