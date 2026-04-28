# PilotCode 文档中心

本文档中心包含 PilotCode 项目的所有技术文档，按主题分类组织。

---

## 📁 目录结构

### 🏗️ [architecture/](architecture/) - 架构文档
包含系统架构设计、架构分析和架构演进文档。

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 系统架构总览 |
| [agent-system.md](architecture/agent-system.md) | Agent 编排系统 |
| [hook-system.md](architecture/hook-system.md) | Hook 扩展系统 |
| [tools-commands-plugins.md](architecture/tools-commands-plugins.md) | Tools/Commands/Plugins 对比分析 |

### ✨ [features/](features/) - 功能文档
包含功能特性介绍和使用说明。

**核心特性：**
| 文档 | 说明 |
|------|------|
| [README.md](features/README.md) | **功能特性索引** |
| [codebase-intelligence.md](features/codebase-intelligence.md) | 代码智能：索引、搜索与记忆 |
| [context-management.md](features/context-management.md) | 上下文管理 |

| [error-recovery.md](features/error-recovery.md) | 错误恢复与重试 |
| [session-management.md](features/session-management.md) | 会话管理 |
| [unified-directory-structure.md](../guides/unified-directory-structure.md) | 统一目录结构 |

### 📚 [guides/](guides/) - 指南文档
包含配置指南、使用教程和测试说明。

| 文档 | 说明 |
|------|------|
| [README.md](guides/README.md) | **指南索引** |
| [WINDOWS_GUIDE.md](guides/WINDOWS_GUIDE.md) | Windows 安装指南 |
| [llm-setup.md](guides/llm-setup.md) | LLM 接口设置指南 |
| [analyze-large-project.md](guides/analyze-large-project.md) | 大型项目代码分析指南 |
| [development-workflow.md](guides/development-workflow.md) | 开发工作流指南 |
| [tui-automation-testing.md](guides/tui-automation-testing.md) | TUI 自动化测试指南 |
| [e2e-testing.md](guides/e2e-testing.md) | E2E 测试与三层诊断框架 |

### 🔧 [commands/](commands/) - 命令文档
包含所有可用命令的详细说明。

| 文档 | 说明 |
|------|------|
| [README.md](commands/README.md) | **命令索引** |

### 🛠️ [tools/](tools/) - 工具文档
包含所有可用工具的详细说明。

| 文档 | 说明 |
|------|------|
| [README.md](tools/README.md) | **工具索引** |

### 🔌 [plugins/](plugins/) - 插件文档
包含插件系统文档。

| 文档 | 说明 |
|------|------|
| [README.md](plugins/README.md) | **插件系统索引** |

### 📜 [changelogs/](changelogs/) - 变更日志
包含按日期记录的开发和版本变更。

| 文档 | 说明 |
|------|------|
| [CHANGELOG.md](changelogs/CHANGELOG.md) | 开发日志总览 |
| [daily/](changelogs/daily/) | 按日记录的详细变更 |

### 📦 [archive/](archive/) - 归档文档
包含开发过程中的过程性文档。

| 文档 | 说明 |
|------|------|
| FEATURE_LIST.md | 功能清单（过程文档） |
| FEATURE_AUDIT.md | 功能审计（过程文档） |
| MISSING_FEATURES.md | 缺失功能分析（过程文档） |
| implementation/ | 实现过程文档 |
| comparison/ | 对比分析过程文档 |
| progress/ | 进度跟踪文档 |

---

## 📄 根目录核心文档

根目录保留了最常用的核心文档：

- [**README.md**](../README.md) - 项目简介
- [**README_EN.md**](../README_EN.md) - English Version
- [**QUICKSTART.md**](../QUICKSTART.md) - 快速开始指南（中文版）
- [**QUICKSTART_EN.md**](../QUICKSTART_EN.md) - Quick Start Guide (English)
- [**STARTUP_GUIDE.md**](../STARTUP_GUIDE.md) - 启动指南
- [**STATUS.md**](../STATUS.md) - 项目状态

---

## 🔍 快速导航

**新用户？** 从 [QUICKSTART.md](../QUICKSTART.md) 开始。

**配置 LLM？** 查看 [guides/llm-setup.md](guides/llm-setup.md) 了解如何连接各种 LLM API。

**分析大型项目？** 查看 [guides/analyze-large-project.md](guides/analyze-large-project.md) 学习代码索引和搜索。

**开发工作流？** 查看 [guides/development-workflow.md](guides/development-workflow.md) 了解 AI 辅助开发流程。

**运行 E2E 测试？** 查看 [guides/e2e-testing.md](guides/e2e-testing.md) 了解三层诊断框架。

**想了解功能？** 查看 [features/](features/) 目录。

**查看命令？** 查看 [commands/](commands/) 目录。

**查看工具？** 查看 [tools/](tools/) 目录。

**查看变更历史？** 查看 [changelogs/CHANGELOG.md](changelogs/CHANGELOG.md)。
