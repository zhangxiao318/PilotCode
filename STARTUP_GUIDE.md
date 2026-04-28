# PilotCode 启动指南

## 快速开始

### 方法 1: 使用启动脚本 (推荐)

```bash
# 赋予执行权限（首次使用）
chmod +x pilotcode

# 启动主程序
./pilotcode

# 或指定参数
./pilotcode --verbose --model gpt-4
```

### 方法 2: Python 模块启动

```bash
# 确保在 pilotcode_py 目录下
export PYTHONPATH=src:$PYTHONPATH

# 启动主程序
python3 -m pilotcode

# 查看帮助
python3 -m pilotcode --help
python3 -m pilotcode --help
```

### 方法 3: 直接运行 CLI

```bash
# 使用 PYTHONPATH
PYTHONPATH=src python3 src/pilotcode/cli.py

# 或使用 python -c
PYTHONPATH=src python3 -c "from pilotcode.cli import cli_main; cli_main()"
```

### 方法 4: 演示模式

```bash
# 基础工具演示
PYTHONPATH=src python3 demo.py

# 完整功能演示（包括任务、Agent等）
PYTHONPATH=src python3 full_demo.py
```

---

## 配置说明

### 配置文件位置

- **项目配置**: `.pilotcode.json`
- **全局配置**: `~/.config/pilotcode/settings.json`
- **本地配置**: `.pilotcode/settings.local.json`

### 示例配置

创建 `.pilotcode.json`:

```json
{
  "theme": "dark",
  "verbose": false,
  "auto_compact": true,
  "default_model": "default",
  "base_url": "http://172.19.201.40:3509/v1",
  "api_key": "your-api-key"
}
```

---

## 命令行选项

### 主程序选项

```bash
python3 -m pilotcode [OPTIONS]

Options:
  -v, --version          显示版本
  --verbose              启用详细模式
  -m, --model TEXT       指定模型 [default: default]
  --cwd TEXT            工作目录 [default: .]
  --help                显示帮助
```

### 配置管理

```bash
# 查看配置
python3 -m pilotcode config --list

# 设置配置
python3 -m pilotcode config --set theme --value dark
python3 -m pilotcode config --set default_model --value gpt-4
```

### 工具列表

```bash
# 列出所有工具
python3 -m pilotcode tools --list
```

---

## 交互命令

启动后，在 REPL 中可使用以下命令：

### 基础命令
- `/help` - 显示帮助
- `/clear` - 清屏
- `/quit` 或 `/exit` - 退出

### Agent 管理
- `/agents` - 列出所有代理
- `/agents create <type> [name]` - 创建代理
- `/agents show <id>` - 显示代理详情
- `/agents tree <id>` - 显示代理树
- `/agents types` - 列出可用代理类型
- `/agents delete <id>` - 删除代理

### 工作流编排
- `/workflow sequential '<prompt>'` - 顺序执行
- `/workflow parallel '<prompt>'` - 并行执行
- `/workflow supervisor '<task>'` - 监督者模式
- `/workflow debate '<topic>'` - 辩论模式

### Git 命令
- `/branch` - 分支管理
- `/commit` - 提交更改
- `/diff` - 显示差异
- `/stash` - Stash 操作
- `/merge` - 合并分支
- `/rebase` - Rebase 分支
- `/status` - Git 状态

### 开发工具
- `/test` - 运行测试
- `/lint` - 代码检查（仅支持 Python）
- `/format` - 代码格式化（仅支持 Python）
- `/coverage` - 代码覆盖率
- `/symbols <file>` - 显示符号
- `/references <symbol>` - 查找引用

### 文件操作
- `/cat <file>` - 查看文件
- `/ls [path]` - 列出目录
- `/cd <path>` - 切换目录
- `/pwd` - 当前目录
- `/edit <file>` - 编辑文件

### 其他
- `/cost` - 成本统计
- `/session` - 会话管理
- `/history` - 历史记录
- `/compact` - 压缩历史
- `/mcp` - MCP 管理
- `/skills` - 技能管理

---

## 环境要求

### Python 版本
- Python 3.10+

### 依赖安装

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 必要依赖
- `rich` - TUI 渲染
- `typer` - CLI 框架
- `pydantic` - 数据验证
- `httpx` - HTTP 客户端
- `prompt-toolkit` - 交互式提示
- `platformdirs` - 跨平台目录

---

## 故障排除

### 问题: ModuleNotFoundError

**解决**: 确保设置了 PYTHONPATH
```bash
export PYTHONPATH=/path/to/pilotcode_py/src:$PYTHONPATH
```

### 问题: 模型连接失败

**解决**: 检查配置中的 `base_url` 和 `api_key`
```bash
# 检查配置
python3 -m pilotcode config --list

# 修改配置
python3 -m pilotcode config --set base_url --value http://your-server:port/v1
```

### 问题: 权限被拒绝

**解决**: 检查文件权限
```bash
chmod +x pilotcode
chmod -R u+rw src/
```

---

## 使用示例

### 示例 1: 启动并执行任务

```bash
./pilotcode
> /agents create coder my_coder
> /agents
> /workflow sequential "Analyze the codebase and find bugs"
```

### 示例 2: 代码审查工作流

```bash
./pilotcode
> /workflow parallel "Review this code for issues" reviewer debugger
```

### 示例 3: 调试会话

```bash
./pilotcode
> /agents create debugger bug_hunter
> Debug the error in main.py line 42
```

---

## 快捷键

在 REPL 中：
- `Ctrl+C` - 中断当前操作
- `Ctrl+D` - 退出程序
- `Tab` - 命令补全
- `↑/↓` - 历史记录

---

## 更多信息

- 查看 `FEATURE_LIST.md` 了解完整功能列表
- 查看 `COMPARISON_ANALYSIS.md` 了解与其他实现的对比
- 查看 `ARCHITECTURE.md` 了解架构设计
