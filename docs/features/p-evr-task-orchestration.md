# P-EVR 任务编排：Plan-Execute-Verify-Reflect

> **核心思想**：不是让模型一次性写好，而是让它像一个资深工程师一样工作——理解需求、拆解任务、写代码、自测、Code Review、返工，直到满足质量标准。

---

## 一、为什么需要 P-EVR

传统 AI 编码助手（包括早期 PilotCode）的工作模式是"单轮对话"：用户说需求 → LLM 生成代码 → 结束。这种模式有两个致命问题：

1. **没有验证**：LLM 生成的代码可能有语法错误、逻辑漏洞，但没有任何检查机制
2. **不会返工**：发现问题后，LLM 不会自动修正，需要用户手动指出

P-EVR（Plan-Execute-Verify-Reflect）通过引入**显式验证层和结构化返工机制**，把不确定性关在笼子里——用状态机限制执行路径，用 TaskSpec 约束 Worker 行为，用三级验证尽早发现问题，用 ReworkContext 保留返工上下文。

---

## 二、整体架构

```
┌────────────────────────────────────────────────────┐
│                  Orchestrator                        │
│             (状态机驱动，维护全局上下文)                │
└──────────┬────────────────────────────┬────────────┘
           │                            │
    ┌──────▼──────┐              ┌──────▼──────┐
    │   Planner   │              │  Tracker    │
    │   任务分解   │              │   状态追踪   │
    └──────┬──────┘              └──────┬──────┘
           │                            │
┌──────────▼──────────┐      ┌──────────▼──────────┐
│   Task Executor     │      │   Memory Manager    │
│  (Worker智能体池)    │      │  (上下文+产物管理)   │
└──────────┬──────────┘      └─────────────────────┘
           │
    ┌──────▼──────┐
    │  Verifier   │    ← 三级验证体系
    │   验证层    │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  Reflector  │
    │   反思层    │
    └─────────────┘
```

---

## 三、Plan 层：从模糊需求到可执行 DAG

### 3.1 三层分解模型

不是简单拆成"步骤1、步骤2"，而是建立 **Mission → Phase → Task** 三层结构：

```
Mission: "实现一个支持OAuth2.0的REST API用户模块"
    ├── Phase 1: 基础设施 [无依赖]
    │   ├── Task 1.1: 数据库schema设计
    │   ├── Task 1.2: 配置加载模块
    │   └── Task 1.3: 日志与错误处理中间件
    ├── Phase 2: 核心领域 [依赖: Phase 1]
    │   ├── Task 2.1: User实体与Repository模式
    │   ├── Task 2.2: 密码哈希与验证服务
    │   └── Task 2.3: JWT生成与验证服务
    ├── Phase 3: API层 [依赖: Phase 2]
    │   ├── Task 3.1: /register 端点
    │   ├── Task 3.2: /login 端点
    │   ├── Task 3.3: /refresh 端点
    │   └── Task 3.4: /me 端点
    └── Phase 4: 集成与验证 [依赖: Phase 3]
        ├── Task 4.1: 端到端测试
        ├── Task 4.2: 安全审计
        └── Task 4.3: API文档生成
```

**实现文件**：`src/pilotcode/orchestration/adapter.py` — `MissionAdapter._plan_mission()`

Planner 使用 LLM 将用户请求分解为结构化 JSON Plan，框架负责解析和验证：

```python
system_prompt = (
    "You are a mission planner for a software development AI system.\n"
    "Given a user's request, decompose it into a structured plan ...\n"
    "Output ONLY a JSON object with no markdown formatting."
)
```

框架通过 `_extract_json()` 做容错解析（处理 markdown code block、缺失字段），确保即使 LLM 输出格式不规范也能得到可执行的计划。

### 3.2 任务描述规范 (TaskSpec)

