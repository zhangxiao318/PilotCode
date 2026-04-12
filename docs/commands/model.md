# /model 命令

快速切换和管理 AI 模型。

## 作用

- 查看当前使用的模型
- 快速切换模型
- 列出可用模型

## 基本用法

```bash
/model [model_name]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 显示当前模型 |
| `<name>` | 切换到指定模型 |
| `list` | 列出所有可用模型 |

## 使用示例

### 查看当前模型

```bash
/model
```

输出：
```
Current model: deepseek
Provider: deepseek
Base URL: https://api.deepseek.com/v1
```

### 切换到其他模型

```bash
# 切换到 Qwen
/model qwen

# 切换到 OpenAI
/model openai

# 切换到 DeepSeek
/model deepseek
```

### 列出可用模型

```bash
/model list
```

输出示例：
```
Available models:
  - deepseek     (DeepSeek V3)
  - qwen         (Qwen Max)
  - qwen-plus    (Qwen Plus)
  - openai       (GPT-4o)
  - anthropic    (Claude 3.5 Sonnet)
  - zhipu        (GLM-4)
  - moonshot     (Kimi)
  - ollama       (Local Ollama)
```

## 支持的模型

### 国际模型

| 模型 | 描述 |
|------|------|
| `openai` | GPT-4o - 最强多模态模型 |
| `openai-gpt4` | GPT-4 Turbo |
| `anthropic` | Claude 3.5 Sonnet - 优秀代码能力 |
| `azure` | Azure OpenAI Service |

### 国内模型

| 模型 | 描述 |
|------|------|
| `deepseek` | DeepSeek V3 - 代码能力强 |
| `qwen` | Qwen Max - 阿里通义千问 |
| `qwen-plus` | Qwen Plus - 性价比平衡 |
| `zhipu` | GLM-4 - 智谱清言 |
| `moonshot` | Kimi - 长上下文 |
| `baichuan` | Baichuan 4 |
| `doubao` | Doubao - 字节跳动 |

### 本地模型

| 模型 | 描述 |
|------|------|
| `ollama` | 本地 Ollama 实例 |
| `custom` | 自定义 OpenAI 兼容端点 |

## 使用场景

### 场景1：对比不同模型效果

```bash
# 使用 DeepSeek 提问
/model deepseek
"解释 Python 装饰器"

# 切换到 Qwen 对比
/model qwen
"解释 Python 装饰器"
```

### 场景2：根据任务选择模型

```bash
# 代码生成任务 - 使用 DeepSeek
/model deepseek
"写一个快速排序算法"

# 中文理解任务 - 使用 Qwen
/model qwen
"分析这段中文文本的情感"

# 复杂推理任务 - 使用 Claude
/model anthropic
"设计一个分布式系统架构"
```

### 场景3：检查模型配置

```bash
# 查看当前模型
/model

# 查看所有可用模型
/model list
```

## 注意事项

1. **需要提前配置**：切换模型前需要确保该模型的 API 密钥已配置
2. **实时切换**：切换后立即生效，无需重启
3. **不同模型特性**：不同模型在代码能力、中文理解、价格方面有所不同

## 与 /config 的区别

| 命令 | 作用 | 范围 |
|------|------|------|
| `/model` | 快速切换模型 | 仅模型相关 |
| `/config` | 完整配置管理 | 所有配置项 |

## 相关命令

- `/config` - 完整配置管理
- `/cost` - 查看模型使用成本