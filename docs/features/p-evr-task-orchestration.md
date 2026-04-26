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
┌──────────────────────────────────────────────────────────────────────────┐
│                            MissionAdapter                                │
│                 (编排入口：plan → run → report)                           │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
 ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐
 │   Planner    │  │Orchestrator  │  │  ProjectMemory  │
 │  (_plan_)    │  │ (调度核心)    │  │  (跨任务记忆)    │
 └──────┬───────┘  └──────┬───────┘  └─────────────────┘
        │                 │
        ▼                 ▼
 ┌──────────────┐  ┌──────────────┐
 │   Mission    │  │     DAG      │
 │ (Phase集合)   │  │ (DagExecutor)│
 └──────────────┘  └──────┬───────┘
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
┌──────────┐      ┌──────────┐       ┌──────────────┐
│  Worker  │      │Verifier  │       │  Reflector   │
│(LLM+Tools│      │(L1/L2/L3)│       │ (健康检查)    │
└────┬─────┘      └────┬─────┘       └──────────────┘
     │                 │
     └────────┬────────┘
              ▼
       ┌──────────────┐
       │ MissionTracker│  ──→  实时快照 / 进度通知 / SQLite持久化
       │   (追踪中心)   │
       └──────────────┘
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
| `timeout_seconds` | 执行超时（秒） | `300.0` |
| `worker_type` | 执行者类型 | `simple/standard/complex/debug/auto` |

**实现文件**：`src/pilotcode/orchestration/task_spec.py`

TaskSpec 的设计原则：
- **单一职责**：每个任务聚焦一个文件或一个函数的修改
- **显式依赖**：通过 `dependencies` 声明前置任务，由 DAG 保证执行顺序
- **可验证性**：每个任务附带 `acceptance_criteria`，作为 L2 验证的输入
- **可超时**：`timeout_seconds` 防止弱模型在复杂任务上无限循环

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

**关键数据结构**：
```python
class DagExecutor:
    nodes: dict[str, DagNode]          # task_id -> DagNode
    edges: list[DagEdge]               # 依赖边 (from -> to)
    _adj_in: dict[str, list[str]]      # 反向邻接表
    _adj_out: dict[str, list[str]]     # 正向邻接表
    _topo_order: list[str]             # 拓扑序
    _ready_cache: list[DagNode] | None # 就绪任务缓存
```

**性能优化**：
- 反向邻接表 `_adj_in` 使 `get_ready_tasks()` 从 O(VE) 降至 O(V·avg_in_degree)
- 就绪缓存 `_ready_cache` 在任务状态变化时自动失效
- 支持**动态 DAG**：`add_task()` / `remove_task()` 可在运行时修改拓扑
- Kahn 算法拓扑排序，自动检测循环依赖

---

## 四、Execute 层：状态机驱动的执行

### 4.1 执行状态机

每个任务在执行中经历严格状态流转：

```
                    ┌─────────────┐
         ┌─────────→│   PENDING   │←────────┐
         │          └──────┬──────┘         │
         │                 │ ASSIGN         │
         │                 ▼                │
         │          ┌─────────────┐         │
         │          │  ASSIGNED   │         │
         │          └──────┬──────┘         │
         │                 │ START          │
         │                 ▼                │
         │          ┌─────────────┐         │
    REJECT│    START│ IN_PROGRESS │         │
         │          └──────┬──────┘         │
         │                 │ SUBMIT         │
         │                 ▼                │
         │          ┌─────────────┐         │
         │    BEGIN_REVIEW│ REVIEWING│       │
         │          └──────┬──────┘         │
         │      ┌─────────┼─────────┐       │
         │      │         │         │       │
         │ APPROVE  REQUEST_REWORK  │       │
         │      │         │         │       │
         │      ▼         ▼         ▼       │
         │ ┌────────┐ ┌──────────┐ │REJECT │
         └─┤  DONE  │ │NEEDS_REWORK├─┘      │
           └───┬────┘ └─────┬────┘         │
               │ COMPLETE   │ RETRY        │
               ▼            └──────────────┘
          ┌─────────┐
          │VERIFIED │
          └─────────┘
```

**实现文件**：`src/pilotcode/orchestration/state_machine.py`

**关键特性**：
- `_state_entered_at` 记录进入每个状态的时间戳，支持 `time_in_current_state()` 停滞检测
- `on_state_change` 回调实现事件驱动：状态变化 → 触发调度器重新评估就绪任务
- 非法转换抛出 `InvalidTransitionError`，防止编排逻辑错误
- StateMachine 构造时绑定 DagNode，setter 自动同步 DAG 节点状态

### 4.2 事件驱动调度器

Orchestrator 是 P-EVR 的核心引擎，负责主事件循环。

替换传统的 `while + sleep(0.5)` 轮询：

```python
async def run(self, mission: Mission) -> dict[str, Any]:
    task_event = asyncio.Event()
    active_workers: dict[asyncio.Task, DagNode] = {}
    
    while not self.tracker.all_done(mid):
        # 健康检查（每30秒）
        if now - last_health_check > 30.0:
            health = reflector.check(mid, self.tracker)
            ...
        
        # 填充就绪任务
        self._enqueue_ready(mid, active_workers)
        
        if not active_workers:
            # 无任务时阻塞等待事件
            await task_event.wait()
            task_event.clear()
            continue
        
        # 等待至少一个 Worker 完成
        done, _ = await asyncio.wait(
            active_workers.keys(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in done:
            node = active_workers.pop(t)
            task_event.set()  # 触发下游调度
```

**优势**：
- 无任务时完全阻塞，不消耗 CPU
- 任务完成立即触发下一轮调度，延迟 < 1ms
- 支持 `asyncio.Event` 的外部触发（如用户取消、状态变化）

### 4.3 任务执行管道

每个任务经历完整的 P-EVR 生命周期：

```
ASSIGN → START → [Worker执行(带超时)] → SUBMIT → L1验证 → L2验证 → L3验证 → APPROVE → COMPLETE
                                          ↓
                                    任一验证失败 → REQUEST_REWORK / REJECT
```

**Worker 执行**：
- 使用 `asyncio.wait_for()` 实现超时控制，默认 300 秒
- 超时后自动级联取消下游任务，防止无效计算
- 超时任务转为 `REJECTED`，记录 `_exec_result` 供分析

**Worker 实现**：

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
            # 更新 ProjectMemory
            self._update_memory_from_tool(tool, result_text, ...)
        
        total_turns += 1
```

**实现文件**：`src/pilotcode/orchestration/adapter.py` — `_llm_worker()`

**关键设计**：
- **Worker 是无状态的**，所有状态由 Orchestrator 维护
- **复杂度感知的 turn 限制**：简单任务 5 轮，复杂任务 50 轮
- **工具执行结果实时反馈**：LLM 能立即看到 FileRead/Grep/Bash 的结果并调整策略
- **ProjectMemory 注入**：Worker prompt 中包含已发现的文件、框架、规范，避免重复读取

### 4.4 上下文防漂移机制

**问题**：长任务执行中，模型容易忘记原始目标，开始"自由发挥"。

**解决方案**：

1. **目标锚定**：每次工具调用前，prompt 中强制重复当前 Task 的 objective
2. **执行轨迹日志**：维护只增不减的操作日志（FileRead → FileEdit → Bash）
3. **定期对齐检查**：每轮结束后检查是否偏离目标
4. **Continue Prompt**：非首轮使用 `_build_continue_prompt()`，总结已完成的动作、修改的文件、遇到的错误

---

## 五、Verify 层：每个任务都有 Review 和测试

### 5.1 三级验证体系

```
Level 1: 自动化检查 (自动，零成本)
    ├── 执行成功且产生输出/文件变更
    └── 静态分析：行数限制、模式匹配、must_use/must_not_use

Level 2: 单元/集成测试 (自动，低成本)
    ├── 自动发现 pytest 测试文件并运行
    ├── 边界测试覆盖
    └── 集成测试：模块间交互验证

Level 3: Code Review (LLM / 静态分析)
    ├── FULL_L3: 结构化 JSON 评分 {"verdict", "score", "feedback"}
    ├── SIMPLIFIED_L3: PASS/FAIL 字符串匹配
    └── STATIC_ONLY: ruff + mypy + 启发式规则（不调用 LLM）
```

**实现文件**：
- `src/pilotcode/orchestration/verifiers/adapter_verifiers.py` — L1/L2/L3 实现
- `src/pilotcode/orchestration/verifiers/adaptive_verifiers.py` — 降级验证器

**验证执行流程**：

```
Worker提交产物
    │
    ▼
┌──────────────┐
│ Level 1 检查  │ ← 全自动化，失败直接退回
│ (执行成功?)  │
└──────┬───────┘
       │ PASS
       ▼
┌──────────────┐
│ Level 2 测试  │ ← 自动运行测试套件
│ (pytest通过?)│
└──────┬───────┘
       │ PASS
       ▼
┌──────────────┐
│ Level 3 Review│ ← 根据模型能力选择验证策略
│ (代码审查)   │
└──────┬───────┘
       │
   ┌───┴───┐
   │       │
 APPROVE  REJECT
   │       │
   ▼       ▼
VERIFIED  NEEDS_REWORK
```

验证结果存储在 `DagNode.artifacts` 中：
- `_exec_result` — ExecutionResult（执行结果）
- `_verification_1` — L1 VerificationResult
- `_verification_2` — L2 VerificationResult
- `_verification_3` — L3 VerificationResult

---

## 六、Reflect 层：返工与重设计

### 6.1 问题分级与响应策略

| 级别 | 触发条件 | 响应策略 |
|------|---------|---------|
| **Minor** | 命名不规范、缺少注释、格式问题 | 自动修复或由 Worker 立即修改，不调整计划 |
| **Major** | 逻辑错误、边界处理缺失、测试失败 | Worker 返工，保留已完成上下文，重新执行 |
| **Critical** | 架构设计缺陷、需求理解偏差 | 触发 Redesign，回到 Planner 重新分解 |
| **Blocked** | 外部依赖不可用、环境配置问题 | 挂起任务，通知 Orchestrator 调整 DAG |

### 6.2 智能重试（_smart_retry）

任务进入 `NEEDS_REWORK` 后：
- 递增 `rework_count`，超过上限则转为 `REJECTED`
- 将失败信息注入 ProjectMemory，避免 Worker 重复踩坑
- 重新调度到 Worker，保留之前读取的文件上下文

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

### 6.3 Reflector 健康检查

每 30 秒执行一次全局健康检查：

```python
reflector = Reflector()
health = reflector.check(mid, tracker)
```

检测指标：
- 失败任务比例是否超过阈值
- 是否存在长期停滞的任务（`time_in_current_state()` 过长）
- 下游任务是否被大量阻塞

如果健康风险严重，触发 `mission:redesign_triggered` 事件，由上层决策是否重新规划。

---

## 七、MissionTracker — 全局追踪中心

**实现文件**：`src/pilotcode/orchestration/tracker.py`

```python
class MissionTracker:
    _missions: dict[str, Mission]
    _dag_executors: dict[str, DagExecutor]
    _state_machines: dict[str, dict[str, StateMachine]]
    _db_conn: sqlite3.Connection | None  # 可选持久化
```

**职责**：
- 注册 Mission 时创建 StateMachine 并绑定 DagNode
- 状态变化回调中自动持久化到 SQLite（WAL 模式）
- 提供 `get_ready_tasks()`、`get_snapshot()`、`all_done()` 等查询接口

**MissionSnapshot**：
```python
@dataclass
class MissionSnapshot:
    mission_id: str
    title: str
    status: str  # pending/running/paused/completed/failed
    total_tasks: int
    completed_tasks: int
    verified_tasks: int
    failed_tasks: int
    blocked_tasks: int
    in_progress_tasks: int
    ready_tasks: int
    critical_path_length: int
    task_states: dict[str, str]
```

---

## 八、数据流

### 正常执行流

```
1. 用户: "添加用户认证系统"
   ↓
2. MissionAdapter._plan_mission() → Mission (3 phases, 8 tasks)
   ↓
3. Orchestrator.set_mission_plan() → DagExecutor.build() → 拓扑排序
   ↓
4. _enqueue_ready() → 启动无前依赖的任务（t1, t2, t3 并发）
   ↓
5. Worker 执行 t1 → 修改 auth.py → SUBMIT
   ↓
6. L1: 有文件变更 ✓ → L2: 无测试 → L3: 代码审查通过 ✓
   ↓
7. StateMachine: APPROVE → COMPLETE → VERIFIED
   ↓
8. task_event.set() → _enqueue_ready() 启动 t4（依赖 t1）
   ↓
9. ... 重复直到所有任务完成
   ↓
10. 返回结果：{mission_id, snapshot, task_outputs, metrics}
```

### 失败处理流

```
Worker 执行 t5 → 生成语法错误的代码 → SUBMIT
   ↓
L1: 有文件变更 ✓ → L2: pytest 失败 ✗
   ↓
StateMachine: REQUEST_REWORK → NEEDS_REWORK
   ↓
_smart_retry(t5):
   - rework_count = 1
   - 在 ProjectMemory 记录失败原因
   - 重新提交 Worker，prompt 中注入失败历史
   ↓
Worker 重试 t5 → 修正代码 → SUBMIT → L2 通过 → APPROVE
```

---

## 九、性能与扩展性

| 指标 | 数值 | 说明 |
|---|---|---|
| 调度延迟 | < 1ms | 事件驱动，无轮询开销 |
| 并发上限 | 可配置（默认 3） | `OrchestratorConfig.max_concurrent_workers` |
| DAG 查询 | O(V·avg_in_degree) | 反向邻接表 + 就绪缓存 |
| 状态持久化 | ~5ms/次 | SQLite WAL 模式，异步友好 |
| 健康检查 | 30s 间隔 | 不阻塞主循环 |

---

## 十、与 LLM 规划能力的互补

### 10.1 分工边界

| 能力 | PilotCode 框架 | LLM |
|-----|---------------|-----|
| **任务分解** | 提供 JSON schema + 启发式规则 | 理解意图，将模糊需求拆成具体任务 |
| **依赖推理** | DAG 构建、拓扑排序、cycle 检测 | 在 system prompt 引导下声明依赖 |
| **执行调度** | 并行 wave 计算、并发控制、turn 限制 | 不擅长精确的状态管理 |
| **执行实现** | 提供工具集、cwd 同步、XML fallback | 决定读什么、改什么、调用什么工具 |
| **质量保证** | L1 静态规则 + L2 自动化测试 | L3 代码审查（设计合理性、边界处理） |
| **容错恢复** | 状态机、重做计数、回滚机制 | 从失败反馈中重新规划 |

### 10.2 不同 LLM 的最优使用策略

基于 E2E 测试（44 个测试用例，覆盖代码生成、工具调用、上下文保持、代码编辑、任务规划）的验证结果：

| LLM 类型 | 能力特征 | P-EVR 适配策略 |
|---------|---------|---------------|
| **强规划 + 强执行**<br>(如 Claude 3.5 Sonnet) | 工具调用规范、上下文保持好、编辑积极 | P-EVR 轻量模式：Plan 由 LLM 主导，框架只做 L1/L2 验证和 DAG 调度 |
| **强规划 + 弱执行**<br>(如 Qwen3-30B) | 裸代码生成强，但工具格式错误、编辑回避 | P-EVR 重引导模式：system prompt 强化工具使用规则，框架增强 XML fallback |
| **推理模型**<br>(如 Qwen3.6-35B) | 推理能力强但输出 thinking 内容、速度慢 | P-EVR 过滤模式：thinking 剥离 + 更长的 turn 限制容忍慢速推理 |

### 10.3 核心洞察

> **P-EVR 不是替代 LLM 做计划，而是给 LLM 的计划能力提供一个"安全执行容器"。**

| 没有 P-EVR | 有 P-EVR |
|-----------|---------|
| LLM 输出 plan，但格式不规范导致无法解析 | `_extract_json()` + DAG 验证确保 plan 可执行 |
| LLM 执行时忘记之前做了什么，重复读取文件 | 框架维护 `read_file_state` 和对话历史 |
| LLM 编辑后不做验证，留下语法错误 | L1/L2/L3 分层验证，失败自动重做 |
| LLM 在多文件修改中遗漏某个文件 | DAG 依赖检查 + checklist 提醒 |
| LLM 陷入无限循环（反复尝试错误的 edit） | `max_turns` 限制 + `max_rework_attempts` 限制 |

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

# 64K 上下文：LLM 主导
adapter = MissionAdapter(context_budget=65536)
# -> strategy=LLM_HEAVY
```

---

## 十二、与其他模块的关系

| 模块 | 交互方式 |
|---|---|
| `query_engine.py` | Worker 使用 QueryEngine 调用 LLM + Tools |
| `tools/registry.py` | Worker 排除交互式工具（AskUser），只使用自治工具 |
| `project_memory.py` | Worker 读取历史发现，记录新的文件/规范/失败 |
| `state_machine.py` | Orchestrator 驱动状态转换，Tracker 订阅变化 |
| `verifiers/*.py` | L1/L2/L3 验证器注册到 Orchestrator，按序执行 |
| `telemetry.py` | Orchestrator.run() 返回 metrics（耗时、token、任务计数）|
| `model_capability/` | 根据模型能力动态调整规划策略、验证器、任务粒度 |

---

## 十三、使用示例

### 简单任务（自动跳过 Plan）

```python
from pilotcode.orchestration.adapter import MissionAdapter

adapter = MissionAdapter()
result = await adapter.run("Fix the typo in README.md")
# 复杂度=1，auto_approve_simple=True，直接 Execute，无需 Plan
```

### 复杂任务（完整 P-EVR 循环）

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

### 查看执行报告

```python
from pilotcode.orchestration.report import ExecutionReport

report = ExecutionReport.from_mission(result.mission)
print(report.summary())
# 输出：Mission 完成度、各 Task 状态、返工次数、总耗时
```

---

## 十四、参考

- **模型能力自适应文档**: `docs/features/model_capability_adaptation.md`
- **P-EVR 架构设计文档**: `~/tmp/P-EVR-Architecture.md`
- **E2E 测试框架**: `tests/e2e/model_capability/` — LLM 能力评估与框架修复验证
- **Context Strategy 实验**: `tests/orchestration/experiment_results.json`

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