每个任务必须包含以下字段，这是防止执行迷失的第一道防线：

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 全局唯一ID | `"task_2_1"` |
| `title` | 一句话描述 | `"User实体与Repository模式"` |
| `objective` | 完成后要达到的精确状态 | `"实现User dataclass和UserRepository接口"` |
| `inputs` | 需要的输入 | `["src/models/base.py"]` |
| `outputs` | 必须产出的产物 | `["src/models/user.py", "src/repositories/user_repo.py"]` |
| `dependencies` | 前置任务ID | `["task_1_1"]` |
| `estimated_complexity` | 复杂度 1-5 | `3` |
| `acceptance_criteria` | 明确的验收条件 | `["单元测试覆盖率>80%"]` |
| `constraints` | 执行约束 | `max_lines: 200`, `must_use: ["pydantic"]` |
| `context_budget` | 允许使用的token上限 | `16000` |

**实现文件**：`src/pilotcode/orchestration/task_spec.py`

### 3.3 依赖图与拓扑执行

计划不是线性列表，而是 **有向无环图 (DAG)**：

```
1.1 schema设计 ──┐
1.2 配置加载 ────┼──→ 2.1 User实体 ──→ 3.1 /register ──┐
1.3 日志中间件 ──┘          │                    ├─→ 4.1 端到端测试
                            ↓                    │
                         2.2 密码服务 ──→ 3.2 /login ──┤
                            │                    │      │
                            ↓                    │      ├→ 4.2 安全审计
                         2.3 JWT服务 ───→ 3.3 /refresh─┤
                                                   ├─→ 4.3 API文档
                                                3.4 /me ─┘
```

**执行规则**：只有所有依赖节点为 `VERIFIED` 状态，才能开始执行。

**实现文件**：`src/pilotcode/orchestration/dag.py` — `DagExecutor`

使用 Kahn 算法进行拓扑排序，自动检测循环依赖并报告。计算每个节点的拓扑深度，为并行执行 wave 调度提供基础。

---

## 四、Execute 层：状态机驱动的执行

### 4.1 执行状态机

每个任务在执行中经历严格状态流转：

```
PENDING → ASSIGNED → IN_PROGRESS → SUBMITTED → UNDER_REVIEW
                                              ↓
                              ┌───────────────┴───────────────┐
                              ↓                               ↓
                          VERIFIED                        REJECTED
                              │                               │
                              │        ┌──────────────────────┘
                              │        ↓
                              │    NEEDS_REWORK (保留上下文)
                              │        │
                              │        ↓ (回到 IN_PROGRESS)
                              └────→ DONE
```

**实现文件**：`src/pilotcode/orchestration/state_machine.py`

### 4.2 LLM Worker 与执行循环

每个 Task 由一个独立的 QueryEngine 实例执行，配备完整的工具集：

```python
async def _llm_worker(self, task: TaskSpec, context: dict) -> ExecutionResult:
    # 根据复杂度决定 turn 限制
    max_turns = DEFAULT_TURN_LIMITS[task.estimated_complexity]  # 5~50

    engine = QueryEngine(config)  # 独立实例，隔离上下文

    while total_turns < max_turns:
        # 提交给 LLM
        async for result in engine.submit_message(prompt):
            ...

        # 执行工具并反馈结果
        for tool in pending_tools:
            exec_result = await executor.execute_tool_by_name(...)
            engine.add_tool_result(tool.tool_use_id, result_text)

        total_turns += 1
```

**实现文件**：`src/pilotcode/orchestration/adapter.py` — `_llm_worker()`

**关键设计**：
- **Worker 是无状态的**，所有状态由 Orchestrator 维护
- **复杂度感知的 turn 限制**：简单任务 5 轮，复杂任务 50 轮
- **工具执行结果实时反馈**：LLM 能立即看到 FileRead/Grep/Bash 的结果并调整策略

### 4.3 上下文防漂移机制

**问题**：长任务执行中，模型容易忘记原始目标，开始"自由发挥"。

