# 面向不同能力模型的自适应设计（Model Capability Adaptation）

## 概述

PilotCode 的编排系统对底层大模型的能力有显著依赖：规划需要模型输出合法的 DAG JSON，执行需要模型生成正确的代码，验证需要模型做可靠的代码审查。当模型从 DeepSeek-V4 降级到本地 7B 模型时，这些假设会同时失效。

本系统通过**"模型能力评估 → 自适应配置映射 → 运行时动态校准"**的三层机制，使 PilotCode 能够：
1. **事前评估**：通过标准化基准测试量化模型在规划、编码、JSON 输出、推理、审查五个维度的能力
2. **事中适配**：根据评估结果自动调整任务粒度、验证严格度、规划策略
3. **事后校准**：在任务执行过程中持续收集反馈，动态修正能力评分

核心设计哲学：**默认假设模型强，运行时自动降级，而非默认保守造成过度干预。**

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Model Capability Adaptation                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     benchmark      ┌──────────────┐                      │
│  │   LLM API    │ ────────────────→ │  Capability  │                      │
│  │ (13 tests)   │                    │   Profile    │                      │
│  └──────────────┘                    └──────┬───────┘                      │
│                                             │                               │
│                    ┌────────────────────────┼────────────────────────┐     │
│                    │                        │                        │     │
│                    ▼                        ▼                        ▼     │
│           ┌──────────────┐        ┌─────────────────┐       ┌──────────────┐│
│           │   CLI Test   │        │ AdaptiveConfig  │       │   Runtime    ││
│           │  --test cap  │        │     Mapper      │       │  Calibrator  ││
│           └──────────────┘        └────────┬────────┘       └──────┬───────┘│
│                                            │                       │       │
│                                            ▼                       ▼       │
│                                   ┌─────────────────┐    ┌─────────────────┐│
│                                   │ AdaptiveOrche-  │    │  Calibrated     ││
│                                   │   stratorConfig │    │  Capability     ││
│                                   │  (planning/     │    │  (per-dimension)││
│                                   │   verify/granul-│    │                 ││
│                                   │   arity/retry)  │    │                 ││
│                                   └────────┬────────┘    └─────────────────┘│
│                                            │                                │
│                                            ▼                                │
│                                   ┌─────────────────┐                       │
│                                   │  MissionAdapter │                       │
│                                   │  (plan + run)   │                       │
│                                   └─────────────────┘                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第一层：模型能力评估（Benchmark）

### 评估维度

能力评估覆盖 5 个维度、13 个细分测试：

| 维度 | 子维度 | 测试内容 | 权重 |
|---|---|---|---|
| **Planning** | dag_correctness | 输出合法 JSON DAG | 高 |
| | task_granularity | 任务粒度是否合理（3-8 个/阶段） | 高 |
| | dependency_accuracy | 依赖关系无循环、无悬空引用 | 高 |
| **Task Completion** | code_correctness | 生成可运行、结果正确的代码 | 高 |
| | test_pass_rate | 修复已知 bug 的能力 | 中 |
| **JSON Formatting** | valid_json_rate | 输出合法 JSON 的比例 | 高 |
| | schema_compliance | 遵循指定 schema | 高 |
| | self_correction | 在提示下修正错误 JSON 的能力 | 中 |
| **Chain of Thought** | reasoning_depth | 多步数学/逻辑推理 | 中 |
| | error_diagnosis | 诊断代码错误类型 | 中 |
| | debugging_skill | 修复隐蔽 bug（如重复元素检测） | 中 |
| **Code Review** | bug_detection | 发现代码中的问题（如除零） | 中 |
| | structured_output | 输出结构化审查 JSON | 中 |

### 评估方式

每个测试向 LLM 发送标准化 prompt，对返回结果进行**程序化判定**（非人工打分）：

```python
# 示例：代码生成测试
prompt = "Write a Python function fibonacci(n). Output ONLY the function."
# 判定逻辑：
# 1. AST 解析是否包含名为 fibonacci 的函数
# 2. 执行 fib(0), fib(1), fib(5) 是否得到 0, 1, 5
# 3. 两项全对 → score=1.0，仅语法正确 → score=0.5，完全错误 → score=0.0
```

