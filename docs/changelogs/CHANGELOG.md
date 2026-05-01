# PilotCode 开发日志

本文档按时间倒序记录 PilotCode 的重要开发变更。

---

## 2026-05-02

### 模型配置与向导更新
- `models.json` 默认值全面更新至最新提供商模型（Qwen3.5-plus、kimi-k2.6、claude-4-sonnet、gpt-4o、qwen2.5 等）。
- 修复 `config --list` 中 `context_window` 保存 bug（llama-server 更新无法持久化）。
- 通用化模型文件扩展名清理，防止脏 ID 覆盖显示名称。
- 重写 `pc configure` 向导：默认国内模型、步骤重排、去重、本地服务器合并、空 Key 跳过。

### 编译器/语法验证（全端同步）
- `MissionAdapter` / `SimpleCLI` / `TUIController` / `WebSocketManager` 统一新增修改代码文件的编译检查。
- 自动检测编译命令（gcc、make、cmake、rustc、cargo 等），若 LLM 未执行则自动补做。
- `PytestRunnerVerifier` 重命名为 `TestRunnerVerifier`，扩展项目级构建系统检测（make、cmake、npm、cargo、go mod、meson）。
- 支持 `skip_project_build` 参数，避免不完整源码误报。

### CLI 与测试修复
- 修复 `main()` 内冗余局部 `import asyncio` 导致的 `UnboundLocalError`。
- 远程模型测试补充 mock `_probe_backend_limits`，测试耗时从 55 秒降至 0.33 秒。

---

## 2026-05-01

### 多模型支持三层架构重构
- 引入 `ModelCapabilities` 数据类、`MessageNormalizer` / `ResponseNormalizer`、`ParameterGenerator`。
- 统一 `chat_completion` 为单一路径，委托给三层处理。
- 新增架构文档与 49 个单元测试。

### Anthropic 协议完整支持
- `api_protocol` 解耦 Provider 身份与 API 协议格式。
- `ModelClient` 新增 Anthropic 规范化层，支持 `thinking` 块映射到 `reasoning_content`。
- 配置向导新增协议选择，CLI 新增 `--protocol` 选项。

### 启动诊断与 JSON 鲁棒性
- 默认启动 3 秒轻量级 LLM 探测，失败自动运行诊断。
- 生产代码全面替换贪婪正则 JSON 提取为平衡括号/方括号扫描。
- 解决尾随解释或代码块导致的静默解析失败。

### 基准测试与自适应补偿重构
- `benchmark.py` 拆分为 7 个维度模块，难度升级为中等-困难。
- 自适应补偿从基准分数驱动切换为运行时成功率驱动（滑动窗口 + 乐观默认值）。
- 2195 passed, 94 skipped。

---

## 2026-04-30

### E2E 测试框架扩展
- 新增 C 代码生成 E2E 任务（AVL 树、哈希表、JSON 解析器、内存池等）。
- 新增 `quest` 命令支持批量任务下发。
- WebSocket 支持 `auto_allow`，Runner 新增 `--timeout` 参数（默认 360s）。
- 超时优雅处理，分析结果使用 `PASS/FAIL` 替代 emoji 适配 Windows。

### FileEdit 智能预编辑预览
- 括号平衡、缩进一致性、关键结构删除检测。
- Tree-sitter 多语言语法检查（10+ 语言），两级严重程度。

### SWE-bench 与 Windows 兼容性
- SWE-bench Review Prompt 反删除保护、动态 explore 预算、FileEdit 范围守卫。
- Windows PowerShell 显示、编码回退、ANSI 清理、路径适配、超时延长。

---

## 2026-04-29

### SWE-bench 成功率提升
- 测试期望注入、断言差异比对、删除式修复检测。
- FileEdit 失败回退协议、降低补偿阈值与持久性弱模型阈值。
- 改进调用链分析的 explore/execution/review Prompt。

---

## 2026-04-27

### `/format` 与 `/lint` 命令增强
- **参数透传**：两个命令现在支持将额外参数直接透传给底层工具（`black`/`autopep8`、`ruff`/`flake8`）。
- **常用示例**：
  - `/lint --fix` — 自动修复可修复的问题
  - `/format --diff` — 预览改动差异，不写入文件
  - `/format --check` — 检查格式，不写入文件
- **范围说明**：目前仅支持 **Python** 语言。如需支持其他语言（如 `clang-format`、`prettier`、`eslint` 等），请联系开发者。
- **文档更新**：新增独立命令文档 `docs/commands/format.md`、`docs/commands/lint.md`。

### 文档清理：统一目录路径更新
- 将散落在各文档中的旧路径（`~/.config/pilotcode/`、`~/.local/share/pilotcode/`、`~/.cache/pilotcode/`）全部更新为新的统一路径 `~/.pilotcode/`。
- 涉及文件：`docs/features/*`、`docs/architecture/*`、`docs/plugins/*`、`docs/guides/*`、`docs/commands/session.md` 等 10+ 个文档。

