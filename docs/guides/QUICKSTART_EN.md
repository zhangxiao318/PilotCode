# PilotCode Quick Start Guide

Get started with PilotCode AI coding assistant in 5 minutes.

---

## 1. Installation

### System Requirements
- Python 3.11 or higher
- Linux/macOS/Windows

### Installation Steps

```bash
# Clone the repository
git clone https://github.com/zhangxiao318/PilotCode.git
cd PilotCode

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# Or: venv\Scripts\activate  # Windows

# Install dependencies
pip3 install -e .
```

**Verify Installation:**
```bash
python3 -m pilotcode main --version
```

---

## 2. Configure LLM

PilotCode supports various LLMs, including international models (OpenAI, Anthropic) and domestic models (DeepSeek, Qwen, GLM, etc.).

### Method 1: Interactive Configuration (Recommended)

Run the configuration wizard and follow the prompts to select a model and enter your API key:

```bash
python3 -m pilotcode configure
```

The wizard will guide you through:
1. Selecting model type (International/Domestic/Local)
2. Choosing a specific model
3. Entering your API key
4. Optional settings (theme, auto-compact, etc.)

### Method 2: Quick Configuration (Command Line)

If you already know which model and API key to use:

```bash
# DeepSeek example
python3 -m pilotcode configure --model deepseek --api-key sk-xxx

# Qwen example
python3 -m pilotcode configure --model qwen --api-key sk-xxx

# OpenAI example
python3 -m pilotcode configure --model openai --api-key sk-xxx
```

### Method 3: Environment Variables

```bash
# Generic configuration
export PILOTCODE_API_KEY="your-api-key"
export PILOTCODE_MODEL="deepseek"
export PILOTCODE_BASE_URL="https://api.deepseek.com/v1"

# Provider-specific (auto-detected)
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."  # Qwen
export ZHIPU_API_KEY="..."         # GLM
```

### Method 4: Manual Configuration File

Create `~/.config/pilotcode/settings.json`:

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

### Supported Models

| Model | Command | Description |
|-------|---------|-------------|
| DeepSeek | `--model deepseek` | Strong coding ability, cost-effective |
| Qwen | `--model qwen` | Alibaba Tongyi Qianwen |
| GLM | `--model zhipu` | Zhipu Qingyan |
| OpenAI | `--model openai` | GPT-4o |
| Claude | `--model anthropic` | Claude 3.5 Sonnet |
| Ollama | `--model ollama` | Local deployment, no API key needed |

View all supported models:
```bash
python3 -m pilotcode configure --list-models
```

### View Current Configuration

```bash
python3 -m pilotcode configure --show
```

---

## 3. Run PilotCode

### Start Interactive TUI

```bash
# Default start (recommended)
python3 -m pilotcode main

# Or use startup scripts (Linux/macOS)
./pilotcode.sh

# Windows
.\pilotcode.cmd

# Or use aliases (after installation)
pilotcode
pc
```

### One-Shot Command Mode

```bash
# Execute a single command and exit
python3 -m pilotcode main -p "Analyze the code structure of current directory"
```

### Simple CLI Mode (No TUI)

```bash
python3 -m pilotcode main --simple
```

### Other Startup Options

```bash
# Specify working directory
python3 -m pilotcode main --cwd /path/to/project

# Auto-allow all tool executions (use with caution)
python3 -m pilotcode main --auto-allow

# Show verbose logs
python3 -m pilotcode main --verbose
```

---

## Quick Verification

After starting, enter a test message to verify it's working:

```
Hello, please introduce yourself
```

If you see the AI response, the configuration is successful!

---

## Common Commands

In the PilotCode interactive interface, you can use the following commands:

| Command | Description |
|---------|-------------|
| `/help` | Show help information |
| `/model <name>` | Switch model |
| `/config` | View/modify configuration |
| `/theme` | Switch theme |
| `/session` | Session management |
| `/cost` | View usage statistics |
| `/quit` | Exit |

---

## Getting API Keys

- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Qwen (Alibaba)**: https://dashscope.aliyun.com/api-key-management
- **Zhipu**: https://open.bigmodel.cn/usercenter/apikeys
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys

---

## Troubleshooting

### Check Configuration
```bash
python3 -m pilotcode configure --show
```

### Test API Connection
```bash
curl $PILOTCODE_BASE_URL/models \
  -H "Authorization: Bearer $PILOTCODE_API_KEY"
```

### Reset Configuration
```bash
rm ~/.config/pilotcode/settings.json
python3 -m pilotcode configure  # Reconfigure
```

---

## Next Steps

- Read full documentation: [README_EN.md](README_EN.md)
- Learn architecture design: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
- View feature list: [docs/features/FEATURE_LIST.md](docs/features/FEATURE_LIST.md)

---

**Tip**: For first-time users, we recommend starting with DeepSeek or Qwen, as they offer better Chinese support and competitive pricing.