### CLI 使用

```bash
# 运行完整能力评估（约 1-3 分钟）
pilotcode config --test capability

# 输出示例：
# ┌─────────────────┬────────┐
# │ Dimension       │ Score  │
# ├─────────────────┼────────┤
# │ Planning        │ 85.0%  │
# │ Task Completion │ 92.0%  │
# │ JSON Formatting │ 98.0%  │
# │ Chain of Thought│ 82.0%  │
# │ Code Review     │ 88.0%  │
# └─────────────────┴────────┘
# Overall Score: 89.0%
# Capability profile saved to ~/.pilotcode/model_capability.json
```

### 能力文件格式

```json
{
  "model_name": "deepseek-v4-pro",
  "evaluated_at": "2026-04-26T02:53:03Z",
  "overall_score": 0.89,
  "dimensions": {
    "planning": {
      "score": 0.85,
      "dag_correctness": 0.88,
      "task_granularity_appropriateness": 0.82,
      "dependency_accuracy": 0.85
    },
    "task_completion": { "score": 0.92, "code_correctness": 0.95, "test_pass_rate": 0.88 },
    "json_formatting": { "score": 0.98, "valid_json_rate": 0.99, "schema_compliance": 0.97, "self_correction": 0.98 },
    "chain_of_thought": { "score": 0.82, "reasoning_depth": 0.80, "error_diagnosis": 0.84, "debugging_skill": 0.82 },
    "code_review": { "score": 0.88, "bug_detection": 0.86, "structured_output": 0.90, "style_consistency": 0.88 }
  },
  "calibration": {
    "samples_evaluated": 0,
    "last_calibrated_at": null,
    "adjustments": [],
    "accumulated_deltas": {}
  }
}
```

---

## 第二层：自适应配置映射（Adaptive Config）

### 默认策略：强模型假设

**如果未找到能力配置文件，系统默认假设模型能力强**（overall_score = 0.88）：

```python
# 默认配置对应的能力水平
planning_score = 0.85       # 能一次性规划完整 DAG
task_completion = 0.90      # 代码生成正确率高
json_formatting = 0.92      # 几乎总是输出合法 JSON
chain_of_thought = 0.85     # 能做多步推理
code_review = 0.88          # 能输出结构化审查
```

这意味着：
- 新用户无需任何配置即可使用 PilotCode，获得最小框架干预的体验
- 只有在实际运行中发现模型能力不足时，系统才会收紧控制

### 配置映射规则

`AdaptiveConfigMapper.from_capability()` 根据评分动态生成配置：

#### 1. 规划策略（Planning Strategy）

| planning + cot 评分 | 策略 | 说明 |
|---|---|---|
| > 0.80 | `FULL_DAG` | 一次性输出完整 DAG |
| > 0.30 | `PHASED` | 分阶段规划，降低单次认知负担 |
| ≤ 0.30 | `TEMPLATE_BASED` | 使用预定义分解模板 |

#### 2. 任务粒度（Task Granularity）

| planning + completion 平均分 | 粒度 | max_lines | max_files |
|---|---|---|---|
| > 0.80 | `COARSE` | 300 | 4 |
| > 0.55 | `MEDIUM` | 150 | 2 |
| ≤ 0.55 | `FINE` | 80 | 1 |

#### 3. 验证器策略（Verifier Strategy）

| review + json 评分 | L3 验证器 | 说明 |
|---|---|---|
| > 0.80, > 0.60 | `FULL_L3` | 结构化 JSON 评分 + 详细反馈 |
| > 0.60 | `SIMPLIFIED_L3` | PASS/FAIL 字符串匹配 |
| ≤ 0.60 | `STATIC_ONLY` | ruff + mypy + 启发式规则，不调用 LLM |

**验证器降级示例**：

```python
# FULL_L3：模型输出 {"verdict": "APPROVE", "score": 85, "feedback": "..."}
if review_score > 0.80:
    l3_code_review_verifier  # 结构化 JSON

# SIMPLIFIED_L3：模型只需回答 "PASS" 或 "FAIL"
elif review_score > 0.60:
    simplified_l3_verifier   # 字符串匹配

# STATIC_ONLY：完全不用 LLM
else:
    static_analysis_l3_verifier  # ruff check + mypy + 行长度检查
```

