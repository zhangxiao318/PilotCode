#!/usr/bin/env pwsh
<#
.SYNOPSIS
    PilotCode Windows 启动脚本
.DESCRIPTION
    在 Windows 上快速启动 PilotCode
.EXAMPLE
    .\run_windows.ps1
.EXAMPLE
    .\run_windows.ps1 -Model deepseek
#>

param(
    [string]$Model = "",
    [switch]$Test,
    [switch]$Setup
)

$ErrorActionPreference = "Stop"

# 颜色输出
function Write-Color($Text, $Color = "White") {
    Write-Host $Text -ForegroundColor $Color
}

# 检查 uv
function Check-UV {
    if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Color "uv 未安装，正在安装..." "Yellow"
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        # 重新加载 PATH
        $env:PATH = [Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [Environment]::GetEnvironmentVariable("PATH", "Machine")
    }
    Write-Color "✓ uv 已安装" "Green"
}

# 检查 Python
function Check-Python {
    $pythonVersion = uv python find 3.11 2>$null
    if (!$pythonVersion) {
        Write-Color "Python 3.11 未安装，正在安装..." "Yellow"
        uv python install 3.11
    }
    Write-Color "✓ Python 3.11 已安装" "Green"
}

# 安装依赖
function Install-Dependencies {
    Write-Color "正在安装依赖..." "Yellow"
    uv sync --extra dev
    Write-Color "✓ 依赖安装完成" "Green"
}

# 运行测试
function Run-Tests {
    Write-Color "正在运行测试..." "Yellow"
    uv run pytest tests/ -v --tb=short -q
    if ($LASTEXITCODE -eq 0) {
        Write-Color "✓ 所有测试通过" "Green"
    } else {
        Write-Color "✗ 有测试失败" "Red"
    }
}

# 启动 PilotCode
function Start-PilotCode {
    Write-Color "启动 PilotCode..." "Cyan"
    Write-Color "支持的模型: openai, anthropic, deepseek, qwen, moonshot 等" "Gray"
    Write-Color "使用 /help 查看帮助" "Gray"
    Write-Host ""
    
    if ($Model) {
        # 启动后切换到指定模型
        uv run pilotcode --model $Model
    } else {
        uv run pilotcode
    }
}

# 主逻辑
Write-Color @"
╔══════════════════════════════════════════════════╗
║         PilotCode - AI 编程助手                  ║
║         Windows 快速启动脚本                     ║
╚══════════════════════════════════════════════════╝
"@ "Cyan"

if ($Test) {
    Run-Tests
    exit
}

if ($Setup) {
    Check-UV
    Check-Python
    Install-Dependencies
    Write-Color "✓ 设置完成！运行 .\run_windows.ps1 启动" "Green"
    exit
}

# 检查依赖
if (!(Test-Path ".venv")) {
    Write-Color "首次运行，正在设置环境..." "Yellow"
    Check-UV
    Check-Python
    Install-Dependencies
}

# 启动
Start-PilotCode
