# PilotCode 改进分析：基于 SWE-bench 测试结果

**分析时间**: 2026-04-15

---

## 一、测试中发现的核心问题

### 问题 1：Patch 不完整（Requests 实例）

**实例**: `psf/requests-3563`

**Gold Patch 涉及文件**:
1. `requests/adapters.py` — 2 处修改（添加 `enforce_content_length=True` 和 `request_method`）
2. `requests/models.py` — 2 处修改（导入 `ConnectionError` + 修改 `generate()` 异常处理）
3. `requests/sessions.py` — 2 处修改（导入 `ConnectionError` + 异常捕获扩展）

**PilotCode 表现**:
- **第一次运行**: 只修改了 `adapters.py` 中的第一处（`enforce_content_length=True`），遗漏了 `request_method` 以及 `models.py`、`sessions.py`
- **第二次运行**（相同 prompt）: 生成的 patch 为空，**完全没有修改任何文件**

**根因分析**:
1. **非确定性行为**: LLM 在相同输入下产生了截然不同的输出，说明系统对工具调用的控制力不足
2. **缺乏系统性验证**: 修改完一个文件后，LLM 认为任务已完成，没有主动检查是否还有其他文件需要修改
3. **Prompt 中的任务列表不够强制**: 虽然 bug report 列出了 4 项修改，但 LLM 没有将其当作必须逐条完成的 checklist

---

### 问题 2：语法错误（Pytest 实例）

**实例**: `pytest-dev/pytest-13626`

**Gold Patch**: 用 `try/finally` 包裹 `runtestprotocol` 中的执行逻辑

**PilotCode 表现**:
生成的 patch 中 `try:` 只缩进了 **2 个空格**，与函数体要求的 **4 个空格** 不匹配：

```diff
+  try:
+        rep = call_and_report(item, "setup", log)
```

运行 `py_compile` 验证：
```
IndentationError: unindent does not match any outer indentation level (runner.py, line 128)
```

**根因分析**:
1. **FileEdit 工具的脆弱性**: `FileEdit` 使用简单的 `str.replace()`，如果 LLM 提供的 `old_string` 或 `new_string` 稍有偏差（例如前导空格计算错误），就会写出语法错误的文件
2. **没有编辑后校验**: PilotCode 在调用 `FileEdit` 后，没有任何工具去验证文件是否仍然是合法的 Python 代码
3. **LLM 对空格/缩进不敏感**: 当前系统没有给 LLM 提供视觉化的缩进提示（如显示 tab/space 标记）

---

### 问题 3：Docker Evaluation 网络阻塞

**表现**:
- SWE-bench 的 `base image` 和 `env image` 可以本地构建成功
- 但 `instance image` 构建时，容器内的 `git clone https://github.com/...` 极慢或超时
- 即使宿主机上 `git clone` 只需 2-7 秒，Docker build 中的同样操作却 30 分钟未完成

**根因分析**:
1. **Docker build 的代理配置不完整**: 虽然修改了 `swebench/harness/dockerfiles/python.py` 加入了 `ENV http_proxy/https_proxy`，但 `git` 在 Docker build 中可能使用 `git://` 或 HTTPS 而不走代理
2. **后台任务输出缓冲**: `sg docker -c "..."` 启动的进程 stdout 被严重缓冲，导致无法及时观察进度和调试
3. **SWE-bench 镜像拉取受限**: 国内镜像加速对 `docker.io/swebench/...` 预构建镜像返回 403

---

## 二、PilotCode 系统层面的具体缺陷

### 缺陷 1：FileEdit 工具过于简单

**当前实现**（`src/pilotcode/tools/file_edit_tool.py`）:
```python
new_content = original_content.replace(old_string, new_string)
```

**问题**:
- 没有模糊匹配（fuzzy matching）能力，LLM 稍微差一个空格就会替换失败
- 替换成功后没有语法校验
- 没有行号定位机制，LLM 只能靠记忆来构造 `old_string`

### 缺陷 2：没有 "编辑后验证" 机制

