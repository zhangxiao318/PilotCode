# PilotCode 改进实施报告

**日期**: 2026-04-15

---

## 一、原始问题回顾

根据 SWE-bench 测试，PilotCode 存在以下核心问题：

1. **Patch 不完整**（Requests 实例 `psf/requests-3563`）
   - Gold patch 涉及 3 个文件（adapters.py, models.py, sessions.py）
   - PilotCode 仅修改了 adapters.py 的一部分

2. **语法错误**（Pytest 实例 `pytest-dev/pytest-13626`）
   - 生成的 patch 中 `try:` 缩进只有 2 个空格，导致 `IndentationError`

3. **Docker Evaluation 网络阻塞**
   - SWE-bench 容器内 GitHub 访问极慢，无法完成 instance image 构建

---

## 二、已实施的改进

### 改进 1：FileEdit 自动语法校验 + 回滚

**文件**: `src/pilotcode/tools/file_edit_tool.py`

**修改内容**: 在 `edit_file_content` 中，写入文件后如果文件是 `.py`，自动运行 `py_compile.compile()`。若发现语法错误，**立即回滚到原始内容**并返回错误。

**验证结果**: ✅ **有效**

```python
# 测试：故意制造缩进错误
result = await edit_file_content(
    test_file,
    "def hello():\n    print('world')\n  if True:\n        print('yes')\n",
    "def hello():\n    print('world')\nif True:\n        print('yes')\n"
)
# 结果:
# "Edit introduced Python syntax error, change rolled back: 
#  IndentationError: unindent does not match any outer indentation level"
```

**影响**: LLM 现在会在 FileEdit 失败后收到明确的语法错误反馈，而不是把错误代码留在工作区。

---

### 改进 2：Harness Prompt 增强

**文件**: `swe_bench_test/run_pilotcode_harness.py`

**修改内容**: 将原来的简单指令替换为包含 **CRITICAL WORKFLOW** 的结构化 prompt，强制要求：
1. 先读取所有相关文件
2. 逐条列出需要修改的文件
3. 一次只编辑一个文件
4. 每次编辑 Python 文件后运行 `py_compile` 验证
5. 编辑完成后运行 `git diff` 做 checklist 检查

**验证结果**: ⚠️ **部分有效**

对比两次运行结果：

| 运行 | adapters.py 修改 | 是否完整 |
|------|------------------|----------|
| 第一次（旧 prompt） | 只加了 `enforce_content_length=True` | ❌ 遗漏 `request_method` 和其他文件 |
| 第四次（新 prompt） | 加了 `enforce_content_length=True` 和 `request_method` | ⚠️ 仍有 models.py 和 sessions.py 未修改 |

**结论**: prompt 改进提升了**单个文件内的修改完整度**，但没有根本解决**多文件协同修改**时 LLM 提前终止的问题。

---

### 改进 3：Harness Shell 转义修复

**文件**: `swe_bench_test/run_pilotcode_harness.py`

**修改内容**: 原来 `run_pilotcode` 中直接用双引号包裹 prompt：
```python
f'-p "{prompt}"'
```
当 prompt 包含换行和引号时，导致 `/bin/sh: Syntax error`。

修复为使用 `shlex.quote(prompt)` 进行正确的 shell 转义。

**验证结果**: ✅ **有效**
修复后 prompt 中的多行文本和引号不再导致 shell 语法错误。

---

### 改进 4：Shallow Clone 优化

**文件**: `swe_bench_test/run_pilotcode_harness.py`

**修改内容**: `clone_and_checkout` 函数从完整 clone 改为：
1. `git clone --depth 1 --filter=blob:none`
2. `git fetch --depth 1 origin <commit>`
3. 失败时 fallback 到完整 fetch

**验证结果**: ✅ **有效**
- requests 仓库的 clone 和 checkout 速度显著提升
- pytest 仓库的 shallow clone 在宿主机上 7 秒内完成

**注意**: Docker build 中的 clone 仍然受网络代理问题影响（见下文）。

---

### 改进 5：System Prompt 增强

**文件**: `src/pilotcode/query_engine.py`

**修改内容**: 在默认 system prompt 末尾新增 **Code Editing Best Practices** 段落，强调：
- FileEdit 必须精确匹配
- 编辑后必须验证 Python 语法
- 多文件修改必须使用 checklist
- 完成前必须 review `git diff`

**验证结果**: ⏳ **长期效果待观察**
该改进对所有 PilotCode 对话生效，需要更多实际任务来验证长期效果。

---

## 三、重测结果汇总

### 测试 A：Requests 实例（`psf/requests-3563`）