#### 4. JSON 自修正

| json 评分 | 行为 |
|---|---|
| > 0.80 | 不要求修正（json_retry_on_failure = False） |
| 0.30-0.80 | 解析失败时最多重试 2 次 |
| < 0.30 | 解析失败时最多重试 3 次，并降低 temperature |

#### 5. 重试与重设计

| overall 评分 | max_rework | enable_redesign | stagnation_threshold |
|---|---|---|---|
| > 0.80 | 4 | True | 120s |
| > 0.55 | 2 | True | 60s |
| ≤ 0.55 | 1 | False | 30s |

---

## 第三层：运行时动态校准（Runtime Calibration）

### 核心机制

在 Mission 执行过程中，每个任务的成败被实时分析，调整对应维度的能力评分。

**调整公式**：
```
新评分 = 基准评分 + 累积调整值 (累积范围 [-0.25, +0.25])
```

### 失败分类与调整映射

```
任务失败
  ├── json_error          → json_formatting.valid_json_rate ↓
  ├── syntax_error        → task_completion.code_correctness ↓
  ├── logic_error         → task_completion.code_correctness ↓
  │                         + chain_of_thought.debugging_skill ↓
  ├── timeout             → chain_of_thought.reasoning_depth ↓
  └── planning_invalid    → planning.dag_correctness ↓
      /missing_fields      + json_formatting.schema_compliance ↓
      /invalid_dag         + planning.dependency_accuracy ↓
      /poor_granularity    + planning.task_granularity ↓
```

**调整幅度与完成度相关**：
```python
severity = 1.0 - completion_percentage  # 0.0 ~ 1.0
penalty = FAILURE_PENALTY_BASE * (0.5 + severity)
# completion=0% → penalty = -0.05 * 1.0 = -0.05
# completion=50% → penalty = -0.05 * 0.75 = -0.0375
```

### 成功强化

任务成功且正确率 ≥ 90% 时，小幅提升对应维度评分：
```python
SUCCESS_REWARD_BASE = +0.01  # 保守的正向强化
```

### 模型切换检测

系统在多处以防止能力错配：

**1. 配置保存时（ConfigManager.save_global_config）**
```python
if old_model != new_model:
    print("[Model Switch Detected] {old} -> {new}")
    print("Run 'pilotcode config --test capability' to evaluate.")
```

**2. CLI 设置模型时（config --set default_model）**
```bash
$ pilotcode config --set default_model llama-3-8b
Set default_model = llama-3-8b

[Model Switch Detected] deepseek-v4-pro -> llama-3-8b
Run capability benchmark for this model? [Y/n]:
```

**3. MissionAdapter 初始化时**
```python
cap = load_capability_or_default()
if cap.model_name != current_model:
    logger.warning(
        "Capability profile mismatch: stored='%s' vs current='%s'. "
        "Run 'pilotcode config --test capability' to regenerate.",
        cap.model_name, current_model
    )
```

---

## 完整自适应流程示例

### 场景：从云端强模型切换到本地弱模型

