# 模型配置与能力验证

PilotCode 支持通过外部 JSON 配置文件管理模型参数，并能在运行时自动探测本地模型的实际能力（上下文窗口、工具支持、视觉支持等）。

---

## 配置文件的三个层级

| 层级 | 文件位置 | 作用 |
|------|---------|------|
| **模型静态配置** | `config/models.json`（项目内） | 定义云端/远程模型的默认参数（base_url、context_window、max_tokens 等） |
| **用户全局配置** | `~/.config/pilotcode/settings.json` | 用户实际使用的配置，**本地模型的唯一配置来源** |
| **项目级配置** | `.pilotcode.json`（工作目录或 git 根目录） | 项目特定的工具白名单、MCP 服务器等 |

> **重要区别**：
> - **远程模型**（OpenAI、DeepSeek 等）：`models.json` 提供默认值，`settings.json` 可覆盖。
> - **本地模型**（Ollama、vLLM）：**所有配置必须写在 `settings.json` 中**，`models.json` 不参与本地模型的配置加载。

---

## 配置加载的完整流程

### 远程模型

```
settings.json ──► GlobalConfig(**data)
                      │
                      ▼
              __post_init__()  从 models.json 补全缺失的 base_url / context_window
                      │
                      ▼
         _apply_env_overrides()  环境变量覆盖
                      │
                      ▼
              设置 model_provider（从 models.json 读取）
```

### 本地模型（ollama / vLLM）

```
settings.json ──► GlobalConfig(**data)
                      │
                      ▼
              __post_init__()  检测到本地模型 → 跳过 models.json，不自动填充
                      │
                      ▼
         _apply_env_overrides()  环境变量覆盖
                      │
                      ▼
              启动时探测 API → 发现缺失/不一致 → 提示确认 → 自动修复 settings.json
```

### 步骤 1：读取 `settings.json`

```json
{
  "default_model": "vllm",
  "base_url": "http://172.19.202.70:8080/v1",
  "context_window": 204800
}
```

### 步骤 2：`GlobalConfig.__post_init__()` 自动补全

| 条件 | 远程模型 | 本地模型（ollama / vLLM） |
|------|---------|------------------------|
| `default_model` 为空 | 设为 `deepseek` | 设为 `deepseek` |
| `base_url` 为空 | 从 `models.json` 填充 | **不填充**（保持空或等待用户配置） |
| `context_window` ≤ 0 | 从 `models.json` 填充 | **不填充**（保持 0，启动时探测） |

### 步骤 3：环境变量覆盖

以下环境变量会覆盖 `settings.json` 中的值：

| 环境变量 | 覆盖字段 |
|---------|---------|
| `PILOTCODE_API_KEY` | `api_key` |
| `PILOTCODE_BASE_URL` | `base_url` |
| `PILOTCODE_MODEL` | `default_model` |
| `PILOTCODE_CONTEXT_WINDOW` | `context_window` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | `api_key` / `base_url`（兼容旧变量）|

此外，如果环境中有 `ANTHROPIC_API_KEY`、`DEEPSEEK_API_KEY` 等模型专用 key，`get_model_from_env()` 会推断出对应模型名。若 `default_model` 为空或等于默认模型 `deepseek`，则自动覆盖为推断出的模型。

### 步骤 4：设置 `model_provider`

根据 `default_model` 从 `models.json` 中查找对应的 `provider` 字段，自动填充到 `GlobalConfig.model_provider`。

---

## 配置文件详解

### `config/models.json`

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
| `provider` | string | 提供商类别：`openai`、`anthropic`、`deepseek`、`qwen`、`vllm`、`custom` 等 |
| `base_url` | string | API 基础地址，本地模型可留空或在配置中覆盖 |
| `default_model` | string | 实际请求时使用的模型 ID（如 `deepseek-chat`） |
| `description` | string | 模型描述 |
| `supports_tools` | bool | 是否支持 Function Calling / 工具调用 |
| `supports_vision` | bool | 是否支持图片/多模态输入 |
| `max_tokens` | int | **模型单次最大输出 Token 数**（仅作元数据展示，不参与压缩阈值计算） |
| `context_window` | int | **上下文窗口总大小**，用于计算自动压缩阈值（80% / 95%） |
| `env_key` | string | 该模型默认使用的环境变量名 |

> **注意**：`max_tokens` 和 `context_window` 是两个不同的概念。
> - `context_window` = 模型能处理的总 Token 上限（输入 + 输出），用于决定何时触发上下文压缩。
> - `max_tokens` = 模型单次回复的最大输出 Token 数，仅作为元数据展示，不影响压缩逻辑。

---

## 修改模型参数

### 1. 修改现有模型

