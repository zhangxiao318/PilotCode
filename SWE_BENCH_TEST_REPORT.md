# SWE-bench + PilotCode 测试报告

**生成时间**: 2026-04-15

---

## 一、环境准备结果

| 组件 | 状态 | 说明 |
|------|------|------|
| **Docker** | ✅ | `docker.io 29.1.3` 安装成功，配置了国内镜像加速（DaoCloud / 中科大 / 网易） |
| **SWE-bench** | ✅ | `swebench 4.1.0` 及全部依赖（datasets, docker, ghapi, modal 等）安装成功 |
| **PilotCode** | ✅ | 修改 `pyproject.toml` 中 Python 要求从 `>=3.11` 改为 `>=3.10` 后，`pip install -e .` 成功 |
| **LLM 连通性** | ✅ | 本地模型代理 `http://172.19.201.40:3509/` 响应正常 |

---

## 二、测试 1：PilotCode 基础能力测试

**脚本**: `swe_bench_test/test_pilotcode_simple.py`

**测试内容**: 在临时 Git 仓库中人为引入一个简单 bug（`add` 函数缺少 `return`），观察 PilotCode 是否能独立修复并产出 `git diff` patch。

**结果**: ✅ **PASS**

```
GIT DIFF:
 diff --git a/math_utils.py b/math_utils.py
index cca3e9a..81f066f 100644
--- a/math_utils.py
+++ b/math_utils.py
@@ -1,3 +1,3 @@
 def add(a, b):
     # Bug: missing return
-    a + b
+    return a + b

SUCCESS: PilotCode produced a patch that includes 'return'
```

**结论**: PilotCode 具备独立完成简单代码修复、生成标准 patch 的能力。

---

## 三、测试 2：SWE-bench 基础设施连通性测试

**脚本**: `swe_bench_test/test_swebench_pipeline.py`

**结果**:
- Docker Client 连接: ✅ PASS
- SWE-bench 核心模块导入: ✅ PASS
- `make_test_spec` API 调用: ⚠️ **部分失败**（因使用了 mock version 触发预期内的失败，非关键错误）

**结论**: SWE-bench 框架和 Docker 运行时可以正常初始化。

---

## 四、测试 3：端到端 Harness（Requests 实例 `psf/requests-3563`）

### 4.1 PilotCode Patch 生成

**脚本**: `swe_bench_test/run_pilotcode_harness.py`

**结果**: ✅ **成功生成 predictions.jsonl**

```jsonl
{"instance_id": "psf__requests-3563", "model_name_or_path": "pilotcode", "model_patch": "diff --git a/requests/adapters.py ..."}
```

Patch 内容: 在 `requests/adapters.py` 的 `urlopen()` 调用中增加了 `enforce_content_length=True`。

**问题**: 该 patch **不完整**。真实的修复还需要修改 `requests/models.py`（导入 `ConnectionError` 并处理不完整内容），但 PilotCode 只完成了 `adapters.py` 的修改。

### 4.2 SWE-bench Evaluation 评分

**结果**: ⚠️ **未完成**

- `run_evaluation` 能够正常启动，并成功构建 `base image` 和 `env image`。
- 但在拉取/构建 `instance image` 时遇到网络限制（`docker.io/swebench/...` 403 Forbidden 或容器内 GitHub 访问超时），无法在合理时间内完成。

---

## 五、测试 4：端到端 Harness（Pytest 实例 `pytest-dev/pytest-13626`）

### 5.1 实例构造

从 GitHub PR #13626 提取了真实 bug 修复，构造了本地 `mini_dataset_pytest.json`:
- **base_commit**: `5898e9c7a`（已验证在默认分支上可达）
- **真实 patch**: 用 `try/finally` 包裹 `runtestprotocol` 中的执行逻辑，确保 `KeyboardInterrupt` 时也能清理 `item._request` 和 `item.funcargs`

### 5.2 Gold Patch 本地验证

为验证这个 bug 实例本身是有效的，先进行了 **Gold Patch 验证**:

**步骤**:
1. `git apply` test patch（新增测试）
2. 运行新测试 → **FAILED**（复现了 bug）
3. `git apply` code patch（真实修复）
4. 再次运行新测试 → **PASSED**（修复生效）

