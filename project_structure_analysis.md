项目文件结构分析报告
================================

## 项目概述
PilotCode 是一个 Python 重写的 Claude Code CLI 工具，提供 AI 辅助编程功能。

## 主要文件和目录结构

### 根目录文件
- README.md - 项目主文档
- README_EN.md - 英文版项目文档
- QUICKSTART.md - 快速开始指南
- QUICKSTART_EN.md - 英文版快速开始指南
- INSTALL.md - 安装指南
- pyproject.toml - 项目配置文件
- requirements.txt - 依赖包列表
- pilotcode.sh - Linux/Mac 启动脚本
- pilotcode.cmd - Windows 启动脚本
- full_demo.py - 演示脚本
- run_single_instance.py - 单实例运行脚本

### 源代码目录结构 (src/pilotcode/)

#### 核心模块
- cli.py - 命令行接口
- query_engine.py - 查询引擎
- main.py - 主程序入口

#### 功能模块
- tools/ - 工具实现 (18个工具)
- commands/ - 命令系统 (13个命令)
- services/ - 外部服务
- components/ - TUI 组件
- tui/ - 终端用户界面
- tui_v2/ - 新版终端用户界面
- state/ - 状态管理
- types/ - 类型定义 (Pydantic 模型)
- utils/ - 工具函数
- agent/ - AI 代理相关
- permissions/ - 权限管理
- provider/ - 模型提供商
- model_capability/ - 模型能力检测
- orchestration/ - 协调控制
- plugins/ - 插件系统
- hooks/ - 钩子系统
- web/ - Web 相关
- mcp_tui_client/ - MCP TUI 客户端
- ui/ - 用户界面

## 文件类型

- Python 文件 (.py) - 主要代码
- Markdown 文件 (.md) - 文档
- Shell 脚本 (.sh) - 启动脚本
- Batch 脚本 (.cmd) - Windows 启动脚本
- JSON 文件 (.json) - 配置和数据
- Text 文件 (.txt) - 纯文本文件
- TOML 文件 (.toml) - 项目配置
- Python 包结构 - 包含 __init__.py 文件

## 主要功能模块

1. **工具系统 (Tools)** - 实现了18个核心工具，包括文件操作、Shell执行、搜索、Web访问、任务管理等
2. **命令系统 (Commands)** - 实现了13个命令，包括帮助、搜索、配置、会话管理等
3. **查询引擎 (Query Engine)** - 与 LLM 进行交互的核心模块
4. **用户界面 (TUI)** - 终端用户界面实现
5. **状态管理 (State Management)** - 系统状态管理
6. **模型支持 (Model Support)** - 支持国内外主流大模型 API
7. **代码索引与搜索 (Code Indexing & Search)** - 企业级代码索引和智能搜索系统
8. **插件系统 (Plugin System)** - 支持插件扩展
9. **权限管理 (Permissions)** - 权限控制