**现状**: 工具执行链中没有 `ValidatePythonSyntax`、`CheckPatchCompleteness` 之类的工具。

**后果**:
- LLM 不知道自己的修改是否合法
- 错误会累积到最终 patch 中

### 缺陷 3：没有任务清单（Checklist）跟踪

**现状**: LLM 只看到一次性 prompt，没有状态化的任务追踪器告诉它 "还有 3 个文件未修改"。

**后果**:
- 容易在修改了 1-2 个文件后就宣布完成
- 无法处理需要跨多个文件协同修改的复杂 bug

### 缺陷 4：Query Engine 的终止条件过于宽松

**现状**（`src/pilotcode/components/repl.py`）:
```python
if not pending_tools:
    break
```

只要 LLM 不再调用工具，对话就结束。LLM 很容易在"我觉得差不多了"的时候停止，而不会主动验证是否遗漏。

---

## 三、改进方案（按优先级排序）

### 高优先级：立即改进

#### 1. 为 FileEdit 添加语法校验钩子

**实现思路**:
在 `file_edit_call` 或 `edit_file_content` 中，写入文件后，如果文件扩展名为 `.py`，自动运行 `py_compile` 检查语法：

```python
import py_compile
import tempfile

def validate_python_syntax(path: Path) -> str | None:
    if path.suffix != ".py":
        return None
    try:
        py_compile.compile(str(path), doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return f"Syntax error after edit: {e}"
```

如果校验失败，**自动回滚修改**并返回错误给 LLM，让 LLM 重新尝试。

#### 2. 增强 SWE-bench Harness 的 Prompt

**当前 prompt 的问题**: 只是简单描述了 bug，没有强制 LLM 必须完成所有修改。

**改进后的 prompt 模板**:
```python
PILOTCODE_PROMPT_TEMPLATE = """\
You are given a code repository and a bug report. Fix the bug with MINIMAL changes.

Bug Report:
{problem_statement}

IMPORTANT WORKFLOW:
1. Read ALL relevant files before making any edits.
2. Make edits one file at a time.
3. After each edit, run `git diff` to verify the change.
4. Before finishing, use a checklist to confirm EVERY item in the bug report has been addressed.
5. If you modify Python files, ensure they pass `python -m py_compile <file>`.
6. Do NOT explain your reasoning in the file contents.

Current working directory: {cwd}
Repository: {repo}
"""
```

#### 3. 添加 `ValidateFile` 工具

让 LLM 能够主动调用一个工具来验证修改后的文件是否合法：

```python
class ValidateFileInput(BaseModel):
    file_path: str
    validation_type: Literal["syntax", "exists", "diff"]
```

#### 4. 修复 Docker build 中的 GitHub 访问问题

**短期方案**:
在 `run_pilotcode_harness.py` 的 `clone_and_checkout` 中，使用 `--depth 1` + `git fetch origin <commit>` 来减少下载量：

```bash
git clone --depth 1 --filter=blob:none https://github.com/{repo}.git {work_dir}
cd {work_dir}
git fetch --depth 1 origin {commit}
git checkout {commit}
```

**长期方案**:
修改 SWE-bench 的 Dockerfile，在 `setup_repo.sh` 中加入代理配置和 shallow clone 优化。

---

### 中优先级：系统增强

#### 5. 引入行号版 FileEdit（或 diff patch 工具）

当前 `FileEdit` 依赖 LLM 记忆文本块。更可靠的方式是:
- 先让 LLM 使用 `FileRead` 读取文件
- 返回的行号信息一起传给 LLM
- LLM 使用行号范围指定替换内容

或者，新增一个 `ApplyPatch` 工具，直接接受 unified diff 格式，由程序解析并应用。

#### 6. 添加 "Plan & Verify" 子 Agent

在复杂任务（如 SWE-bench）开始时，先让一个子 Agent 做规划：
1. 分析 bug report
2. 列出需要修改的文件和具体修改点
3. 主 Agent 按计划执行
4. 最后再让一个子 Agent 验证 plan 的完成度

