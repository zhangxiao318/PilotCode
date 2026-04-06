# 功能差异分析报告

## 项目概述

| 项目 | 语言 | 代码量 | 性质 | 目标 |
|------|------|--------|------|------|
| **pilotcode_py** | Python | ~9,500 行 | 个人实现 | Claude Code 替代品 |
| **claw-code-main** | Python/Rust | ~20,000 行 | 开源社区 | 追踪/记录原始功能 |
| **原始 Claude Code** | TypeScript | ~512,000 行 | 闭源商业产品 | 参考标准 |

---

## 1. 工具系统对比

### 1.1 工具数量

| 项目 | 已实现工具 | 目标工具 | 完成度 |
|------|-----------|---------|--------|
| pilotcode_py | **51** | ~80 | 64% |
| claw-code-main (Rust) | **20** | ~80 | 25% |
| claw-code-main (Python) | **0** | ~184 (镜像) | 0% (仅元数据) |

### 1.2 工具详细对比

| 工具类别 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|---------|---------------|----------------------|------------------|
| **文件操作** | FileRead, FileWrite, FileEdit | ✅ 完整 | ✅ 完整 |
| **Shell** | Bash, PowerShell | ✅ Bash, PowerShell | ✅ Bash, PowerShell |
| **搜索** | Glob, Grep | ✅ Glob, Grep | ✅ Glob, Grep |
| **网络** | WebSearch, WebFetch | ✅ WebSearch, WebFetch | ✅ WebSearch, WebFetch |
| **Agent** | Agent, SendMessage, ReceiveMessage | ⚠️ Agent (基础) | ✅ AgentTool, 多种子代理 |
| **任务** | TodoWrite, Task* | ⚠️ TodoWrite | ✅ TaskCreate/Get/Update/List/Stop |
| **Team** | TeamCreate/Delete/List/AddMember | ❌ 缺失 | ✅ TeamCreate, TeamDelete, etc. |
| **Cron** | CronCreate/Delete/List/Update | ❌ 缺失 | ✅ ScheduleCronTool |
| **MCP** | MCP, ListMcpResources, ReadMcpResource | ⚠️ 配置支持 | ✅ 完整 MCP 工具集 |
| **LSP** | LSP | ❌ 缺失 | ✅ LSPTool |
| **Notebook** | NotebookEdit | ✅ NotebookEdit | ✅ NotebookEditTool |
| **配置** | Config | ✅ Config | ✅ ConfigTool |
| **计划模式** | Enter/ExitPlanMode, UpdatePlanStep | ❌ 缺失 | ✅ Enter/ExitPlanModeTool |
| **Worktree** | Enter/ExitWorktree, ListWorktrees | ❌ 缺失 | ✅ Enter/ExitWorktreeTool |
| **Git** | GitBranch, GitDiff, GitLog, GitStatus | ❌ 缺失 | ✅ Git 工具套件 |
| **AskUser** | AskUser | ❌ 缺失 | ✅ AskUserQuestionTool |
| **Brief** | Brief | ✅ Brief | ✅ BriefTool |
| **Skill** | Skill | ✅ Skill | ✅ SkillTool |
| **Sleep** | Sleep | ✅ Sleep | ✅ SleepTool |
| **REPL** | REPL | ✅ REPL | ✅ REPLTool |
| **RemoteTrigger** | RemoteTrigger | ❌ 缺失 | ✅ RemoteTriggerTool |
| **SyntheticOutput** | SyntheticOutput | ✅ StructuredOutput | ✅ SyntheticOutputTool |
| **ToolSearch** | ToolSearch | ✅ ToolSearch | ✅ ToolSearchTool |

---

## 2. 命令系统对比

### 2.1 命令数量

| 项目 | 已实现命令 | 目标命令 | 完成度 |
|------|-----------|---------|--------|
| pilotcode_py | **64** | ~80 | 80% |
| claw-code-main (Rust) | **15** | ~207 | 7% |
| claw-code-main (Python) | **0** | ~207 (镜像) | 0% (仅元数据) |