```
Step 1: 用户切换模型
─────────────────────
$ pilotcode config --set default_model qwen-1.8b
Set default_model = qwen-1.8b

[Model Switch Detected] deepseek-v4-pro -> qwen-1.8b
Run capability benchmark for this model? [Y/n]: Y

Step 2: 运行能力评估
─────────────────────
[1/13] test_planning_json_validity... done (score=0.40)
[2/13] test_planning_dependency_accuracy... done (score=0.25)
[3/13] test_code_generation_correctness... done (score=0.60)
...
Overall Score: 42.0%

Capability profile saved to ~/.pilotcode/model_capability.json

Step 3: 系统生成自适应配置
───────────────────────────
Planning Strategy:   TEMPLATE_BASED   (planning=0.35)
Task Granularity:    FINE             (max_lines=80, max_files=1)
Verifier Strategy:   STATIC_ONLY      (跳过 LLM 审查)
Max Rework:          1                (不耐心重试)
JSON Correction:     3 retries        (频繁格式错误)

Step 4: 执行第一个 Mission
───────────────────────────
用户: "实现用户登录功能"

MissionAdapter._plan_mission():
  - 使用模板化分解（非 LLM 创造性规划）
  - 任务粒度：每个任务只修改一个文件

Orchestrator.run():
  - L3 验证器：ruff + mypy（不调用 LLM）
  - Worker: 限制为 5 turns（防止弱模型无限循环）
  
任务 t1 失败（Worker 输出非法 JSON）
  → RuntimeCalibrator 记录:
    json_formatting.valid_json_rate: 0.50 -> 0.45 (-0.05)
  
任务 t2 成功
  → RuntimeCalibrator 记录:
    task_completion.code_correctness: 0.60 -> 0.61 (+0.01)

Step 5: 能力评分更新
─────────────────────
Runtime calibration updated:
  overall: 0.42 -> 0.39 (success_rate=33.3%)

如果继续恶化（success_rate < 50% 且 2+ 维度 <-0.15）：
  should_escalate_to_stronger_model() → True
  系统建议用户切换回更强的模型
```

---

## 第四层：弱模型多维代偿模式

当模型能力低于阈值（overall < 0.55 或单个维度 < 0.55）时，仅靠前述的"事前评估 + 事中适配 + 事后校准"三层机制仍不足以应对弱模型在**代码编辑**这一核心场景中的系统性缺陷。第四层引入**"框架代偿"**思想——由框架接管模型不擅长的全局分析、策略选择和错误检测，让弱模型只做它最擅长的事情：**原子化编辑**。

### 设计哲学

> **弱模型的根因不是"不会做"，而是"做不对细节"。**
> 
> - 上下文窗口小（73K vs 1M）→ 无法同时看到所有相关代码
> - 指令遵循差 → "修改所有引用"只改 2/5 处
> - 转义细节错误 → `\\n` 而不是 `\n`
> - 任务分解差 → 33+ 轮循环无法收敛

**代偿策略**：框架代劳全局分析和验证，弱模型只做原子化编辑。

### 架构总览

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Weak Model Compensation Layer                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │ Compensation    │───→│ EditValidator   │───│ ModelKnowhow    │          │
│  │ Engine          │    │                 │    │ Library         │          │
│  │                 │    │ • syntax check  │    │                 │          │
│  │ • prompt suffix │    │ • completeness  │    │ • scan rules    │          │
│  │ • failure track │    │ • knowhow scan  │    │ • auto-fix      │          │
│  └────────┬────────┘    └─────────────────┘    └─────────────────┘          │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │ SmartEditPlanner│    │ FileEditTool    │    │ FileWriteTool   │          │
│  │                 │    │                 │    │                 │          │
│  │ • pattern search│    │ • fuzzy match   │    │ • overwrite     │          │
│  │ • edit checklist│    │ • diag diff     │    │   warning       │          │
│  │ • scope filter  │    │ • syntax rollback│   │ • atomic write  │          │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘          │
│                                                                              │
│  MissionAdapter 集成点：                                                     │
│    • _build_worker_prompt()  → 注入 compensation suffix                      │
│    • _build_continue_prompt() → 运行 EditValidator + knowhow scan           │
│    • 连续 2 次 FileEdit 失败 → 提示"Use SmartEditPlanner"                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5 维度补偿策略映射

`AdaptiveConfigMapper` 在每个维度上生成对应的补偿字段：

| 维度 | 弱（<0.55）补偿 | 补偿字段 |
|------|---------------|---------|
| **planning** | TEMPLATE_BASED、FINE 粒度、≤50 行/任务、≤2 任务/阶段 | `max_tasks_per_phase=2` |
| **json_formatting** | 禁用 schema、3 次重试、优先纯文本输出 | `json_retry_on_failure=3` |
| **task_completion** | 原子编辑（1 次/轮）、自动验证、×1.5 轮次 | `max_edits_per_round=1`, `enable_auto_verify=True` |
| **chain_of_thought** | 每轮提醒目标、AskUser 确认关键决策、禁用自纠正 | `ask_user_on_critical_decisions=True` |
| **code_review** | 仅静态分析 L3、强制测试通过才标记完成 | `enforce_test_before_mark_complete=True` |

