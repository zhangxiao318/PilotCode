# PilotCode 快速开始指南

[中文](QUICKSTART.md) | [English](QUICKSTART_EN.md)

在 5 分钟内启动 PilotCode AI 编程助手。

---

## 1. 安装环境

### 系统要求
- Python 3.11 或更高版本
- Linux/macOS/Windows

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/zhangxiao318/PilotCode.git
cd PilotCode

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或: venv\Scripts\activate  # Windows

# 安装依赖
pip3 install -e .
```

**验证安装：**
```bash
python3 -m pilotcode main --version
```

---

## 2. 配置 LLM

PilotCode 支持多种大语言模型，包括国际模型（OpenAI、Anthropic）和国内模型（DeepSeek、Qwen、GLM 等）。

### 方式一：交互式配置（推荐）

运行配置向导，按提示选择模型并输入 API 密钥：

```bash
python3 -m pilotcode configure
```

向导会引导你完成：
1. 选择模型类型（国际/国内/本地）
2. 选择具体模型
3. 输入 API 密钥
4. 可选设置（主题、自动压缩等）

### 方式二：快速配置（命令行）

如果你已经知道要使用的模型和 API 密钥：

```bash
# DeepSeek 示例
python3 -m pilotcode configure --model deepseek --api-key sk-xxx

# Qwen 示例
python3 -m pilotcode configure --model qwen --api-key sk-xxx

# OpenAI 示例
python3 -m pilotcode configure --model openai --api-key sk-xxx
```

### 方式三：环境变量

```bash
# 通用配置
export PILOTCODE_API_KEY="your-api-key"
export PILOTCODE_MODEL="deepseek"
export PILOTCODE_BASE_URL="https://api.deepseek.com/v1"

# 服务商特定（自动识别）
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."  # Qwen
export ZHIPU_API_KEY="..."         # GLM
```

### 方式四：手动配置文件

创建 `~/.config/pilotcode/settings.json`：

```bash
mkdir -p ~/.config/pilotcode
cat > ~/.config/pilotcode/settings.json << 'EOF'
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "default_model": "deepseek",
  "model_provider": "deepseek",
  "api_key": "your-api-key",
  "base_url": "https://api.deepseek.com/v1"
}
EOF
```

### 支持的模型

| 模型 | 命令 | 描述 |
|------|------|------|
| DeepSeek | `--model deepseek` | 代码能力强，性价比高 |
| Qwen | `--model qwen` | 阿里通义千问 |
| GLM | `--model zhipu` | 智谱清言 |
| OpenAI | `--model openai` | GPT-4o |
| Claude | `--model anthropic` | Claude 3.5 Sonnet |
| Ollama | `--model ollama` | 本地运行，无需 API 密钥 |

查看所有支持的模型：
```bash
python3 -m pilotcode configure --list-models
```

### 查看当前配置

```bash
python3 -m pilotcode configure --show
```

---

## 3. 运行 PilotCode

### 启动交互式 TUI

```bash
# 默认启动（推荐）
python3 -m pilotcode main

# 或使用启动脚本（Linux/macOS）
./pilotcode.sh

# Windows 使用
.\pilotcode.cmd

# 或使用别名（安装后）
pilotcode
pc
```

### 单次命令模式

```bash
# 执行单条命令后退出
python3 -m pilotcode main -p "分析当前目录的代码结构"
```

### 简单 CLI 模式（无 TUI）

```bash
python3 -m pilotcode main --simple
```

### 其他启动选项

```bash
# 指定工作目录
python3 -m pilotcode main --cwd /path/to/project

# 自动允许所有工具执行（谨慎使用）
python3 -m pilotcode main --auto-allow

# 显示详细日志
python3 -m pilotcode main --verbose
```

---

## 快速验证

启动后，输入测试消息验证是否正常工作：

```
你好，请介绍一下自己
```

如果看到 AI 回复，说明配置成功！

---

## 常用命令

在 PilotCode 交互界面中，可以使用以下命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/model <name>` | 切换模型 |
| `/config` | 查看/修改配置 |
| `/theme` | 切换主题 |
| `/session` | 会话管理 |
| `/cost` | 查看用量统计 |
| `/quit` | 退出 |

---

## 获取 API 密钥

- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Qwen (阿里云)**: https://dashscope.aliyun.com/api-key-management
- **Zhipu (智谱)**: https://open.bigmodel.cn/usercenter/apikeys
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys

---

## 故障排除

### 检查配置
```bash
python3 -m pilotcode configure --show
```

### 测试 API 连接
```bash
curl $PILOTCODE_BASE_URL/models \
  -H "Authorization: Bearer $PILOTCODE_API_KEY"
```

### 重置配置
```bash
rm ~/.config/pilotcode/settings.json
python3 -m pilotcode configure  # 重新配置
```

---

## 下一步

- 阅读完整文档：[README.md](README.md)
- 了解架构设计：[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
- 查看功能列表：[docs/features/FEATURE_LIST.md](docs/features/FEATURE_LIST.md)

---

**提示**: 首次使用建议从 DeepSeek 或 Qwen 开始，它们对中文支持更好且价格优惠。
