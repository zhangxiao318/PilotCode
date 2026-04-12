# PilotCode 指南文档

本目录包含 PilotCode 的使用指南和教程文档。

---

## 新用户入门

| 文档 | 说明 | 推荐阅读顺序 |
|------|------|-------------|
| [QUICKSTART.md](./QUICKSTART.md) | 快速开始指南 - 5分钟上手 | ⭐ 第1步 |
| [QUICKSTART_EN.md](./QUICKSTART_EN.md) | Quick Start Guide (English) | ⭐ 第1步 |
| [WINDOWS_GUIDE.md](./WINDOWS_GUIDE.md) | Windows 系统安装指南 | ⭐ 第2步 |

---

## 配置指南

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [llm-setup.md](./llm-setup.md) | LLM 接口设置指南 | 配置 OpenAI、Claude、本地模型等 |
| [SETUP_QWEN_API.md](./SETUP_QWEN_API.md) | Qwen API 设置指南（内部） | 连接内部 Qwen 服务 |

---

## 使用指南

| 文档 | 说明 | 适用场景 |
|------|------|----------|
| [analyze-large-project.md](./analyze-large-project.md) | 大型项目代码分析指南 | 分析大型代码库、代码搜索 |
| [development-workflow.md](./development-workflow.md) | 开发工作流指南 | AI 辅助开发、Git 集成、测试 |

---

## 学习路径

### 路径1：快速体验（5分钟）

1. [QUICKSTART.md](./QUICKSTART.md) - 完成安装和首次运行
2. 尝试与 AI 对话，体验基础功能

### 路径2：完整配置（15分钟）

1. [QUICKSTART.md](./QUICKSTART.md) - 安装
2. [llm-setup.md](./llm-setup.md) - 配置 LLM 接口
3. 开始实际项目开发

### 路径3：高效开发（30分钟）

1. [QUICKSTART.md](./QUICKSTART.md) - 安装
2. [llm-setup.md](./llm-setup.md) - 配置 LLM
3. [analyze-large-project.md](./analyze-large-project.md) - 学习代码分析
4. [development-workflow.md](./development-workflow.md) - 掌握开发工作流

---

## 常见问题

**Q: 如何连接到我的 OpenAI API？**  
A: 查看 [llm-setup.md](./llm-setup.md) 中的 OpenAI 配置示例。

**Q: 如何分析公司的大型项目？**  
A: 查看 [analyze-large-project.md](./analyze-large-project.md)，学习使用 `/index` 和 `/search` 命令。

**Q: 如何用 PilotCode 提交代码？**  
A: 查看 [development-workflow.md](./development-workflow.md) 中的 Git 集成部分。

**Q: Windows 上如何安装？**  
A: 查看 [WINDOWS_GUIDE.md](./WINDOWS_GUIDE.md)。

---

## 其他资源

- [架构文档](../architecture/) - 系统设计文档
- [命令文档](../commands/) - 所有可用命令
- [工具文档](../tools/) - 工具详细说明
- [插件文档](../plugins/) - 插件系统
