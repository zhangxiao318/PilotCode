# /config 命令

配置管理命令，用于查看和修改 PilotCode 的设置。

## 作用

- 查看当前配置
- 修改配置项
- 重置配置

## 基本用法

```bash
/config [subcommand]
```

## 子命令

### REPL 斜杠命令 (`/config`)

| 子命令 | 说明 |
|--------|------|
| (无) | 显示当前配置 |
| `set <key> <value>` | 设置配置项 |
| `get <key>` | 获取配置项 |
| `reset` | 重置为默认配置 |

### CLI 命令 (`python3 -m pilotcode config`)

| 选项 | 说明 |
|------|------|
| `--list` / `-l` | 查看完整配置和模型能力（含本地模型运行时探测） |
| `--set <key> --value <val>` | 修改配置项 |
| `--protocol <1\|2>` | 设置 API 协议（1=OpenAI, 2=Anthropic） |
| `--test <layer1\|layer2>` | 测试配置连通性（L1=API 可达, L2=模型能力验证） |

## 使用示例

### 查看当前配置（REPL）

```bash
/config
```

输出示例：
```json
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "default_model": "deepseek",
  "model_provider": "deepseek",
  "api_key": "sk-****",
  "base_url": "https://api.deepseek.com/v1"
}
```

### 查看完整配置和模型能力（CLI）

```bash
python3 -m pilotcode config --list
```

输出包含：
- **Global Configuration** — 当前全局配置（`settings.json`）
- **Model Capability (Static Config)** — 来自 `config/models.json` 的静态配置（仅远程模型显示）
- **Model Capability (Runtime Detected)** — 本地模型的运行时探测结果（仅本地模型显示）

本地模型探测时，若探测值与 `settings.json` 不一致，会提示确认后自动更新：

```
⚠ context_window mismatch: settings.json=31072, detected=131072
Update settings.json to match detected value? [Y/n]:
```

### 测试配置连通性

```bash
# L1 测试：验证 API 可达性
python3 -m pilotcode config --test layer1

# L2 测试：验证模型能力（工具调用、JSON 输出等）
python3 -m pilotcode config --test layer2
```

输出包含 pytest 实时流式结果，显示模型在各维度的通过/失败状态。

### 设置配置项

```bash
# 设置主题
/config set theme dark

# 启用详细模式
/config set verbose true

# 设置默认模型
/config set default_model qwen
```

## 本地模型的配置行为

对于本地模型（Ollama、vLLM），`config --list` 会：

1. **不显示** `models.json` 的静态配置
2. **探测**本地模型的实际能力（`context_window`、`model_id` 等）
3. **对比** `settings.json` 与探测值
4. **提示确认**后自动修复 `settings.json`

> 本地模型的所有配置以 `settings.json` 为唯一来源，`models.json` 不参与本地模型的配置加载。

## API 协议选择

PilotCode 支持两种 API 协议格式：

| 协议 | 值 | 适用场景 |
|------|-----|----------|
| OpenAI-compatible | `1` | 绝大多数后端（OpenAI、DeepSeek、Qwen、本地 llama-server 等） |
| Anthropic | `2` | Claude 系列模型，支持 `thinking` 内容块和 cache token |

```bash
# 配置时选择协议
python3 -m pilotcode config --protocol 2

# 或 REPL 内设置
/config set api_protocol anthropic
```

**协议影响**：
- 请求参数构造（`tool_choice` 格式、`messages` 结构）
- 响应解析（Anthropic 的 `thinking` 块映射到 `reasoning_content`）
- 启动探测的端点选择

## API Key 与探测

配置向导和 `config --list` 在探测本地/远程模型时会自动携带 `Authorization: Bearer {api_key}` 请求头：

- `/v1/models` — 获取模型列表
- `/props` — llama-server 能力探测

这确保 LiteLLM Proxy 等**需要 API Key 的代理后端**也能正常探测，避免 401 错误。