这已经在 Claude Code 的架构中被证明非常有效。

#### 7. 增强 System Prompt 的编程规范

在 `query_engine.py` 的 `_get_default_system_prompt` 中加入：

```markdown
## Code Editing Best Practices
- When using FileEdit, ensure `old_string` matches the file content EXACTLY, including indentation.
- After editing a Python file, always verify syntax with `python -m py_compile <filepath>`.
- Before declaring a task complete, review the full `git diff` to ensure no unintended changes.
- If a bug report mentions multiple files, create a checklist and address each one systematically.
```

---

### 低优先级：架构优化

#### 8. 支持 AST-aware 编辑

对于 Python 项目，可以使用 `libcst` 或 `redbaron` 提供 AST 级别的编辑工具。这样 LLM 只需要说 "在函数 X 的第 Y 行之后插入 Z"，工具就能精确完成，不受空格影响。

#### 9. 建立本地 SWE-bench 镜像缓存

由于 Docker Hub 访问受限，可以：
1. 在本地构建一次 base/env 镜像
2. 打 tag 保存到本地 registry 或 tar 包
3. 修改 `swebench` 代码优先使用本地镜像，避免重复构建

---

## 四、可立即落地的代码修改

### 修改 1：FileEdit 自动语法回滚

文件: `src/pilotcode/tools/file_edit_tool.py`

在 `edit_file_content` 函数末尾，写入文件后增加：

```python
# After write, validate Python syntax and rollback if invalid
if path.suffix == ".py":
    import py_compile, shutil
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as e:
        # rollback
        path.write_text(original_content, encoding="utf-8")
        return FileEditOutput(
            file_path=str(path),
            replacements_made=0,
            original_content=original_content,
            error=f"Edit introduced syntax error, rolled back: {e}",
        )
```

### 修改 2：Harness 中增加 shallow clone

文件: `swe_bench_test/run_pilotcode_harness.py`

```python
def clone_and_checkout(repo: str, commit: str, work_dir: str) -> bool:
    import shutil
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir, exist_ok=True)

    repo_url = f"https://github.com/{repo}.git"
    # Shallow clone to save time
    rc, _, stderr = run_cmd(f"git clone --depth 1 --filter=blob:none {repo_url} {work_dir}", timeout=300)
    if rc != 0:
        print(f"[ERROR] Failed to clone {repo}: {stderr}")
        return False

    rc, _, stderr = run_cmd(f"git fetch --depth 1 origin {commit}", cwd=work_dir, timeout=120)
    if rc != 0:
        # fallback: try full fetch
        rc, _, stderr = run_cmd(f"git fetch origin {commit}", cwd=work_dir, timeout=300)
        if rc != 0:
            print(f"[ERROR] Failed to fetch {commit}: {stderr}")
            return False

    rc, _, stderr = run_cmd(f"git checkout {commit}", cwd=work_dir, timeout=60)
    if rc != 0:
        print(f"[ERROR] Failed to checkout {commit}: {stderr}")
        return False

    return True
```

### 修改 3：增强 System Prompt

文件: `src/pilotcode/query_engine.py`

在 `_get_default_system_prompt` 末尾追加编程规范段落（见上文第 7 点）。

---

## 五、结论

本次 SWE-bench 测试揭示了 PilotCode 在 **复杂真实代码修复任务** 上的三个核心短板：

1. **工具可靠性不足**：`FileEdit` 的字符串替换机制在缩进敏感场景下极易出错
2. **缺乏自我验证**：编辑后没有语法检查、diff 检查、任务清单检查
3. **网络/基础设施瓶颈**：Docker 容器内的 GitHub 访问不稳定，导致无法跑通完整的 evaluation 评分

**改进优先级**:
- **P0**（立即做）: FileEdit 语法校验回滚 + Harness shallow clone
- **P1**（本周做）: 增强 System Prompt + Harness Prompt 中的强制 checklist
- **P2**（本月做）: 引入 Plan/Verify 子 Agent + AST-aware 编辑工具
- **P3**（按需）: 本地镜像缓存体系
