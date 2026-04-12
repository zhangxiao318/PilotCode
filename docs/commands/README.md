# PilotCode 命令文档

本目录包含 PilotCode 所有斜杠命令的详细文档。

## 命令列表

### 核心命令

| 命令 | 说明 | 文档 |
|------|------|------|
| `/help` | 显示帮助信息 | [help.md](help.md) |
| `/index` | 索引代码库 | [index.md](index.md) |
| `/search` | 智能代码搜索 | [search.md](search.md) |
| `/clear` | 清除屏幕 | [clear.md](clear.md) |
| `/quit` | 退出程序 | [quit.md](quit.md) |

### 配置命令

| 命令 | 说明 | 文档 |
|------|------|------|
| `/config` | 配置管理 | [config.md](config.md) |
| `/model` | 模型设置 | [model.md](model.md) |
| `/theme` | 主题切换 | [theme.md](theme.md) |

### 会话命令

| 命令 | 说明 | 文档 |
|------|------|------|
| `/session` | 会话管理 | [session.md](session.md) |
| `/cost` | 用量统计 | [cost.md](cost.md) |

### Git 命令

| 命令 | 说明 | 文档 |
|------|------|------|
| `/git` | Git 操作 | [git.md](git.md) |

## 快速参考

### 常用命令速查

```bash
# 代码索引与搜索
/index full              # 完整索引
/search <query>          # 语义搜索
/search -s Symbol        # 符号搜索

# 配置管理
/config                  # 查看配置
/model <name>            # 切换模型
/theme <name>            # 切换主题

# 会话管理
/session save <name>     # 保存会话
/session load <name>     # 加载会话
/session list            # 列出会话
/cost                    # 查看用量

# Git 操作
/git status              # Git 状态
/git log -5              # 提交历史
/git diff                # 查看修改

# 系统
/help                    # 显示帮助
/clear                   # 清除屏幕
/quit                    # 退出程序
```

## 命令使用技巧

### 1. 查看命令帮助

大多数命令支持查看详细帮助：

```bash
/help <command>
```

### 2. 命令自动补全

在输入命令时，可以使用 `Tab` 键自动补全命令名。

### 3. 命令历史

使用上下箭头键可以浏览之前输入的命令。

### 4. 快捷键

| 快捷键 | 作用 |
|--------|------|
| `Ctrl+C` | 中断当前操作 |
| `Ctrl+L` | 清屏（等效于 `/clear`） |
| `Ctrl+D` | 退出（等效于 `/quit`） |
| `Tab` | 自动补全 |
| `↑/↓` | 浏览历史 |

## 学习路径

### 新手入门

1. 先阅读 [help.md](help.md) 了解如何获取帮助
2. 学习 [index.md](index.md) 和 [search.md](search.md) 掌握代码搜索
3. 阅读 [config.md](config.md) 和 [model.md](model.md) 配置环境

### 进阶使用

1. 学习 [session.md](session.md) 管理对话
2. 阅读 [git.md](git.md) 集成版本控制
3. 使用 [cost.md](cost.md) 监控使用量

## 文档格式

每个命令文档包含：

- **作用**：命令的基本功能
- **基本用法**：命令语法
- **选项/子命令**：可用选项和子命令
- **使用示例**：常见使用场景
- **故障排除**：常见问题解决

## 贡献文档

如果发现文档有误或需要更新，欢迎提交 PR。

文档模板：

```markdown
# /command 命令

简要说明命令的作用。

## 作用

- 功能点1
- 功能点2

## 基本用法

\`\`\`bash
/command [options]
\`\`\`

## 选项

| 选项 | 说明 |
|------|------|
| `-h` | 帮助 |

## 使用示例

### 场景1：示例说明

\`\`\`bash
/command example
\`\`\`

## 相关命令

- `/other` - 相关命令
```