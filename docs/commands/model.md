# /model 命令

查看和管理当前 AI 模型，支持显示模型能力详情和快速切换。

## 作用

- 查看当前模型的详细能力（上下文窗口、工具支持、视觉支持等）
- 列出所有可用模型及其上下文大小
- 快速切换模型
- 查看或修改 Base URL

## 基本用法

```bash
/model                  # 显示当前模型能力详情和可用模型列表
/model set <name>       # 切换到指定模型
/model url [url]        # 查看或设置 Base URL
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 显示当前模型能力详情和所有可用模型 |
| `set <name>` | 切换到指定模型 |
| `url` | 查看当前 Base URL |
| `url <url>` | 设置新的 Base URL |

## 使用示例

### 查看当前模型详情

```bash
/model
```

输出示例：
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
```

`★` 标记表示当前正在使用的模型。

### 切换模型

```bash
# 切换到 Qwen
/model set qwen

# 切换到 OpenAI
/model set openai

# 切换到 DeepSeek
/model set deepseek
```

输出示例：
```
Model set to: qwen (context: 256K)
```

### 查看和设置 Base URL

```bash
# 查看当前 Base URL
/model url

# 设置本地模型地址
/model url http://localhost:11434/v1
```

## 使用场景

### 场景1：对比不同模型上下文大小

```bash
/model
# 查看各模型的 ctx 值，选择适合长文本任务的模型
# 例如 qwen-plus (1M) 适合分析大型代码库
```

### 场景2：根据任务选择模型

```bash
# 代码生成 - DeepSeek
/model set deepseek
"写一个快速排序算法"

# 中文理解 - Qwen
/model set qwen
"分析这段中文文本的情感"

# 超长上下文分析 - Qwen Plus
/model set qwen-plus
"分析这个 50万 token 的日志文件"
```

### 场景3：本地模型调试

```bash
# 切换到本地 Ollama
/model set ollama
/model url http://localhost:11434/v1
```

## 模型能力字段说明

| 字段 | 说明 |
|------|------|
| `Context window` | 模型支持的最大上下文 Token 数 |
| `Max output` | 单次回复的最大输出 Token 数 |
| `Tools` | 是否支持 Function Calling / 工具调用 |
| `Vision` | 是否支持图片/多模态输入 |

## 注意事项

1. **需要提前配置**：切换模型前需要确保该模型的 API 密钥已配置
2. **实时切换**：切换后立即生效，无需重启
3. **上下文自动同步**：切换模型后，所有上下文管理模块会自动使用新模型的上下文窗口大小

## 相关命令

- `/status` - 查看当前会话 Token 使用量和模型信息
- `/config` - 完整配置管理
- `/compact` - 手动压缩上下文
