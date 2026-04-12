# Windows 运行指南

本文档介绍如何在 Windows 上安装和运行 PilotCode。

## 环境要求

- **Python**: 3.11 或更高版本
- **Git**: 2.30 或更高版本
- **uv**: Python 包管理器（推荐）或 pip

## 安装步骤

### 1. 安装 uv（推荐）

```powershell
# 使用 PowerShell 安装 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 安装 Python 3.11+

```powershell
# 使用 uv 安装 Python 3.11
uv python install 3.11
```

### 3. 克隆项目

```powershell
git clone https://github.com/zhangxiao318/PilotCode.git
cd PilotCode
```

### 4. 安装依赖

```powershell
# 使用 uv（推荐）
uv sync --extra dev

# 或使用 pip
pip install -e ".[dev]"
```

## 配置 API 密钥

### 方式一：环境变量（推荐）

```powershell
# PowerShell
$env:OPENAI_API_KEY = "your-api-key"
$env:ANTHROPIC_API_KEY = "your-api-key"
$env:DEEPSEEK_API_KEY = "your-api-key"

# 或者设置用户级环境变量（永久生效）
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-api-key", "User")
```

### 方式二：使用 config 命令

```powershell
# 启动后使用 config 命令设置
uv run python -m pilotcode main

# 然后在交互式界面中输入
/config set openai.api_key your-api-key
```

## 运行方式

### 方式一：使用 pilotcode.cmd（Windows 推荐）

项目根目录提供了 `pilotcode.cmd` 批处理脚本，自动处理虚拟环境和编码：

```cmd
# 直接双击运行，或在 CMD/PowerShell 中执行
pilotcode

# 启动 TUI 模式
pilotcode --tui

# 运行配置向导
pilotcode configure
```

### 方式二：使用 uv run（开发推荐）

```powershell
# 启动交互式 CLI
uv run python -m pilotcode main

# 或者使用短命令
uv run pilotcode main
```

### 方式三：使用 pip 安装后运行

```powershell
# 安装后直接使用
pip install -e .
pilotcode
```

### 方式四：使用 pilotcode.sh（Git Bash/WSL）

```bash
# 使用 pilotcode.sh 脚本（需安装 Git Bash 或使用 WSL）
./pilotcode.sh
```

## 支持的模型

### 国际模型
- **OpenAI GPT-4o**: 设置 `OPENAI_API_KEY`
- **Anthropic Claude 3.5**: 设置 `ANTHROPIC_API_KEY`
- **Azure OpenAI**: 设置 `AZURE_OPENAI_API_KEY`

### 国内模型
- **DeepSeek**: 设置 `DEEPSEEK_API_KEY`
- **通义千问**: 设置 `QWEN_API_KEY`
- **智谱 GLM**: 设置 `ZHIPU_API_KEY`
- **月之暗面 Kimi**: 设置 `MOONSHOT_API_KEY`
- **百川**: 设置 `BAICHUAN_API_KEY`
- **豆包**: 设置 `DOUBAO_API_KEY`

## 常用命令

```powershell
# 查看帮助
/help

# 查看当前配置
/config

# 切换模型
/model openai
/model deepseek

# Git 操作
/git status
/git diff

# 文件操作
/ls
/cat <文件名>
/edit <文件名>

# 任务管理
/tasks
/agents

# 退出
/quit
```

## 测试

```powershell
# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/unit/tools/test_bash.py -v
```

## 常见问题

### 1. 命令无法识别

确保已正确安装依赖：
```powershell
uv sync --extra dev
```

### 2. API 密钥错误

检查环境变量是否设置正确：
```powershell
$env:OPENAI_API_KEY  # 查看是否设置
```

### 3. Git 相关命令失败

确保 Git 已安装并添加到 PATH：
```powershell
git --version
```

### 4. 中文显示乱码

在 PowerShell 中设置 UTF-8 编码：
```powershell
$OutputEncoding = [console]::InputEncoding = [console]::OutputEncoding = New-Object System.Text.UTF8Encoding
```

### 5. 跨平台命令兼容性

PilotCode 已针对 Windows 进行适配：
- `pwd` → `cd`（Windows 等效命令）
- `sleep` → `Start-Sleep`（PowerShell）
- `seq` → PowerShell 循环
- 管道命令 `tr` → PowerShell `ForEach-Object`

## Windows 特殊功能

### PowerShell 集成

PilotCode 支持 PowerShell 命令：
```powershell
# 使用 PowerShell 工具
Write-Output "Hello World"
Get-ChildItem
Get-Content file.txt
```

### Windows 路径处理

支持 Windows 路径格式：
- `C:\Users\name\project`
- `/c/Users/name/project`（Git Bash 格式）

## 开发调试

```powershell
# 启用调试模式
$env:PILOTCODE_DEBUG = "1"
uv run pilotcode

# 查看日志
tail -f ~/.pilotcode/logs/pilotcode.log
```

## 获取帮助

```powershell
# 内置帮助
/help

# 查看命令列表
/commands

# 查看工具列表
/tools
```
