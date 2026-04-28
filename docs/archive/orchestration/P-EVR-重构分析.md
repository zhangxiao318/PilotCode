# PilotCode 任务编排重构分析：P-EVR 架构落地方案

> 基于 `P-EVR-Architecture.md` 与现有代码基线的差距分析

---

## 一、现有代码基线盘点

### 1.1 任务编排相关代码规模

| 模块 | 文件 | 行数 | 现状描述 |
|------|------|------|----------|
| Agent Orchestrator | `agent/agent_orchestrator.py` | 630 | 有 WorkflowStep/WorkflowResult，支持 sequential/parallel/supervisor/debate/pipeline 5种模式，依赖检查只有简单的 `depends_on` 字符串列表比对 |
| Agent Manager | `agent/agent_manager.py` | 479 | 管理 SubAgent 生命周期，定义7种内置 agent 类型（coder/debugger/explainer/tester/reviewer/planner/explorer），无复杂度分级 |
| Tool Orchestrator | `services/tool_orchestrator.py` | 281 | 按 read-only/write 分组工具调用，支持并行/顺序执行，无 DAG 拓扑排序 |
| Plan Mode | `tools/plan_mode_tools.py` + `commands/plan_cmd.py` | 289 | 全局 `_plan_state` 管理，只有简单的步骤列表（`list[str]`），无依赖关系 |
| Task Queue | `services/task_queue.py` + `tools/task_tools.py` | 726 | 后台异步任务系统，支持创建/停止/获取输出，与主编排流程是独立的两套系统 |
| Team Manager | `services/team_manager.py` + `tools/team_tools.py` | 601 | ClaudeCode 风格的团队管理，支持角色分配、消息传递、共享上下文，但无状态机 |
| Agent Hooks | `agent/agent_hooks.py` | 354 | 生命周期钩子系统，pre/post agent run, pre/post tool use 等 |
| Agent Tool | `tools/agent_tool.py` | 149 | LLM 可调用的 Agent 工具，spawn sub-agent 执行 |
| CLI 命令 | `commands/agents_cmd.py` + `workflow_cmd.py` | 464 | `/agents`, `/workflow` 命令 |
| **总计** | | **~3,973** | 代码量不小，但功能分散，没有统一的状态机和 DAG 执行引擎 |

### 1.2 现有能力映射到 P-EVR

```
P-EVR 组件          现有对应代码                差距
─────────────────────────────────────────────────────────────────
Orchestrator        AgentOrchestrator           ❌ 无全局状态机
Planner             PlanModeState               ❌ 只有线性步骤列表，无 DAG
Task Executor       AgentTool + TaskTools       ⚠️ 两套并行系统，未统一
Tracker             TeamManager                 ⚠️ 有进度但无状态流转
Memory Manager      app_state + read_file_state ❌ 无分层记忆
Verifier            无                          ❌ 完全没有
Reflector           无                          ❌ 完全没有
```

**核心结论**：现有代码有"零件"但没有"总成"。AgentOrchestrator、TeamManager、TaskQueue、PlanMode 四者是**独立运转的四个子系统**，没有统一的 Orchestrator 把它们串联起来。

---

## 二、P-EVR 与现有代码的关键差距

### 2.1 Plan 层差距：从线性列表到 DAG

**现有**：
```python
# plan_mode_tools.py
_plan_state.current_plan = [
    {"step": i+1, "description": step, "status": "pending"}
    for i, step in enumerate(input_data.steps)
]
```
只是一个字符串列表，没有依赖关系。

**P-EVR 要求**：
- 三层分解（Mission → Phase → Task）
- TaskSpec 规范（objective、inputs、outputs、dependencies、acceptance_criteria、constraints、context_budget）
- DAG 拓扑执行（只有依赖节点为 `VERIFIED` 才能开始）

### 2.2 Execute 层差距：从"跑完拉倒"到状态机驱动

**现有 AgentOrchestrator.run_sequential()**：
```python
for i, step in enumerate(steps):
    agent = self.agent_manager.create_agent(agent_type=step.agent_type)
    result = await self._run_agent_task(agent, prompt)
    results[step.output_key] = result
```
只有"创建 → 运行 → 保存结果"三步，没有状态流转。

**P-EVR 要求的状态机**：
```
PENDING → ASSIGNED → IN_PROGRESS → SUBMITTED → UNDER_REVIEW
                                              ↓
                                      VERIFIED / REJECTED
                                         ↓        ↓
                                        DONE  NEEDS_REWORK → IN_PROGRESS
```

### 2.3 Verify 层差距：完全缺失

