# /model 命令

查看当前 AI 模型能力详情和所有可用模型列表。只读显示，不支持直接切换模型。

## 作用

- 查看当前模型的详细能力（上下文窗口、工具支持、视觉支持等）
- 列出所有可用模型及其上下文大小
- 确认当前配置是否生效

## 基本用法

```bash
/model
```

## 输出内容

```
Current model: deepseek

Capability:
  Display name:   DeepSeek (深度求索)
  API model:      deepseek-chat
  Provider:       deepseek
  Context window: 128K
  Max output:     8K
  Tools:          Yes
  Vision:         No

Available models:
  deepseek        DeepSeek (深度求索)          ctx=128K *
  qwen            Qwen (通义千问)              ctx=256K
  qwen-plus       Qwen Plus (通义千问 Plus)    ctx=1M
  openai          OpenAI GPT                   ctx=128K
  anthropic       Anthropic Claude             ctx=200K
  moonshot        Moonshot (月之暗面)          ctx=256K
  ollama          Ollama (Local)               ctx=128K

Base URL: https://api.deepseek.com/v1

To switch model, use: python3 -m pilotcode configure
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `Current model` | 当前生效的模型标识名 |
| `Display name` | 展示名称 |
| `API model` | 实际请求时使用的模型 ID |
| `Provider` | 提供商类别 |
| `Context window` | 模型支持的最大上下文 Token 数 |
| `Max output` | 单次回复的最大输出 Token 数 |
| `Tools` | 是否支持 Function Calling / 工具调用 |
| `Vision` | 是否支持图片/多模态输入 |
| `*` 标记 | 当前正在使用的模型 |

## 使用场景

### 场景1：确认当前模型配置

```bash
> /model
# 检查当前使用的模型、上下文大小和能力支持
```

### 场景2：对比不同模型的上下文大小

```bash
> /model
# 查看各模型的 ctx 值
# 例如需要分析大型代码库时，确认是否使用了 qwen-plus (1M)
```

### 场景3：验证模型切换是否生效

```bash
# 通过 configure 向导切换模型后
> /model
# 确认 Current model 和 Capability 已更新
```

## 如何切换模型

`/model` 命令**不支持直接切换**。如需切换模型，请使用：

```bash
# 交互式配置向导（推荐）
python3 -m pilotcode configure

# 或命令行快速配置
python3 -m pilotcode configure --model <model_name> --api-key <key>
```

## 注意事项

1. **只读命令**：`/model` 仅展示信息，不会修改任何配置
2. **实时反映配置**：显示的是当前生效的配置，包括通过 `configure` 或 `config --set` 修改后的值
3. **ctx 值来源**：上下文窗口大小来自 `config/models.json` 中的静态配置

## 相关命令

- `/status` - 查看当前会话 Token 使用量和模型信息
- `configure` - 交互式配置向导，用于切换模型
- `config --list` - 查看完整配置和模型能力详情