**解决方案**：

1. **目标锚定**：每次工具调用前，prompt 中强制重复当前 Task 的 objective
2. **执行轨迹日志**：维护只增不减的操作日志（FileRead → FileEdit → Bash）
3. **定期对齐检查**：每轮结束后检查是否偏离目标

**实现文件**：`src/pilotcode/query_engine.py` — system prompt 中的 `MULTI-STEP WORKFLOW` 和 `CRITICAL INSTRUCTIONS`

---

## 五、Verify 层：每个任务都有 Review 和测试

### 5.1 三级验证体系

```
Level 1: 自动化检查 (自动，零成本)
    ├── 静态分析：行数限制、模式匹配、must_use/must_not_use
    ├── 安全扫描：检测禁止模式
    └── 复杂度检查：单文件行数限制

Level 2: 单元/集成测试 (自动，低成本)
    ├── 自动发现 pytest 测试文件并运行
    ├── 边界测试覆盖
    └── 集成测试：模块间交互验证

Level 3: Code Review (LLM)
    ├── 设计合规性：是否符合 task spec 中的约束
    ├── 逻辑正确性：是否满足 acceptance criteria
    └── 可维护性：命名、注释、复杂度
```

**实现文件**：
- `src/pilotcode/orchestration/verifier/level1_static.py`
- `src/pilotcode/orchestration/verifier/level2_tests.py`
- `src/pilotcode/orchestration/verifier/level3_review.py`

### 5.2 验证执行流程

```
Worker提交产物
    │
    ▼
┌──────────────┐
│ Level 1 检查  │ ← 全自动化，失败直接退回
│ (30秒内完成) │
└──────┬───────┘
       │ PASS
       ▼
┌──────────────┐
│ Level 2 测试  │ ← 自动运行测试套件
│ (2分钟内完成) │
└──────┬───────┘
       │ PASS
       ▼
┌──────────────┐
│ Level 3 Review│ ← LLM Reviewer角色
│ (深度检查)   │
└──────┬───────┘
       │
   ┌───┴───┐
   │       │
 APPROVE  REJECT
   │       │
   ▼       ▼
VERIFIED  NEEDS_REWORK
```

---

## 六、返工与重设计机制

### 6.1 问题分级与响应策略

| 级别 | 触发条件 | 响应策略 |
|------|---------|---------|
| **Minor** | 命名不规范、缺少注释、格式问题 | 自动修复或由 Worker 立即修改，不调整计划 |
| **Major** | 逻辑错误、边界处理缺失、测试失败 | Worker 返工，保留已完成上下文，重新执行 |
| **Critical** | 架构设计缺陷、需求理解偏差 | 触发 Redesign，回到 Planner 重新分解 |
| **Blocked** | 外部依赖不可用、环境配置问题 | 挂起任务，通知 Orchestrator 调整 DAG |

### 6.2 返工上下文保留

**关键设计**：返工不是"从头再来"，而是增量修正。

```python
ReworkContext:
  original_task: TaskSpec
  failed_attempt:
    code: str
    test_results: TestReport
    review_feedback: str
  preserve: ["保留JWT生成逻辑，只改verify"]       # 明确告诉Worker哪些保留
  must_change: ["必须添加过期时间验证"]           # 明确告诉Worker哪些必须改
  lessons_learned: "上次失败原因：没处理exp字段"  # 避免重复犯错
```

**实现文件**：`src/pilotcode/orchestration/orchestrator.py` — `max_rework_attempts=3`

---

## 七、与 LLM 规划能力的互补

### 7.1 分工边界