现有代码**没有任何结构化验证机制**。工具执行成功就标记完成，没有：
- Level 1: 静态分析（lint、类型检查、复杂度）
- Level 2: 单元/集成测试自动运行
- Level 3: LLM Code Review（Reviewer 角色）

### 2.4 返工机制差距：完全缺失

现有代码没有返工概念。Agent 执行失败只有一种结果：报错。没有：
- Minor/Major/Critical/Blocked 分级
- ReworkContext（保留已完成上下文）
- Redesign 流程（根因分析 → 重新规划）

### 2.5 Memory 层差距：无分层记忆

现有：
- `AppState`：单个 dataclass，保存 cwd、model 配置等
- `read_file_state`：字典，记录文件读取时间戳
- `context.read_file_state`：ToolUseContext 上的文件冲突检测

P-EVR 要求三层记忆：
- Layer 3: Project Memory（技术栈决策、架构模式，跨 Session）
- Layer 2: Session Memory（当前 Mission 的完整 DAG 状态）
- Layer 1: Working Memory（当前 Task 的代码上下文 + 最近5步轨迹）

---

## 三、实现方案（分阶段）

### 阶段一：核心骨架（~2 周，新增 ~1,500 行）

**目标**：建立统一 Orchestrator + DAG 执行引擎 + TaskSpec 规范

```
src/pilotcode/orchestration/
├── __init__.py
├── orchestrator.py          # 统一 Orchestrator（状态机驱动）
├── dag.py                   # DAG 构建与拓扑排序
├── task_spec.py             # TaskSpec dataclass
├── state_machine.py         # 任务状态机定义与流转规则
├── tracker.py               # 全局任务追踪（Tracker）
└── context/                 # 上下文管理层
    ├── __init__.py
    ├── project_memory.py    # Layer 3: 项目级记忆
    ├── session_memory.py    # Layer 2: 会话级记忆
    └── working_memory.py    # Layer 1: 工作级记忆
```

**关键设计决策**：

1. **Orchestrator 作为 Singleton**，取代现有分散的 AgentOrchestrator/TeamManager/TaskQueue
2. **TaskSpec 使用 Pydantic 模型**，方便 LLM 输出结构化 JSON 后自动解析
3. **DAG 用 networkx 或自研**，拓扑排序后按批次调度执行
4. **状态机用枚举 + 状态转换表**，避免散落在 if/else 中

### 阶段二：验证层（~1 周，新增 ~800 行）

```
src/pilotcode/orchestration/
├── verifier/
│   ├── __init__.py
│   ├── level1_static.py     # 静态分析（lint、类型检查、复杂度）
│   ├── level2_tests.py      # 测试自动运行
│   ├── level3_review.py     # LLM Code Review
│   └── verdict.py           # Verdict 枚举与判定逻辑
```

### 阶段三：返工与反思（~1 周，新增 ~600 行）

```
src/pilotcode/orchestration/
├── rework/
│   ├── __init__.py
│   ├── rework_context.py    # ReworkContext 数据结构
│   ├── redesigner.py        # Redesign 流程
│   └── reflector.py         # 定期复盘检查
```

### 阶段四：Worker 分级与优化（~1 周，新增 ~500 行）

```
src/pilotcode/orchestration/
├── workers/
│   ├── __init__.py
│   ├── simple_worker.py     # 单文件修改 (<50行)
│   ├── standard_worker.py   # 模块开发
│   ├── complex_worker.py    # 架构设计
│   └── debug_worker.py      # Bug 修复/返工
```

### 总估算

| 阶段 | 新增代码 | 修改现有代码 |
|------|----------|-------------|
| 一：核心骨架 | ~1,500 行 | ~500 行（AgentOrchestrator、PlanMode 接入） |
| 二：验证层 | ~800 行 | ~200 行（ToolExecutor 后接 Verifier） |
| 三：返工反思 | ~600 行 | ~100 行 |
| 四：Worker 分级 | ~500 行 | ~300 行（AgentManager 接入） |
| **总计** | **~3,400 行** | **~1,100 行** |

**关键原则**：
- 新代码在 `orchestration/` 包中，不与现有代码耦合
- 现有 AgentOrchestrator/TeamManager/TaskQueue **渐进式迁移**，不是一次性替换
- 通过 `Orchestrator.register_legacy_adapter()` 方式兼容现有工具调用

---

## 四、用户问题的详细回答

### 4.1 "各 Agent 共享的基础模块" — 必要且优先

**结论：必须做，这是 P-EVR 的 Orchestrator 核心。**

现有问题：
- AgentOrchestrator 管理 "workflow steps"
- TeamManager 管理 "team agents"
- TaskQueue 管理 "background tasks"
- PlanMode 管理 "plan steps"

四个系统互不通信，一个 Agent 无法知道另一个 Agent 在干什么。

