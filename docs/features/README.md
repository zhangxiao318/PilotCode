# PilotCode 功能特性

本文档介绍 PilotCode 的核心功能特性，包括设计原理、使用方法和与其他工具的对比。

---

## 核心特性

| 特性 | 说明 | 完成度 |
|------|------|--------|
| **代码智能** | 代码索引、语义/符号搜索、项目记忆 | ✅ 完整 |
| **上下文管理** | Token 监控、智能压缩、MemPO 记忆 | ✅ 完整 |
| **P-EVR 任务编排** | Plan-Execute-Verify-Reflect 闭环 | ✅ 核心骨架 |
| **弱模型代偿** | 框架级多维补偿引擎（Qwen3-Coder-30B 实测有效） | ✅ 完整 |
| **错误恢复** | 容错与降级 | ✅ 完整 |
| **会话管理** | 对话持久化与恢复 | ✅ 完整 |
| **Reflection Mode** | 生成→审查→修改闭环（三层：Self-Critique / Pre-Edit / Post-Turn） | 📝 设计完成，待实现 |
| **Reasoning Content 利用** | DeepSeek/Qwen/Claude thinking 内容全链路后处理（动态开关/一致性/循环检测/压缩/Reflection） | ✅ 已实现 |

---

## 特性文档

### 代码智能

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [codebase-intelligence.md](./codebase-intelligence.md) | 代码智能：索引、搜索与记忆 | 大型项目分析、代码查找、项目知识沉淀 |

### 上下文与稳定性

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [context-management.md](./context-management.md) | 上下文管理 | Token 监控、自动/手动压缩、MemPO 记忆 |
| [token-counting-architecture.md](./token-counting-architecture.md) | Token 计算体系 | 四层回退策略、精确/启发式计数、基线测量 |
| [session-service-mvc.md](./session-service-mvc.md) | SessionService MVC 架构 | UIProtocol 三通道、共用 Controller、消除 UI 重复逻辑 |
| [error-recovery.md](./error-recovery.md) | 错误恢复与重试 | 网络不稳定、API 限流 |
| [session-management.md](./session-management.md) | 会话管理 | 多项目管理、历史恢复 |

### 模型系统

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [model-system.md](./model-system.md) | 模型系统：配置与探测 | 自定义模型、本地模型部署、参数调优 |
| [weak-model-compensation.md](./weak-model-compensation.md) | 弱模型多维代偿 | 本地弱模型（7B-30B）、自托管模型、能力评估 |

### 任务编排

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [p-evr-task-orchestration.md](./p-evr-task-orchestration.md) | P-EVR 任务编排 | 结构化任务分解、DAG 执行、三级验证 |

### Agent 模式（规划中）

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [reflection-mode.md](./reflection-mode.md) | Reflection Mode 设计文档 | 生成→审查→修改闭环、代码质量提升 |

### Reasoning 与模型能力

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [reasoning-content-utilization.md](./reasoning-content-utilization.md) | Reasoning Content 全链路利用 | DeepSeek/Qwen/Claude thinking 模式优化、token 节省、防漏改 |
| [weak-model-compensation.md](./weak-model-compensation.md) | 弱模型多维代偿 | 本地 7B–30B 模型、能力评估、自适应降级 |

---

## 快速导航

**开发者？**
- 学习 [代码智能](./codebase-intelligence.md) 如何加速代码理解
- 了解 [P-EVR 任务编排](./p-evr-task-orchestration.md) 的闭环工作流

**运维关注？**
- 查看 [错误恢复](./error-recovery.md) 的容错机制
- 了解 [上下文管理](./context-management.md) 的成本控制
- 配置 [模型系统](./model-system.md) 与本地模型探测

**日常使用？**
- 掌握 [会话管理](./session-management.md) 提高工作效率

---

## 功能对比总览

| 特性类别 | PilotCode | Claude Code | Cursor | Copilot |
|---------|-----------|-------------|--------|---------|
| **代码索引** | 本地 + 语义 | 本地 | 云端 | 云端 |
| **上下文压缩** | 3级智能 | 基础 | 基础 | ❌ |
| **错误恢复** | 完整 | 基础 | 基础 | ❌ |
| **会话管理** | 项目级 | 基础 | 基础 | ❌ |
| **弱模型代偿** | 多维补偿 | ❌ | ❌ | ❌ |

---

## 相关文档

- [架构设计](../architecture/ARCHITECTURE.md) - 系统架构（含 Agent 系统、Hook 系统）
- [使用指南](../guides/README.md) - 用户指南
- [命令参考](../commands/README.md) - 命令文档
- [变更日志](../changelogs/CHANGELOG.md) - 开发历史