### 2.2 命令详细对比

| 命令类别 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|---------|---------------|----------------------|------------------|
| **基础** | help, clear, quit | ✅ help, clear, status | ✅ 完整 |
| **配置** | config, theme, model | ✅ config, model | ✅ config, theme, color |
| **会话** | session, history, compact, export | ✅ compact, resume | ✅ session, history, compact, resume |
| **Git** | branch, commit, diff, stash, tag, remote, merge, rebase, reset, cherrypick, revert, blame, bisect | ❌ 缺失 | ✅ 完整 Git 命令集 |
| **代码** | lint, format, test, coverage | ❌ 缺失 | ✅ 可能支持 |
| **分析** | symbols, references | ❌ 缺失 | ✅ 可能支持 |
| **Agent** | agents, tasks | ❌ 缺失 | ✅ agents, tasks |
| **MCP** | mcp, lsp | ⚠️ MCP 配置 | ✅ mcp, lsp 管理 |
| **计划** | plan | ❌ 缺失 | ✅ plan |
| **其他** | doctor, debug, cost, memory, skills, share | ✅ cost, permissions, memory | ✅ doctor, debug, cost, memory, skills |

---

## 3. 架构对比

### 3.1 核心架构组件

| 组件 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|------|---------------|----------------------|------------------|
| **状态管理** | ✅ Store 模式 (Zustand-like) | ✅ Session 管理 | ✅ 复杂状态管理 |
| **工具注册表** | ✅ ToolRegistry | ✅ ToolRegistry | ✅ 工具注册表 |
| **命令注册表** | ✅ CommandRegistry | ✅ 命令注册表 | ✅ 命令注册表 |
| **查询引擎** | ✅ QueryEngine | ✅ ConversationRuntime | ✅ QueryEngine |
| **权限系统** | ⚠️ 基础权限检查 | ✅ PermissionMode | ✅ 完整权限系统 |
| **MCP 集成** | ⚠️ 基础 MCP 客户端 | ✅ MCP 客户端 | ✅ 完整 MCP 服务 |
| **LSP 集成** | ⚠️ 基础 | ❌ 缺失 | ✅ LSP 管理器 |
| **Hook 系统** | ❌ 缺失 | ⚠️ 配置解析 | ✅ 完整 Hook 系统 |
| **插件系统** | ❌ 缺失 | ⚠️ 插件框架 | ✅ 完整插件系统 |

### 3.2 TUI/界面

| 功能 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|------|---------------|----------------------|------------------|
| **REPL** | ✅ Rich-based | ✅ 自定义 REPL | ✅ Ink-based |
| **权限对话框** | ❌ 缺失 | ⚠️ 基础提示 | ✅ 交互式对话框 |
| **消息渲染** | ⚠️ 基础 Markdown | ✅ Markdown 渲染 | ✅ 完整消息组件 |
| **状态栏** | ❌ 缺失 | ✅ 状态显示 | ✅ 状态栏 |
| **多面板** | ❌ 缺失 | ❌ 缺失 | ✅ 复杂布局 |

### 3.3 服务/集成

| 服务 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|------|---------------|----------------------|------------------|
| **LLM 客户端** | ✅ OpenAI-compatible | ✅ Anthropic API | ✅ Anthropic SDK |
| **多模型支持** | ✅ 配置化 | ✅ 模型别名 | ✅ 多模型 |
| **OAuth** | ❌ 缺失 | ✅ OAuth 支持 | ✅ OAuth 服务 |
| **分析/遥测** | ❌ 缺失 | ❌ 缺失 | ✅ 完整分析 |
| **远程同步** | ❌ 缺失 | ⚠️ 远程配置 | ✅ 远程设置同步 |
| **团队内存** | ❌ 缺失 | ❌ 缺失 | ✅ 团队内存同步 |

---

