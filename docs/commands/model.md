# /model 命令

查看当前 AI 模型的能力详情。只读显示，不支持切换模型。

## 作用

- 查看当前模型的详细能力（上下文窗口、最大输出、工具支持、视觉支持等）
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

## 使用场景

### 场景1：确认当前模型配置

```bash
> /model
# 检查当前使用的模型、上下文大小和能力支持
```

### 场景2：验证模型切换是否生效

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
- `config --list` - 查看完整配置和模型能力详情（支持本地模型运行时探测、provider 自动推断、差异高亮与交互更新）