---

## 2026-04-26

### 统一目录结构（Unified Directory Layout）
- **变更**：所有 PilotCode 用户级数据统一迁移到 `~/.pilotcode/` 下，分为四个子目录：
  - `config/` — 用户可编辑的配置（`settings.json`、`model_capability.json`）
  - `data/` — 持久化应用数据（`sessions/`、`agents/`、`knowhow/`、`forks.json`）
  - `cache/` — 可安全删除的缓存（`prompt_cache/`、`embeddings/`、`index/`、`plans/`）
  - `themes/` — TUI 主题文件
- **项目级数据**仍保留在 `{project}/.pilotcode/`（`memory/`、`snapshots/`、`backups/`）。
- **迁移脚本**：自动将旧路径（`~/.config/pilotcode/`、`~/.local/share/pilotcode/`、`~/.cache/pilotcode/`）中的数据迁移到新位置。
- **代码影响**：15 个源文件 + `install.sh` 更新为使用 `utils/paths.py` 中的集中式路径定义。

### CWD 漂移修复（3 类问题）
- **问题**：会话加载、保存、PLAN 模式下工作目录不一致，导致文件操作指向错误目录。
- **修复**：所有涉及 cwd 的场景统一采用三级 fallback 链：
  ```
  store.cwd → config.cwd → self.cwd
  ```
- **影响范围**：`_list_sessions`、`session_save`、`session_load`、PLAN 模式 `MissionAdapter`、auto-save 路径解析。

### 会话持久化格式升级
- **变更**：移除旧的 `.json.gz` 格式支持，仅保留增量 JSON Lines 格式。
- **文件结构**：
  ```
  {sid}.index.json      # 段索引
  {sid}.meta.json       # 用户可见元数据
  {sid}.data.{n}.jsonl  # 数据段（JSON Lines）
  ```
- **限制**：`MAX_SEGMENTS = 2`，`SEGMENT_MAX_MESSAGES = 50`。
- **清理**：自动删除 `~/.local/share/pilotcode/sessions/` 下遗留的旧格式 `.json.gz` 文件。

### 依赖调整：运行时工具移至核心依赖
- **pytest / pytest-asyncio**：从 `[dev]` 移至核心依赖（L2 verifier 运行时调用）。
- **black / ruff / mypy**：从 `[dev]` 移至核心依赖（`/format`、`/lint`、L3 adaptive verifier 运行时调用）。
- **tree-sitter 依赖重组**：
  - C/C++ 解析器（`tree-sitter`、`tree-sitter-c`、`tree-sitter-cpp`）→ 核心依赖
  - JS/Go/Rust/Java 解析器 → `[index]` 可选 extras

### Windows 安装脚本
- **新增 `install.cmd`**：Batch 脚本，兼容 Win7+，支持 `--dev`、`--index`、`--help` 标志。
- **修复**：`set /p` 提示语中包含 `)` 导致 batch 解析崩溃的问题。
- **同步**：`install.sh` 更新为相同的标志支持。

### 文档更新
- `README.md`、`README_EN.md`、`QUICKSTART.md`、`QUICKSTART_EN.md`、`WINDOWS_GUIDE.md` 更新以引用新路径和 `install.cmd`/`install.sh`。

---

## 2026-04-25 及之前（近期重要变更摘要）

### Web UI
- Web UI 服务在 HTTP 8080 / WebSocket 8081 上运行。
- 统一存储根使用 `~/.pilotcode/`。

### 模型能力自适应
- 支持运行时探测本地模型能力（上下文窗口、工具支持、视觉支持）。
- 支持后端：`llama.cpp`、`Ollama`、`vLLM`、`LiteLLM`、OpenAI-compatible。
- 弱模型代偿模式：框架级多维补偿引擎，针对 Qwen3-Coder-30B 等本地模型优化。

### 代码索引
- 支持 15+ 语言（Python 正则高速提取，其他 Tree-sitter AST）。
- 分层索引（Tier 1/2/3）解决大型代码库上下文窗口瓶颈。
- 项目记忆知识库（`.pilotcode/memory/`）自动注入相关上下文。

---

## 记录规范

- **日期格式**：`YYYY-MM-DD`
- **内容结构**：每日下按模块分组，每组包含「变更简述」和「影响范围」
- **文件位置**：`docs/changelogs/CHANGELOG.md`

如需查看更早期的开发记录，请参考：
- `docs/archive/FEATURE_LIST.md` — 详细功能清单
- `docs/archive/FEATURE_AUDIT.md` — 功能审计报告
- `docs/archive/IMPLEMENTATION_*.md` — 各轮实现记录