| 能力 | PilotCode 框架 | LLM |
|-----|---------------|-----|
| **任务分解** | 提供 JSON schema + 启发式规则 | 理解意图，将模糊需求拆成具体任务 |
| **依赖推理** | DAG 构建、拓扑排序、cycle 检测 | 在 system prompt 引导下声明依赖 |
| **执行调度** | 并行 wave 计算、并发控制、turn 限制 | 不擅长精确的状态管理 |
| **执行实现** | 提供工具集、cwd 同步、XML fallback | 决定读什么、改什么、调用什么工具 |
| **质量保证** | L1 静态规则 + L2 自动化测试 | L3 代码审查（设计合理性、边界处理） |
| **容错恢复** | 状态机、重做计数、回滚机制 | 从失败反馈中重新规划 |

### 7.2 不同 LLM 的最优使用策略

基于 E2E 测试（44 个测试用例，覆盖代码生成、工具调用、上下文保持、代码编辑、任务规划）的验证结果：

| LLM 类型 | 能力特征 | P-EVR 适配策略 |
|---------|---------|---------------|
| **强规划 + 强执行**<br>(如 Claude 3.5 Sonnet) | 工具调用规范、上下文保持好、编辑积极 | P-EVR 轻量模式：Plan 由 LLM 主导，框架只做 L1/L2 验证和 DAG 调度 |
| **强规划 + 弱执行**<br>(如 Qwen3-30B) | 裸代码生成强，但工具格式错误、编辑回避 | P-EVR 重引导模式：system prompt 强化工具使用规则，框架增强 XML fallback |
| **推理模型**<br>(如 Qwen3.6-35B) | 推理能力强但输出 thinking 内容、速度慢 | P-EVR 过滤模式：thinking 剥离 + 更长的 turn 限制容忍慢速推理 |

**E2E 测试验证结果对比**：

| 维度 | Qwen3-30B (旧) | Qwen3.6-35B (新) | 框架补偿效果 |
|-----|---------------|-----------------|------------|
| Layer 2 工具调用 | 83.9% | **96.8%** | system prompt 优化 + XML fallback |
| 上下文保持 | 0/3 | **3/3** | 框架隔离每个 Task 的 QueryEngine 实例 |
| 代码编辑 | 0/3 | **4/4** | "ACT, DON'T JUST TALK" 指令强化 |
| 跨文件重构 | 未测试 | **1/1** | cwd 同步 + DAG 依赖调度 |

### 7.3 核心洞察

> **P-EVR 不是替代 LLM 做计划，而是给 LLM 的计划能力提供一个"安全执行容器"。**

| 没有 P-EVR | 有 P-EVR |
|-----------|---------|
| LLM 输出 plan，但格式不规范导致无法解析 | `_extract_json()` + DAG 验证确保 plan 可执行 |
| LLM 执行时忘记之前做了什么，重复读取文件 | 框架维护 `read_file_state` 和对话历史 |
| LLM 编辑后不做验证，留下语法错误 | L1/L2/L3 分层验证，失败自动重做 |
| LLM 在多文件修改中遗漏某个文件 | DAG 依赖检查 + checklist 提醒 |
| LLM 陷入无限循环（反复尝试错误的 edit） | `max_turns` 限制 + `max_rework_attempts` 限制 |

---

## 八、实现状态与路线图

### 8.1 已实现组件 ✅

| 组件 | 文件 | 状态 |
|------|------|------|
| **MissionAdapter** | `orchestration/adapter.py` | ✅ 完整实现，支持 LLM Plan + Worker 执行 |
| **TaskSpec / Mission** | `orchestration/task_spec.py` | ✅ 完整实现，含 Constraints、AcceptanceCriterion |
| **DAG 引擎** | `orchestration/dag.py` | ✅ Kahn 拓扑排序 + cycle 检测 + 并行 wave |
| **状态机** | `orchestration/state_machine.py` | ✅ 完整状态流转定义 |
| **Orchestrator** | `orchestration/orchestrator.py` | ✅ 核心调度循环 |
| **Tracker** | `orchestration/tracker.py` | ✅ SQLite 持久化 + 事件订阅 |
| **Decomposer** | `orchestration/decomposer.py` | ✅ 启发式复杂度检测 + 策略选择 |
| **L1 验证器** | `orchestration/verifier/level1_static.py` | ✅ 静态分析（行数、模式匹配） |
| **L2 验证器** | `orchestration/verifier/level2_tests.py` | ✅ pytest 自动运行 |
| **L3 验证器** | `orchestration/verifier/level3_review.py` | ⚠️ 启发式框架，预留 LLM 接口 |
| **System Prompt** | `query_engine.py` | ✅ MULTI-STEP WORKFLOW + Tool Selection Cheat Sheet |