**设计建议**：

```python
# orchestration/tracker.py
class MissionTracker:
    """全局任务追踪中心，所有 Agent/Worker/Orchestrator 共享。"""

    def __init__(self):
        self.missions: dict[str, Mission] = {}      # mission_id → Mission
        self.agents: dict[str, AgentStatus] = {}    # agent_id → 状态快照
        self.dag_states: dict[str, DagState] = {}   # mission_id → DAG 执行状态

    def get_agent_progress(self, agent_id: str) -> AgentProgress:
        """查询任意 Agent 的当前进度。"""

    def get_ready_tasks(self, mission_id: str) -> list[TaskSpec]:
        """获取 DAG 中所有依赖已满足、可以执行的任务。"""

    def get_blocked_tasks(self, mission_id: str) -> list[BlockedTask]:
        """获取被阻塞的任务及阻塞原因。"""

    def subscribe(self, callback: Callable[[Event], None]):
        """订阅状态变更事件（用于 Web UI 实时刷新）。"""
```

这个 Tracker 应该：
1. **驻留在主进程**，不随 Agent 生命周期销毁
2. **提供 WebSocket 推送**，让 Web UI 能实时看"当前哪个 Agent 在跑什么任务"
3. **持久化到 SQLite**，会话中断后可以恢复

### 4.2 "能否用强化学习评估不同修改尝试的效果" — 可行，但分两步走

**短期（不加 RL，先用规则/启发式）**：

P-EVR 文档中的关键指标已经可以作为评估框架：

```python
class AttemptEvaluator:
    """评估一次修改尝试（返工循环）的效果。"""

    def evaluate(self, attempt: ReworkAttempt) -> AttemptScore:
        return AttemptScore(
            # 直接指标
            passed_level1=attempt.verdict.level1_passed,
            passed_level2=attempt.verdict.level2_passed,
            passed_level3=attempt.verdict.level3_passed,
            rework_count=attempt.rework_count,

            # 质量指标
            code_complexity=self._calc_complexity(attempt.code),
            test_coverage=self._calc_coverage(attempt.tests),
            diff_size=len(attempt.diff_lines),

            # 效率指标
            token_usage=attempt.token_usage,
            time_spent=attempt.time_spent,
        )
```

每次返工循环结束后，记录 `AttemptScore`，形成数据集。

**长期（引入轻量级 RL）**：

可以用 **Bandit 算法**（如 Thompson Sampling）而不是完整 RL：

```python
class StrategyBandit:
    """多臂老虎机：选择最优 Worker/验证策略。"""

    strategies = [
        "simple_worker",      # 简单 Worker
        "standard_worker",    # 标准 Worker
        "complex_worker",     # 复杂 Worker
        "with_l3_review",     # 带 L3 Review
        "skip_l3_review",     # 跳过 L3 Review
    ]

    def select_strategy(self, task: TaskSpec) -> str:
        """根据任务特征和历史胜率选择策略。"""
```

为什么用 Bandit 而不是 PPO/DQN？
- 每次 "尝试" 的反馈延迟很高（几分钟到几十分钟）
- 状态空间复杂（代码、任务描述、项目结构），难以定义好的状态表示
- Bandit 只关心"哪个策略更好"，不需要建模状态转移

**奖励函数设计**（参考 P-EVR 指标）：

```python
reward = (
    10.0 if attempt.is_verified else 0.0           # 通过验证
    - 3.0 * attempt.rework_count                   # 惩罚返工
    - 0.01 * attempt.token_usage                   # 惩罚token浪费
    - 0.1 * attempt.time_spent_minutes             # 惩罚时间浪费
    + 2.0 if attempt.is_first_try_verified else 0  # 一次通过奖励
)
```

### 4.3 "对话上下文保留多久，什么形式保留" — 三层记忆 + 产物版本控制

**P-EVR 的分层记忆策略已经在文档中给出了清晰答案，建议直接采纳：**

| 层级 | 保留内容 | 保留时长 | 存储形式 |
|------|----------|----------|----------|
| **L3 Project Memory** | 技术栈决策、架构模式、API约定、`.pilotcode/project_memory.json` | **永久**，跨 Session | JSON 文件，版本控制 |
| **L2 Session Memory** | 当前 Mission 的完整 DAG、每个节点的产物和验证结果 | **Session 期间** + 可选导出 | SQLite / JSON，会话结束后归档到 `~/.pilotcode/sessions/` |
| **L1 Working Memory** | 当前 Task 的代码上下文、最近5步执行轨迹、当前焦点 | **Task 执行期间**，切换 Task 时清空 | 内存中的 dataclass，必要时 snapshot 到 L2 |

**具体实现建议**：