直接编辑 `config/models.json`，例如将 DeepSeek 的上下文窗口更新为最新值：

```json
{
  "deepseek": {
    "context_window": 256000
  }
}
```

修改保存后立即生效，无需重启。PilotCode 在每次启动和每次执行 `config --list` 时都会重新读取该文件。

也可以通过代码动态更新：

```python
from pilotcode.utils.models_config import update_model_in_json

# 更新指定模型的字段（直接写回 config/models.json 并刷新内存缓存）
update_model_in_json("vllm", {
    "context_window": 204800
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

`config --list` 不仅显示用户配置，还会展示当前模型的运行时探测结果：

### 远程模型

```bash
$ python3 -m pilotcode config --list

Global Configuration:
  Theme: default
  Verbose: False
  Auto Compact: True
  Default Model: deepseek
  Model Provider: deepseek
  Base URL: https://api.deepseek.com/v1
  API Key: ***set***
  Context Window: 128000

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

### 本地模型

```bash
$ python3 -m pilotcode config --list

Global Configuration:
  Theme: default
  Verbose: False
  Auto Compact: True
  Default Model: qwen-coder
  Model Provider: vllm
  Base URL: http://172.19.202.70:8080/v1
  API Key: ***set***
  Context Window: 204800

Probing local model runtime info...
Model Capability (Runtime Detected):
  Display Name: qwen-coder
  Provider:     vllm
  Context:      204K
  Vision:       ✗
  Backend:      vllm

Config file: /home/user/.config/pilotcode/settings.json
```

> **注意**：本地模型**不显示** "Model Capability (Static Config)"，因为 `models.json` 不参与本地模型配置。

### 本地模型的运行时探测

如果配置的模型使用本地/内网地址，PilotCode 会自动探测后端实际能力。本地地址的判定标准（RFC1918）：

- `localhost`、`127.0.0.1`
- Ollama 默认端口 `:11434`
- `10.x.x.x`
- `172.16.x.x` ~ `172.31.x.x`
- `192.168.x.x`

#### 支持的探测后端

| 后端 | 探测端点 | 提取字段 |
|------|----------|----------|
| **llama.cpp / llama-server** | `/props` | `n_ctx`, `model_path`, `modalities` |
| **Ollama** | `/api/show` | `context_length`, `capabilities` |
| **vLLM** | `/v1/models` | `max_model_len`, `max_tokens`, `model_id` |
| **LiteLLM** | `/model/info` | `max_input_tokens`, `max_output_tokens` |
| **OpenAI-compatible** | `/v1/models` | `context_length`, `max_tokens` 等 |

探测按优先级依次尝试，成功获取 `context_window` 即停止。

#### `/v1` 后缀自动检测

对于 vLLM 等 OpenAI 兼容后端，如果 `base_url` 缺少 `/v1` 后缀（如 `http://host:8080`），`config --list` 会提示：

```
⚠ base_url missing /v1 suffix: http://172.19.202.70:8080
  vLLM and other OpenAI-compatible backends typically expose endpoints
  under /v1 (e.g. /v1/chat/completions).
Auto-append /v1 to base_url? [Y/n]:
```

确认后自动将 `base_url` 更新为 `http://host:8080/v1` 并保存到 `settings.json`。

---

## 差异检测与交互更新

### `config --list` 中的检测

对于本地模型，`config --list` 会对比 `settings.json` 中的配置与探测到的实际能力：

| 检测项 | 未设置时的行为 | 不一致时的行为 |
|--------|--------------|--------------|
| `context_window` | 自动填充探测值 | ⚠️ 提示 mismatch，`[Y/n]` 确认后更新 |
| vLLM `model_id` | — | ⚠️ 提示 mismatch，`[Y/n]` 确认后更新 `default_model` |
| `/v1` 后缀 | — | ⚠️ 提示缺失，`[Y/n]` 确认后自动追加 |

### 启动时的自动检测

每次启动 PilotCode 时，`check_configuration()` 会自动探测本地模型能力。若发现 `settings.json` 中的配置与实际能力不一致：

```
Using local/internal LLM at http://172.19.202.70:8080/v1
⚠ context_window mismatch: settings.json=31072, detected=131072
Update settings.json to match detected value? [Y/n]:
```

按 **回车（默认 Yes）** 即可自动修复，修复后继续正常启动。

> **为什么只更新 `settings.json`？**
> 本地模型的配置以 `settings.json` 为唯一来源。`models.json` 仅用于云端/远程模型的默认值参考，本地模型的任何参数变更都直接写入 `settings.json`。

---

## 上下文窗口的动态应用