```bash
# 未修复时
FAILED testing/test_runner.py::TestExecutionNonForked::test_keyboardinterrupt_clears_request_and_funcargs
E       assert not <FixtureRequest ...>

# 修复后
PASSED testing/test_runner.py::TestExecutionNonForked::test_keyboardinterrupt_clears_request_and_funcargs
```

**结论**: 该实例是一个有效的 SWE-bench 测试用例。

### 5.3 PilotCode Patch 生成与验证

**结果**: ❌ **生成失败（语法错误）**

PilotCode 尝试修改 `src/_pytest/runner.py`，但最终产出的 patch 存在 **缩进错误**:

```diff
+  try:
+        rep = call_and_report(item, "setup", log)
```

`try:` 只缩进了 2 个空格，与函数体的 4 空格缩进不匹配。运行 `py_compile` 验证:

```bash
IndentationError: unindent does not match any outer indentation level (runner.py, line 128)
```

**结论**: 在这个真实、较复杂的代码修改任务上，PilotCode 未能生成语法正确的 patch。

---

## 六、测试 5：SWE-bench Docker Evaluation（完整链路）

### 6.1 已验证通过的环节
- 数据集加载 ✅
- `make_test_spec` ✅
- Docker base image 构建 ✅
- Docker env image 构建 ✅

### 6.2 阻塞环节

**Instance image 构建失败**，原因如下:

| 尝试 | 结果 | 原因 |
|------|------|------|
| 拉取官方 swebench instance 镜像 | ❌ 403 | 国内镜像加速器对 `docker.io/swebench/...` 返回 403 |
| 强制本地构建（requests） | ❌ exit 128 | `git clone --single-branch` 无法获取 2016 年的老 commit |
| 强制本地构建（pytest） | ❌ 超时 | Docker 容器内通过代理访问 GitHub 极慢，30 分钟未 clone 完 |
| PilotCode harness clone | ❌ 300s 超时 | 后台任务中 `git clone pytest` 超时（同网络下手动 clone 仅 7s） |

**根因**: 后台任务中 `sg docker -c "..."` 启动的 shell 层存在严重的 **stdout 缓冲** 和 **网络代理不稳定** 问题，导致 Docker build 中的 `git clone` 无法在规定时间内完成。

---

## 七、总体结论

> **这台机器可以运行 SWE-bench，并且可以与 PilotCode 集成测试，但当前网络环境导致完整的 Docker-based evaluation 无法在合理时间内跑通。**

### 量化结果

| 测试项 | 结果 |
|--------|------|
| PilotCode 简单 bug 修复 | ✅ **成功** |
| SWE-bench 框架安装与初始化 | ✅ **成功** |
| SWE-bench Docker base/env 构建 | ✅ **成功** |
| SWE-bench Docker instance 构建/评分 | ❌ **因网络阻塞未完成** |
| PilotCode + requests 实例 patch | ⚠️ **部分正确（不完整）** |
| PilotCode + pytest 实例 patch | ❌ **语法错误（缩进问题）** |
| Gold patch 本地验证（pytest） | ✅ **有效（测试从 FAIL→PASS）** |

### 建议

1. **若仅需跑 PilotCode 的推理/开发流程**: 无需 Docker，当前环境完全可用。
2. **若要跑完整的 SWE-bench evaluation**: 需要解决 Docker 容器内稳定、高速访问 GitHub 的问题（如配置 Docker build 的 HTTP 代理持久化、使用本地 registry 缓存预构建镜像等）。
3. **PilotCode 本身**: 在简单任务上表现良好，但在复杂真实仓库上的 patch 质量仍有提升空间（需要更精准的 `FileEdit` 和上下文理解）。

---

## 附录：测试脚本列表

所有测试脚本位于 `/home/zx/mycc/PilotCode/swe_bench_test/`:

| 脚本 | 作用 |
|------|------|
| `test_pilotcode_simple.py` | 极简本地测试：创建临时 Git 仓库 → 让 PilotCode 修 bug → 验证 `git diff` |
| `test_swebench_pipeline.py` | 验证 SWE-bench + Docker 的核心接口 |
| `build_mini_dataset.py` | 从 GitHub PR 构建单个 SWE-bench instance |
| `run_pilotcode_harness.py` | 核心 Harness：加载数据集 → clone 仓库 → 调用 PilotCode → 提取 patch → 生成 `predictions.jsonl` |
| `debug_eval.py` | 直接调用 `swebench.harness.run_evaluation` 进行调试 |