**Gold Patch 要求**: 修改 adapters.py（2 处）、models.py（2 处）、sessions.py（2 处）

**改进前结果**: 
- patch 长度: 507 chars
- 仅修改 adapters.py 第一处（+ `enforce_content_length=True`）

**改进后结果**:
- patch 长度: 557 chars  
- 修改了 adapters.py 第一处（+ `enforce_content_length=True` 和 `request_method`）
- **但仍然遗漏** models.py 和 sessions.py

**分析**: LLM 在成功修改 adapters.py 并通过 `py_compile` 验证后，认为主要任务已完成，没有继续检查 bug report 中的其余要求。这说明即使 prompt 要求了 checklist，LLM 的执行意愿仍然不足。

---

### 测试 B：Pytest 实例（`pytest-dev/pytest-13626`）

**Gold Patch**: 在 `runtestprotocol` 中添加 `try/finally`

**改进前结果**:
- 生成 patch，但 `try:` 缩进 2 空格，导致 `IndentationError`

**改进后结果**:
- 重新用增强 prompt 测试时，PilotCode 的 FileEdit 触发了新的语法校验，回滚了错误修改
- LLM 随后尝试用 Bash/sed 直接修改，但最终没有生成有效 patch（可能因多次尝试失败而放弃）

**分析**: 语法校验回滚机制**确实防止了错误代码残留**，但也暴露出 LLM 在面对复杂块级编辑时的**工具选择能力有限**——当 FileEdit 多次失败后，LLM 没有很好的 fallback 策略。

---

## 四、仍然存在的问题

### 问题 1：LLM 提前终止（Premature Completion）

**表现**: 修改了 1-2 个文件后，即使 prompt 明确要求 checklist，LLM 仍然停止工具调用并输出完成语。

**根因**: 
- QueryEngine 的终止条件完全依赖 LLM 是否继续调用工具
- 没有外部的"任务完成度 validator"强制 LLM 继续

**建议**: 引入一个显式的 `VerifyTaskCompletion` 工具，或让 harness 在 LLM 停止后自动检查 `git diff` 与 bug report 的匹配度，如果不匹配则追加一条系统消息要求继续修改。

### 问题 2：FileEdit 对复杂块编辑仍然脆弱

**表现**: 对于 `try/finally` 重构这种需要精确控制多行缩进的修改，FileEdit 经常匹配失败或产生错误。

**根因**:
- `str.replace()` 机制对 LLM 的文本记忆精度要求过高
- 没有行号/AST 级别的编辑工具

**建议**: 新增 `ApplyPatch` 工具（接受 unified diff）或 `EditLines` 工具（接受起始行号和替换文本），降低 LLM 的精确记忆负担。

### 问题 3：Docker 容器内网络代理不稳定

**表现**: 宿主机上 `git clone` 只需 2-7 秒，但 SWE-bench Docker build 中同样的操作耗时 30 分钟以上。

**根因**:
- Docker build 的 `ENV http_proxy` 配置对 git HTTPS 不一定生效
- 容器内的 DNS 解析或 TLS 握手存在额外延迟

**建议**:
1. 将 repo 提前 clone 到宿主机，然后通过 `COPY` 进 Docker image（跳过容器内 clone）
2. 或搭建本地 git 镜像 / 使用 `git config --global url.` 重定向

---

## 五、下一步优先级

| 优先级 | 改进项 | 预期效果 |
|--------|--------|----------|
| **P0** | Harness 中添加任务完成度检查（基于 bug report 关键词匹配 git diff） | 强制 LLM 完成所有修改 |
| **P0** | 将宿主机 pre-cloned repo COPY 进 Docker | 解决 evaluation 网络阻塞 |
| **P1** | 新增 `ApplyPatch` 或 `EditLines` 工具 | 解决复杂块编辑的精确性问题 |
| **P1** | 引入 Plan/Verify 子 Agent | 提升多文件修改的系统性 |
| **P2** | 建立本地 SWE-bench 镜像缓存 | 加速重复 evaluation |

---

## 六、总结

本次改进已经在 **代码安全（语法校验回滚）**、**提示工程（结构化 workflow）**、**基础设施（shallow clone + shell 转义）** 三个方面取得了实质性进展。PilotCode 生成的 patch 质量有所提升（requests 实例从修改 1 处提升到 2 处），但距离完整解决真实 SWE-bench 实例仍有差距。

核心瓶颈已从"工具会写错代码"转变为"LLM 难以在复杂多文件任务中保持完整的执行链条"。解决这一问题的关键在于：**在 LLM 外部增加任务状态跟踪和完成度验证机制**，而不是单纯依赖 LLM 的自我约束。
