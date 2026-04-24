# PilotCode 文档中心

本文档中心包含 PilotCode 项目的所有技术文档，按主题分类组织。

---

## 📁 目录结构

### 🏗️ [architecture/](architecture/) - 架构文档
包含系统架构设计、架构分析和架构演进文档。

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | 系统架构总览 |
| [tools-commands-plugins.md](architecture/tools-commands-plugins.md) | Tools/Commands/Plugins 对比分析 |

### ✨ [features/](features/) - 功能文档
包含功能特性介绍和使用说明。

**核心特性：**
| 文档 | 说明 |
|------|------|
| [README.md](features/README.md) | **功能特性索引** |
| [agent-system.md](features/agent-system.md) | Agent 编排系统 |
| [code-indexing.md](features/code-indexing.md) | 代码索引与搜索 |
| [hook-system.md](features/hook-system.md) | Hook 扩展系统 |
| [context-compaction.md](features/context-compaction.md) | 智能上下文压缩 |
| [mempo-context-management.md](features/mempo-context-management.md) | MemPO 上下文管理 |
| [error-recovery.md](features/error-recovery.md) | 错误恢复与重试 |
| [session-management.md](features/session-management.md) | 会话管理 |

### 📚 [guides/](guides/) - 指南文档
包含配置指南和使用教程。

| 文档 | 说明 |
|------|------|
| [README.md](guides/README.md) | **指南索引** |
| [QUICKSTART.md](guides/QUICKSTART.md) | **快速开始指南** - 5分钟上手 |
| [QUICKSTART_EN.md](guides/QUICKSTART_EN.md) | **Quick Start Guide** (English) |
| [WINDOWS_GUIDE.md](guides/WINDOWS_GUIDE.md) | Windows 安装指南 |
| [llm-setup.md](guides/llm-setup.md) | LLM 接口设置指南 |
| [analyze-large-project.md](guides/analyze-large-project.md) | 大型项目代码分析指南 |
| [development-workflow.md](guides/development-workflow.md) | 开发工作流指南 |
| [tui-automation-testing.md](guides/tui-automation-testing.md) | TUI 自动化测试指南 |

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

### 🧪 [test/](test/) - 测试文档
包含 E2E 测试说明和三层诊断框架文档。

| 文档 | 说明 |
|------|------|
| [README.md](test/README.md) | **E2E 测试说明与三层诊断框架** |

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

- [**README.md**](../README.md) - 项目简介、快速开始
- [**README_EN.md**](../README_EN.md) - English Version
- [**QUICKSTART.md**](../QUICKSTART.md) - 快速开始指南
- [**QUICKSTART_EN.md**](../QUICKSTART_EN.md) - Quick Start Guide (English)
- [**STARTUP_GUIDE.md**](../STARTUP_GUIDE.md) - 启动指南
- [**STATUS.md**](../STATUS.md) - 项目状态

---

## 🔍 快速导航

**新用户？** 从 [QUICKSTART.md](../QUICKSTART.md) 或 [guides/QUICKSTART.md](guides/QUICKSTART.md) 开始。

**配置 LLM？** 查看 [guides/llm-setup.md](guides/llm-setup.md) 了解如何连接各种 LLM API。

**分析大型项目？** 查看 [guides/analyze-large-project.md](guides/analyze-large-project.md) 学习代码索引和搜索。

**开发工作流？** 查看 [guides/development-workflow.md](guides/development-workflow.md) 了解 AI 辅助开发流程。

**想了解功能？** 查看 [features/](features/) 目录。

**查看命令？** 查看 [commands/](commands/) 目录。

**查看工具？** 查看 [tools/](tools/) 目录。

**运行 E2E 测试？** 查看 [test/README.md](test/README.md) 了解三层诊断框架。