```python
# L3: Project Memory
.pilotcode/
├── project_memory.json       # 技术栈、架构决策
├── conventions.md            # 项目规范
└── learned_patterns.json     # 从返工中学到的模式

# L2: Session Memory（归档后）
~/.pilotcode/sessions/
├── 20260424_143022/
│   ├── mission.json          # TaskSpec DAG
│   ├── artifacts/            # 产物版本
│   │   ├── v1/
│   │   ├── v2/
│   │   └── FINAL/
│   └── execution_trace.json  # 执行轨迹

# L1: Working Memory（内存中）
@dataclass
class WorkingMemory:
    current_task_id: str
    code_context: CodeContext          # 当前文件、相关接口
    recent_trace: list[ExecutionTrace] # 最近5步
    current_focus: str                 # 当前焦点描述
```

**对话上下文（LLM messages）的保留策略**：

```python
class MessageRetentionPolicy:
    """对话上下文保留策略。"""

    # 方案 A: 时间窗口（简单，推荐作为默认）
    max_age_hours: float = 2.0

    # 方案 B: Token 预算（精确，但需计算）
    max_context_tokens: int = 80000  # ~60k 输入留给模型

    # 方案 C: 事件驱动（P-EVR 推荐）
    # - Task 切换时：保留 summary，丢弃详细对话
    # - Mission 完成时：保留 key decisions，丢弃执行细节
    # - 返工循环时：保留 ReworkContext，丢弃失败的尝试对话
```

**推荐策略**：

1. **Working Memory（L1）**：保留当前 Task 的完整对话，但限制在 ~40k tokens
2. **Task 切换时**：将旧 Task 的对话压缩为 `TaskSummary`（200-500 tokens），存入 L2
3. **Mission 完成时**：将整个 Mission 压缩为 `MissionSummary`，存入 L3
4. **定期清理**：Session 结束后，只保留 `execution_trace.json`（操作日志），丢弃原始 LLM messages

---

## 五、可优化点汇总

### 5.1 架构层面优化

| 优化点 | 现状 | 建议 | 优先级 |
|--------|------|------|--------|
| 统一 Orchestrator | 4 个独立系统 | 合并为单一 MissionTracker + Orchestrator | P0 |
| DAG 执行引擎 | 只有 sequential/parallel | 引入拓扑排序 + 条件执行 | P0 |
| 状态机 | 无 | PENDING→...→VERIFIED 完整流转 | P0 |
| 验证层 | 无 | L1/L2/L3 三级验证 | P1 |
| 返工机制 | 无 | ReworkContext + Redesign 流程 | P1 |
| Worker 分级 | 7 种 agent 类型 | Simple/Standard/Complex/Debug 按复杂度匹配 | P2 |
| 产物版本控制 | 无 | 每次提交生成 v1/v2/FINAL 目录 | P2 |

### 5.2 代码层面优化

| 优化点 | 现状 | 建议 |
|--------|------|------|
| PlanMode 全局状态 | 模块级全局变量 `_plan_state` | 注入到 Orchestrator 中，支持多 Mission 并行 |
| Agent 创建 | 每次 `create_agent()` 新建实例 | 引入 Worker Pool，复用 Agent 实例 |
| 工具执行 | ToolOrchestrator 只分 read/write | 引入 DAG-aware 调度，支持条件分支 |
| 进度回调 | 每个模块自己维护 callbacks | 统一 EventBus，订阅/发布模式 |
| 错误处理 | try/except 分散在各处 | 统一异常类型：`Interrupt`, `RedesignNeeded`, `Blocked` |

### 5.3 性能层面优化

| 优化点 | 效果 |
|--------|------|
| Worker Pool | 避免重复初始化 Agent，减少 LLM 连接开销 |
| 工具结果缓存 | ToolOrchestrator 已有 cache，可复用到验证层 |
| 并行验证 | L1 静态分析和 L2 测试可并行运行 |
| 增量 Code Review | L3 Review 只 diff 变更部分，不是全文件 |

---

## 六、推荐的第一期 MVP 范围

如果资源有限，先做这 5 件事（约 2 周，~1,500 行新代码）：

1. **TaskSpec + DAG 引擎** — 把 PlanMode 从字符串列表升级为结构化 DAG
2. **统一 Tracker** — 一个可查询的 Mission 状态中心
3. **状态机** — 任务从 `PENDING` 到 `DONE` 的流转
4. **L1 验证** — 跑 linter + type check（已有工具，只是整合）
5. **返工上下文** — 第一次失败时保留上下文，让 Worker "增量修正" 而不是重写

这样 PilotCode 就能从 "跑完拉倒" 进化到 "计划 → 执行 → 验证 → 返工" 的闭环。