## 4. 关键差异总结

### 4.1 pilotcode_py 的优势

1. **命令覆盖度高**: 64/80 命令 (80%)，远超 claw-code-main Rust 的 15/207 (7%)
2. **Git 集成完整**: 实现了 stash, tag, remote, merge, rebase 等高级 Git 命令
3. **开发工具**: 实现了 lint, format, test, coverage, symbols, references 等开发命令
4. **代码量精简**: 9,500 行实现核心功能，代码效率较高

### 4.2 pilotcode_py 的劣势

1. **Agent 系统薄弱**: Agent/Team 工具仅基础实现，缺少完整的子代理编排
2. **Hook 系统缺失**: 没有 PreToolUse/PostToolUse 等 Hook 机制
3. **插件系统缺失**: 无插件加载/管理功能
4. **TUI 简陋**: 只有基础 REPL，没有权限对话框等交互组件
5. **服务层薄弱**: 缺少 OAuth、分析、远程同步等企业级功能
6. **测试覆盖**: 缺少全面的测试套件

### 4.3 claw-code-main 的特点

1. **双语言实现**: Python (镜像追踪) + Rust (运行时)
2. **功能完整映射**: Python 部分记录了 184 个工具和 207 个命令的元数据
3. **Rust 运行时**: 提供实际的 CLI 工具，但功能较基础
4. **PARITY.md**: 提供了详细的差异分析文档

---

## 5. 功能优先级建议

### P0 - 核心差距 (必须补齐)

| 功能 | 影响 | 预估工作量 |
|------|------|-----------|
| **AskUser 工具** | 用户交互必需 | 2 天 |
| **权限对话框** | 安全/体验必需 | 3 天 |
| **Hook 系统** | 扩展性必需 | 5 天 |
| **Agent 完善** | 核心功能 | 1 周 |

### P1 - 重要功能 (应该补齐)

| 功能 | 影响 | 预估工作量 |
|------|------|-----------|
| **插件系统** | 扩展生态 | 2 周 |
| **TUI 完善** | 用户体验 | 2 周 |
| **MCP 完整** | 工具生态 | 1 周 |
| **测试套件** | 质量保证 | 1 周 |

### P2 - 增强功能 (可以补齐)

| 功能 | 影响 | 预估工作量 |
|------|------|-----------|
| **OAuth/登录** | 企业功能 | 1 周 |
| **分析遥测** | 产品优化 | 1 周 |
| **远程同步** | 团队协作 | 2 周 |
| **LSP 完善** | 开发体验 | 1 周 |

---

## 6. 代码统计对比

| 指标 | pilotcode_py | claw-code-main (Rust) | 原始 Claude Code |
|------|---------------|----------------------|------------------|
| **总代码行数** | ~9,500 | ~20,000 | ~512,000 |
| **工具实现** | 51 | 20 | ~184 |
| **命令实现** | 64 | 15 | ~207 |
| **源文件数** | ~35 | ~50 | ~1,884 |
| **架构完整度** | 60% | 40% | 100% |
| **功能完整度** | 35% | 15% | 100% |

---

## 7. 结论

### pilotcode_py 定位
- **当前**: 可用的 Claude Code 替代品，适合个人日常使用
- **优势**: 命令覆盖度高、Git 集成好、代码精简
- **劣势**: 企业级功能缺失、TUI 简陋、Agent 系统薄弱

### 与 claw-code-main 的关系
- claw-code-main 更注重**功能追踪和记录** (PARITY.md)
- pilotcode_py 更注重**实际可用性** (64 命令 vs 15 命令)
- 两者可以互补：pilotcode_py 提供功能，claw-code-main 提供参考

### 未来方向
1. 补齐 P0 核心差距 (AskUser、权限对话框、Hook 系统)
2. 完善 Agent/Team 系统
3. 增强 TUI 体验
4. 添加插件/技能系统
5. 考虑与 claw-code-main Rust 运行时整合
