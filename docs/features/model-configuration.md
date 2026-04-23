# 模型配置与能力验证

PilotCode 支持通过外部 JSON 配置文件管理模型参数，并能在运行时自动探测本地模型的实际能力（上下文窗口、工具支持、视觉支持等）。

---

## 配置文件

所有预置模型的静态配置存储在仓库根目录的 `config/models.json` 中：

```json
{
  "models": {
    "deepseek": {
      "name": "deepseek",
      "display_name": "DeepSeek (深度求索)",
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

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 模型标识名，用于 `--model` 参数和配置文件中引用 |
| `display_name` | string | 展示名称，启动验证时会显示 |
| `provider` | string | 提供商类别：`openai`、`anthropic`、`deepseek`、`qwen`、`custom` 等 |
| `base_url` | string | API 基础地址，本地模型可留空或在配置中覆盖 |
| `default_model` | string | 实际请求时使用的模型 ID（如 `deepseek-chat`） |
| `description` | string | 模型描述 |
| `supports_tools` | bool | 是否支持 Function Calling / 工具调用 |
| `supports_vision` | bool | 是否支持图片/多模态输入 |
| `max_tokens` | int | 单次输出最大 Token 数 |
| `context_window` | int | 上下文窗口总大小（输入 + 输出） |
| `env_key` | string | 该模型默认使用的环境变量名 |

---

## 修改模型参数

### 1. 修改现有模型

直接编辑 `config/models.json`，例如将 DeepSeek 的上下文窗口更新为最新值：

```json
{
  "deepseek": {
    "context_window": 256000,
    "max_tokens": 16384
  }
}
```

修改保存后立即生效，无需重启。PilotCode 在每次启动和每次执行 `config --list` 时都会重新读取该文件。

也可以通过代码动态更新：

```python
from pilotcode.utils.models_config import update_model_in_json

# 更新指定模型的字段（直接写回 config/models.json 并刷新内存缓存）
update_model_in_json("ollama", {
    "context_window": 8192,
    "max_tokens": 2048
})
```

### 2. 添加新模型

在 `models` 对象中新增一个键值对即可：

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

添加后，通过交互式配置向导或命令行即可选择该模型：

```bash
python3 -m pilotcode configure --model my-local-llm
```

### 3. 通过配置命令修改运行时参数

除了修改 JSON 文件，还可以通过 `config` 命令修改全局配置：

```bash
# 查看当前完整配置（含模型能力）
python3 -m pilotcode config --list

# 修改默认模型
python3 -m pilotcode config --set default_model --value qwen

# 修改 Base URL（适用于本地模型或代理）
python3 -m pilotcode config --set base_url --value http://localhost:11434/v1

# 启用/禁用自动压缩
python3 -m pilotcode config --set auto_compact --value true
```

---

## `config --list` 命令详解

`config --list` 不仅显示用户配置，还会展示当前模型的静态能力和运行时探测结果：

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
  Display Name: DeepSeek (深度求索)
  API Model:    deepseek-chat
  Provider:     deepseek
  Context:      128K
  Max Tokens:   8K
  Tools:        ✓
  Vision:       ✗
  Source: static

Config file: /home/user/.config/pilotcode/settings.json
```

### 本地模型的运行时探测

如果配置的模型使用本地地址（如 `localhost`、`127.0.0.1`、`:11434`、`10.x.x.x`、`172.16-31.x.x`、`192.168.x.x` 等），PilotCode 会自动探测后端实际能力：

```bash
$ python3 -m pilotcode config --list
...

Probing local model runtime info...
Model Capability (Runtime Detected):
  Display Name: qwen2.5:14b
  Provider:     qwen
  Context:      262K
  Max Tokens:   8K
  Tools:        ✓
  Vision:       ✗
  Backend:      llama-server
```

#### 支持的探测后端

| 后端 | 探测端点 | 提取字段 |
|------|----------|----------|
| **llama.cpp / llama-server** | `/props` | `n_ctx`, `model_path`, `modalities` |
| **Ollama** | `/api/show` | `context_length`, `capabilities` |
| **vLLM** | `/v1/models` | `max_model_len`, `max_tokens` |
| **LiteLLM** | `/model/info` | `max_input_tokens`, `max_output_tokens` |
| **OpenAI-compatible** | `/v1/models` | `context_length`, `max_tokens` 等 |

探测按优先级依次尝试，成功获取 `context_window` 即停止。若探测失败，会回退到 `config/models.json` 中的静态配置值。

#### Provider 自动推断

对于本地模型，系统会根据模型名自动推断 Provider：

| 模型名关键词 | 推断 Provider |
|-------------|--------------|
| `qwen` | `qwen` |
| `deepseek` | `deepseek` |
| `glm` | `zhipu` |
| `moonshot` | `moonshot` |
| `baichuan` | `baichuan` |
| `doubao` | `doubao` |
| 其他 | `custom` |

#### 差异检测与交互更新

当探测值与静态配置不一致时，运行时检测部分会以**红色**高亮差异字段，并显示配置中的原值（灰色）。例如：

```
Model Capability (Runtime Detected):
  Display Name: qwen2.5:14b
  Provider:     [red]qwen[/red]  (config: custom)
  Context:      [red]262K[/red]  (config: 128K)
```

随后会提示：

```
⚠ Detected mismatches with config file:
  default_model: custom → qwen2.5:14b
  model_provider: custom → qwen
  context_window: 128000 → 262144
Update config to match detected values? [Y/n]:
```

确认后，系统会同时更新：
- `~/.config/pilotcode/settings.json`（`default_model`、`model_provider`）
- `config/models.json`（`context_window`、`max_tokens`）

---

## 上下文窗口的动态应用

模型配置中的 `context_window` 不仅用于展示，而是被多个核心模块动态读取，作为上下文管理的硬上限：

### 自动压缩阈值

所有上下文管理模块统一采用 **80%** 作为自动压缩触发阈值：

| 模块 | 阈值来源 | 行为 |
|------|----------|------|
| `query_engine` | `get_model_context_window()` | 达到 80% 时触发 `auto_compact_if_needed()` |
| `context_manager` | `ContextConfig.max_tokens` | 达到 75% 警告，80% 触发 `auto_compact` |
| `intelligent_compact` | 运行时计算 `ctx * 0.80` | ClaudeCode 风格压缩 |
| `context_compression` | 运行时计算 `ctx * 0.70` | 摘要压缩的目标 Token 数 |
| `simple_cli` | `get_model_context_window()` | Token 使用量检查 |

这意味着：当你把 `context_window` 从 128K 改为 256K，所有模块的压缩阈值会自动同步调整，无需修改代码。

### 交互式查看

在对话过程中，可以使用以下命令查看和管控上下文：

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

## 配置优先级

当同一参数存在多个来源时，按以下优先级生效（高到低）：

1. **命令行参数**（如 `--model`、`--base-url`）
2. **环境变量**（如 `DEEPSEEK_API_KEY`、`PILOTCODE_MODEL`）
3. **用户配置文件**（`~/.config/pilotcode/settings.json`）
4. **静态模型配置**（`config/models.json`）
5. **默认值**

---

## 相关文档

- [配置指南](../guides/llm-setup.md) - LLM 接入与 API Key 设置
- [快速开始](../../QUICKSTART.md) - 交互式配置向导使用说明
- [上下文压缩](./context-compaction.md) - 智能压缩的详细机制