### CompensationEngine（补偿引擎）

根据 `AdaptiveOrchestratorConfig` 生成三类 prompt 后缀：

**1. Worker Prompt 后缀**（编辑前注入）
```
Make exactly ONE atomic edit per tool call. Do not batch multiple changes.
1. BEFORE editing: Call SmartEditPlanner to get a structured checklist.
After editing, verify the change: re-read the file to confirm correctness.
```

**2. Planning Prompt 后缀**（规划阶段注入）
```
IMPORTANT: You are operating with COMPENSATION MODE enabled.
Break this into SMALL, ATOMIC tasks. Each task should modify at most ONE file.
Use the TEMPLATE_BASED approach for task decomposition.
```

**3. Continue Prompt 后缀**（执行中注入）
当 `enable_auto_verify=True` 时，每次 continue 都会运行 `EditValidator`，并将验证结果注入 prompt：
```
[FRAMEWORK VERIFICATION]
⚠️ File src/example.py has syntax error: invalid syntax (line 42)
[HINT] Check for: double-escaped sequences (\\n → \n), mixed indentation, missing quotes.
```

### EditValidator（编辑验证器）

每次编辑后自动执行三级验证：

| 验证级别 | 检查内容 | 触发条件 |
|---------|---------|---------|
| **语法检查** | `py_compile.compile()` 解析 | 所有 `.py` 文件 |
| **完整性检查** | `expected_pattern` 是否仍存在（遗漏检测） | 提供 old_string 时 |
| **Knowhow 扫描** | 检测双转义换行、双转义 tab、混用缩进等 | 所有编辑文件 |

**验证结果注入 continue prompt**：
```python
validator = EditValidator()
result = validator.validate(changed_files=[path], expected_pattern=old_string)
if not result.passed:
    prompt += f"\n[FRAMEWORK VERIFICATION]\n{result.nudge_message}"
```

### SmartEditPlanner（智能编辑规划器）

弱模型缺乏全局视野，SmartEditPlanner 由**框架**代劳搜索和规划：

**输入**：`pattern` + `replacement_hint` + `scope`
**输出**：结构化检查清单

```python
SmartEditPlannerOutput(
    checklist=[
        EditChecklistItem(
            file_path="src/utils.py",
            line_number=42,
            context_before=["def old_func():", "    pass"],
            matched_line="    pass",
            context_after=["", "def another():"],
            suggested_edit="Replace 'pass' with 'return None'",
        )
    ],
    total_occurrences=3,
    truncated=True,  # 超过 max_results 时截断
)
```

**使用场景**：
- 修改函数签名后，需要更新所有调用点
- 重命名变量/类后，需要批量替换
- 弱模型自己搜索时容易遗漏或匹配错误位置

### ModelKnowhow（模型经验库）

将"已知弱模型缺陷"编码为可自动检测和修复的规则：

| 规则 ID | 检测模式 | 严重程度 | 自动修复 |
|---------|---------|---------|---------|
| `double_escaped_newline` | `\\n`（Python 源文件中的字面量 `\n`） | error | ✅ `\\n` → `\n` |
| `double_escaped_tab` | `\\t`（字面量 `\t`） | error | ✅ `\\t` → `\t` |
| `double_escaped_quote` | `\\"`（字面量 `"`） | error | ✅ `\\"` → `\"` |
| `mixed_indentation` | 同一文件混用 tab 和 space | warning | ❌ 仅提示 |
| `asyncio_run_in_async` | async 函数中调用 `asyncio.run()` | warning | ❌ 仅提示 |

**扫描与修复流程**：
```python
library = ModelKnowhowLibrary()
library.load_builtin_rules()

# 扫描文件
report = library.scan("src/example.py")
for issue in report.issues:
    print(f"[{issue.severity}] {issue.message} at line {issue.line}")

# 自动修复
fixed = library.auto_fix("src/example.py")
```

### 工具层增强

#### FileEditTool
- **精确匹配失败时**：显示 `[EXPECTED]` vs `[ACTUAL]` 对比片段
- **模糊匹配（≥0.75 相似度）**：替换后自动 `py_compile` 检查，语法错误则**回滚**
- **回滚后提示**："Pay attention to indentation. Re-read the file first."