模型配置中的 `context_window` 不仅用于展示，而是被多个核心模块动态读取，作为上下文管理的硬上限：

### 自动压缩阈值

所有上下文管理模块统一采用 **80%** 作为自动压缩触发阈值：

| 模块 | 阈值来源 | 行为 |
|------|----------|------|
| `query_engine` | `QueryEngineConfig.context_window` | 达到 80% 时触发 `auto_compact_if_needed()` |
| `context_manager` | `ContextBudget.context_window` | 达到 75% 警告，80% 触发 `auto_compact` |
| `intelligent_compact` | 运行时计算 `ctx * 0.80` | ClaudeCode 风格压缩 |
| `context_compression` | 运行时计算 `ctx * 0.70` | 摘要压缩的目标 Token 数 |
| `simple_cli` | `get_model_context_window()` | Token 使用量检查 |

这意味着：当你把 `context_window` 从 128K 改为 256K，所有模块的压缩阈值会自动同步调整，无需修改代码。

### 交互式查看

在对话过程中，可以使用以下命令查看和管控上下文：

```
> /model
Current Model: vllm (vLLM (Local))
  Context Window: 204K
  Max Output:     4K
  Tools:          ✓
  Vision:         ✗

> /status
Conversation Context:
  Messages:   12
  Tokens:     3240 / 204800 (2%)
  Remaining:  201560
  [░░░░░░░░░░░░░░░░░░░░] 2%

> /compact
Context compacted:
  Messages:  24 -> 10 (14 removed)
  Tokens:    89000 -> 42000 (47000 saved)
  Usage:     43% -> 20%
```

---

## 配置优先级

当同一参数存在多个来源时，按以下优先级生效（高到低）：

1. **命令行参数**（如 `--model`、`--base-url`）
2. **环境变量**（如 `PILOTCODE_MODEL`、`PILOTCODE_BASE_URL`）
3. **用户配置文件**（`~/.config/pilotcode/settings.json`）
4. **静态模型配置**（`config/models.json`）— **仅对远程模型生效**
5. **默认值**

如果你发现配置行为和预期不符，优先检查：

```bash
# 检查环境变量是否覆盖了配置
env | grep -i PILOTCODE
env | grep -i API_KEY
env | grep -i BASE_URL

# 检查用户配置的实际内容
cat ~/.config/pilotcode/settings.json

# 检查模型静态配置（远程模型时有用）
cat config/models.json | jq '.models.deepseek'
```

---

## 本地模型部署指南

### 通过 vLLM 部署任意模型

vLLM 是通用的本地推理服务器，支持任何 HuggingFace 模型：

```bash
# 启动 vLLM 服务
vllm serve Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8 --host 0.0.0.0 --port 8080

# 配置 PilotCode
./pilotcode.sh configure
# → 选择 Local/Custom → vLLM
# → base_url: http://172.19.202.70:8080/v1
```

配置保存后，PilotCode 启动时会自动探测实际模型名称（如 `qwen-coder`）和上下文窗口，并提示是否更新到 `settings.json`。

### 通过 Ollama 部署任意模型

Ollama 支持运行 GGUF 格式的模型，可部署在局域网中的任意主机：

```bash
# 在目标主机启动 Ollama
OLLAMA_HOST=0.0.0.0 ollama serve

# 配置 PilotCode
./pilotcode.sh configure
# → 选择 Local/Custom → Ollama (Local)
# → base_url: http://172.19.202.70:11434/v1
```

> **注意**：Ollama 默认只监听 `127.0.0.1`，局域网访问需要设置 `OLLAMA_HOST=0.0.0.0`。

### 常见模型均可本地部署

| 模型 | 云 API | 本地部署方式 |
|------|--------|-------------|
| DeepSeek | `api.deepseek.com` | `vllm serve deepseek-ai/deepseek-chat` / `ollama run deepseek-r1` |
| Qwen | `dashscope.aliyun.com` | `vllm serve Qwen/Qwen2.5-72B-Instruct` / `ollama run qwen2.5` |
| Llama | 无官方云 API | `vllm serve meta-llama/Llama-3.1-70B` / `ollama run llama3.1` |
| Mistral | `api.mistral.ai` | `vllm serve mistralai/Mistral-7B-Instruct` / `ollama run mistral` |

本地部署时，在 PilotCode 中选择 **vLLM** 或 **Ollama** 即可，无需为每个模型单独添加配置。启动时会自动探测实际能力并提示更新。

---

## 相关文档

- [快速开始](../../QUICKSTART.md) - 交互式配置向导使用说明
- [上下文管理](./context-management.md) - 上下文窗口、Token 监控与压缩机制
- [上下文压缩](./context-compaction.md) - 智能压缩的详细机制