### 8.2 待实现/优化

| 组件 | 状态 | 说明 |
|------|------|------|
| **Worker 分级** | 🔄 待完善 | Simple/Standard/Complex/Debug Worker 按复杂度匹配 |
| **三层记忆** | 🔄 待完善 | L3 Project Memory 跨 Session 持久化 |
| **产物版本控制** | 🔄 待完善 | v1/v2/FINAL 目录结构 |
| **Redesign 流程** | 🔄 待完善 | Critical 问题时的根因分析 + 重新规划 |
| **L3 LLM Review** | 🔄 待接入 | 接入真实 LLM 做代码审查（当前为启发式） |
| **并行验证** | 🔄 待优化 | L1 和 L2 可并行运行 |

### 8.3 路线图

```
MVP (已交付): 线性执行 + Level 1验证 + 基础返工
    ↓
v1.1 (当前): DAG执行 + Level 2测试 + MissionAdapter集成
    ↓
v1.2 (计划): Redesign机制 + 三层记忆 + 执行轨迹
    ↓
v2.0 (远期): 多Worker并行 + 自优化 + 项目模板学习
```

---

## 九、使用示例

### 9.1 简单任务（自动跳过 Plan）

```python
from pilotcode.orchestration.adapter import MissionAdapter

adapter = MissionAdapter()
result = await adapter.run("Fix the typo in README.md")
# 复杂度=1，auto_approve_simple=True，直接 Execute，无需 Plan
```

### 9.2 复杂任务（完整 P-EVR 循环）

```python
result = await adapter.run(
    "Implement OAuth2 login with JWT refresh tokens"
)
# 1. Plan: LLM 分解为 4 个 Phase、12 个 Task
# 2. DAG: 框架构建依赖图，识别并行 wave
# 3. Execute: 按 wave 调度 Worker，每 Task 独立 QueryEngine
# 4. Verify: L1 行数检查 → L2 pytest → L3 代码审查
# 5. Reflect: Task 7 失败 → 保留上下文 → 增量修正 → 重试
```

### 9.3 查看执行报告

```python
from pilotcode.orchestration.report import ExecutionReport

report = ExecutionReport.from_mission(result.mission)
print(report.summary())
# 输出：Mission 完成度、各 Task 状态、返工次数、总耗时
```

---

## 十一、上下文自适应策略（Context Strategy）

P-EVR 框架可以根据后端 LLM 的**上下文窗口大小**动态调整策略，实现框架与 LLM 的最优分工。

### 11.1 三种策略模式

| 策略 | 上下文范围 | 框架角色 | LLM 角色 | 关键参数 |
|-----|-----------|---------|---------|---------|
| **FRAMEWORK_HEAVY** | ≤12K tokens | **主导**：强制细粒度分解、严格约束、自动 Worker 选择 | 仅执行叶子任务 | max_files=2, max_lines=150, max_turns×1.0 |
| **BALANCED** | 12K-48K tokens | **协作**：中等粒度分解、L3 Review 启用 | 子任务内自主规划 | max_files=4, max_lines=300, max_turns×1.2 |
| **LLM_HEAVY** | >48K tokens | **安全网**：验证层 + 失败兜底 | **主导**：自主 Plan + Execute | max_files=8, max_lines=500, max_turns×1.5 |

### 11.2 策略自动切换

