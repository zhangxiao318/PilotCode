# PilotCode 功能特性

本文档介绍 PilotCode 的核心功能特性，包括设计原理、使用方法和与其他工具的对比。

---

## 核心特性

| 特性 | 说明 | 完成度 |
|------|------|--------|
| **Agent 系统** | 多代理协作编排 | ✅ 完整 |
| **代码索引与搜索** | 语义/符号/正则搜索 | ✅ 完整 |
| **Hook 系统** | 生命周期事件扩展 | ✅ 核心 |
| **智能上下文压缩** | Token 管理与压缩 | ✅ 完整 |
| **错误恢复与重试** | 容错与降级 | ✅ 完整 |
| **会话管理** | 对话持久化与恢复 | ✅ 完整 |

---

## 特性文档

### AI 协作

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [agent-system.md](./agent-system.md) | Agent 编排系统 | 复杂任务分解、多代理协作 |
| [hook-system.md](./hook-system.md) | 生命周期 Hook | 扩展系统行为、自定义验证 |

### 代码智能

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [code-indexing.md](./code-indexing.md) | 代码索引与搜索 | 大型项目分析、代码查找 |

### 模型与配置

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [model-configuration.md](./model-configuration.md) | 模型配置与能力验证 | 自定义模型、本地模型部署、参数调优 |

### 系统稳定性

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [context-management.md](./context-management.md) | 上下文窗口管理 | Token 监控、自动/手动压缩、状态查看 |
| [context-compaction.md](./context-compaction.md) | 智能上下文压缩 | 压缩算法与策略 |
| [mempo-context-management.md](./mempo-context-management.md) | MemPO 上下文管理 | 基于 MemPO 论文的智能记忆管理 |
| [error-recovery.md](./error-recovery.md) | 错误恢复与重试 | 网络不稳定、API 限流 |
| [session-management.md](./session-management.md) | 会话管理 | 多项目管理、历史恢复 |

---

## 快速导航

**开发者？**
- 了解 [Agent 系统](./agent-system.md) 如何组织多代理协作
- 学习 [代码索引](./code-indexing.md) 如何加速代码理解

**运维关注？**
- 查看 [错误恢复](./error-recovery.md) 的容错机制
- 了解 [上下文压缩](./context-compaction.md) 的成本控制
- 配置 [模型参数](./model-configuration.md) 与本地模型探测

**日常使用？**
- 掌握 [会话管理](./session-management.md) 提高工作效率
- 使用 [Hook 系统](./hook-system.md) 定制工作流

---

## 功能对比总览

| 特性类别 | PilotCode | Claude Code | Cursor | Copilot |
|---------|-----------|-------------|--------|---------|
| **Agent 编排** | 4种模式 | 基础 | 有限 | ❌ |
| **代码索引** | 本地 + 语义 | 本地 | 云端 | 云端 |
| **Hook 扩展** | ✅ | ✅ | ❌ | ❌ |
| **上下文压缩** | 3级智能 | 基础 | 基础 | ❌ |
| **错误恢复** | 完整 | 基础 | 基础 | ❌ |
| **会话管理** | 项目级 | 基础 | 基础 | ❌ |

---

## 开发归档

以下文档是开发过程中的过程性记录，已归档：

- [FEATURE_LIST.md](../archive/FEATURE_LIST.md) - 详细功能清单
- [FEATURE_AUDIT.md](../archive/FEATURE_AUDIT.md) - 功能审计报告
- [MISSING_FEATURES.md](../archive/MISSING_FEATURES.md) - 缺失功能分析

---

## 相关文档

- [架构设计](../architecture/ARCHITECTURE.md) - 系统架构
- [使用指南](../guides/README.md) - 用户指南
- [命令参考](../commands/README.md) - 命令文档