#### FileWriteTool
- **大文件覆盖警告**：覆盖 >30 行文件时返回警告
  ```
  ⚠️ WARNING: Overwriting a large file (35+ lines).
  Prefer FileEdit for targeted changes to avoid unintended loss.
  ```
- **原子写入**：temp file + rename，避免写一半崩溃导致文件损坏

### 端到端效果验证

以 Qwen3-Coder-30B（73K 上下文）自我修改测试对比：

| 指标 | 无代偿模式 | 有代偿模式 | 改善 |
|------|----------|----------|------|
| 文件修改完成度 | 2/5 处 | 3/3 文件全部修改 | ✅ 100% |
| 工具策略 | FileEdit 失败后重写整个文件 | FileWrite 被阻止后改用精确 FileEdit | ✅ 更精准 |
| `\n` 转义错误 | 7 处 | 1 处 | ✅ -85% |
| 循环轮次 | 33+ | 12 | ✅ -64% |
| 总 Token 消耗 | ~45K | ~18K | ✅ -60% |

**关键洞察**：
- 代偿模式显著改善了**编辑策略**（用什么工具、怎么规划）
- 但无法完全解决**代码生成质量**（字符串转义细节）
- ModelKnowhow 正是为了补上这个缺口——在编辑后自动扫描并修复已知错误

### 局限性与边界

| 局限 | 说明 | 缓解措施 |
|------|------|---------|
| **无法提升代码生成准确性** | 代偿模式改善策略选择，但不改善模型本身生成代码的质量 | ModelKnowhow 事后检测 + 自动修复 |
| **FileEdit 模糊匹配陷阱** | 弱模型提供 `old_string` 不准确时，fuzzy match 可能匹配到错误位置 | 连续 2 次失败后提示"Use SmartEditPlanner" |
| **补偿开销** | 每次编辑后运行语法检查、knowhow 扫描，增加少量延迟 | 仅对 `.py` 文件运行，可配置关闭 |
| **过度干预风险** | 对中等能力模型（0.55-0.75）可能过于保守 | 按维度分级映射，中等能力仅启用部分补偿 |

### 配置启用

```bash
# 运行能力评估，自动生成代偿配置
pilotcode config --test capability

# 或手动在 ~/.pilotcode/config.yaml 中启用
orchestration:
  enable_compensation: true
  compensation:
    enable_auto_verify: true
    verify_after_each_edit: false
    max_edits_per_round: 1
    enable_smart_edit_planner: true
    ask_user_on_critical_decisions: true
    enforce_test_before_mark_complete: true
```

---

## 文件清单

| 文件 | 说明 |
|---|---|
| `src/pilotcode/model_capability/schema.py` | 能力评分数据模型 |
| `src/pilotcode/model_capability/benchmark.py` | 13 个基准测试 |
| `src/pilotcode/model_capability/evaluator.py` | 评分聚合引擎 |
| `src/pilotcode/model_capability/adaptive_config.py` | 能力→配置映射（含补偿字段） |
| `src/pilotcode/model_capability/runtime_calibrator.py` | 运行时校准器 |
| `src/pilotcode/orchestration/adaptive_edit.py` | **补偿引擎 + 编辑验证器** |
| `src/pilotcode/orchestration/verifiers/adaptive_verifiers.py` | 降级验证器实现 |
| `src/pilotcode/orchestration/adapter.py` | MissionAdapter 集成点（补偿注入） |
| `src/pilotcode/tools/smart_edit_planner.py` | **智能编辑规划器工具** |
| `src/pilotcode/tools/file_edit_tool.py` | 增强版 FileEdit（诊断对比 + 回滚） |
| `src/pilotcode/tools/file_write_tool.py` | 增强版 FileWrite（覆盖警告 + 原子写入） |
| `src/pilotcode/services/knowhow.py` | **模型经验库（已知缺陷检测/修复）** |
| `src/pilotcode/utils/config.py` | 模型切换检测 |
| `src/pilotcode/cli.py` | `config --test capability` CLI |
| `~/.pilotcode/model_capability.json` | 用户能力配置文件 |