```python
from pilotcode.orchestration.adapter import MissionAdapter

# 8K 上下文：框架主导分解
adapter = MissionAdapter(context_budget=8192)
# -> strategy=FRAMEWORK_HEAVY
#    - 每个任务最多 2 个文件
#    - 复杂度强制封顶 MODERATE
#    - 每任务预算 6K tokens

# 64K 上下文：LLM 主导
adapter = MissionAdapter(context_budget=65536)
# -> strategy=LLM_HEAVY
#    - 每个任务最多 8 个文件
#    - 复杂度不限
#    - 每任务预算 56K tokens
```

### 11.3 实验验证结果

基于 13 个真实编程任务的模拟实验（10 次运行平均）：

| 上下文 | 策略 | 成功率 | 返工次数 | Token/任务 | 执行时间 |
|-------|------|--------|---------|-----------|---------|
| 8K | FRAMEWORK_HEAVY | **100%** | **2** | **4,254** | **4,669s** |
| 16K | BALANCED | 92.3% | 7 | 6,658 | 5,638s |
| 32K | BALANCED | 92.3% | 5 | 6,263 | 5,310s |
| 64K | LLM_HEAVY | 84.6% | 16 | 11,572 | 6,447s |
| 128K | LLM_HEAVY | 92.3% | 13 | 11,260 | 6,208s |

**核心发现**：
1. **短上下文场景**：FRAMEWORK_HEAVY 的强制分解将复杂任务降至 LLM 可处理范围，成功率最高（100%），返工最少
2. **长上下文场景**：LLM_HEAVY 成功率接近 FRAMEWORK_HEAVY，但 token 消耗高 2.6x，返工多 6.5x
3. **策略切换点**：12K 和 48K 是两个关键阈值，分别对应从"框架主导"到"混合"、再到"LLM 主导"的过渡

> **结论**：P-EVR 的 Context Strategy 不是简单的"短上下文用框架，长上下文不用"，而是**在所有上下文长度下，框架的验证层（L1/L2）都提供不可替代的价值**。差异只在 Plan 和 Execute 层的粒度控制。

### 11.4 实现文件

- **`src/pilotcode/orchestration/context_strategy.py`** — 策略框架核心
- **`src/pilotcode/orchestration/adapter.py`** — MissionAdapter 集成策略选择
- **`tests/orchestration/test_context_strategy.py`** — 30 个单元测试
- **`tests/orchestration/experiment_context_strategy.py`** — 模拟实验脚本

---

## 十二、参考

- **P-EVR 架构设计文档**: `~/tmp/P-EVR-Architecture.md` — 原始设计蓝图
- **重构分析报告**: `../P-EVR-重构分析.md` — 与现有代码基线的差距分析（面向开发者）
- **E2E 测试框架**: `tests/e2e/model_capability/` — LLM 能力评估与框架修复验证
- **Context Strategy 实验**: `tests/orchestration/experiment_results.json` — 模拟实验数据

### 与业界方案的关键差异

| 方案 | 关键特点 | 与 PilotCode P-EVR 的差异 |
|------|---------|------------------------|
| **MetaGPT** (2023) | 多智能体协作，SOP 驱动 | P-EVR 有显式验证层和结构化返工 |
| **SWE-agent** (2024) | 编辑-执行循环，针对软件工程 | P-EVR 有 DAG 拓扑执行和三级验证 |
| **Devin** (2024) | 端到端 AI 工程师（闭源） | P-EVR 开源，可插拔不同 LLM |
| **OpenHands** (2024) | 模块化 Agent 框架 | P-EVR 强调框架与 LLM 的互补而非替代 |

> *"计划不是用来严格执行的，是用来在迷失时找回方向的。"*
>
> P-EVR 的核心是把不确定性关在笼子里——用状态机限制执行路径，用 TaskSpec 约束 Worker 行为，用三级验证尽早发现问题，用 ReworkContext 保留返工上下文。
