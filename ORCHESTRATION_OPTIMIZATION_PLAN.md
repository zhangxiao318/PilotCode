# PilotCode 任务编排系统优化方案

> 版本：v1.0  
> 基于：`task_orchestration_analysis_report.md` + 代码静态审查 + 运行时验证  
> 目标：将四层编排系统从"功能可用"推进到"生产可靠"

---

## 1. 方案总览

### 1.1 当前架构诊断

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 4: Agent Orchestrator (agent_orchestrator.py)                    │
│  5种工作流全部委托给 MissionAdapter，自身为薄壳                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 3: P-EVR Orchestration (orchestration/)                          │
│  核心引擎，但存在 God Class、轮询调度、状态分离、类型重复                   │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 2: Tool Orchestration (services/tool_orchestrator.py)            │
│  设计良好，与上层缺乏标准化接口                                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 1: Task Queue (services/task_queue.py)                           │
│  FIFO 队列，无优先级，与 P-EVR 无集成                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 目标架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Unified Orchestration Facade                     │
│              run(request) → Plan → Schedule → Execute → Report          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐             │
│  │  Planner    │   │  Scheduler   │   │  Verifier        │             │
│  │  (LLM Plan) │──▶│ (Event-Driven│──▶│  (L1→L2→L3)     │             │
│  └──────┬──────┘   └──────┬───────┘   └────────┬─────────┘             │
│         │                 │                     │                       │
│  ┌──────▼──────┐   ┌──────▼───────┐   ┌────────▼─────────┐             │
│  │  Mission    │   │  Worker      │   │  Rework Manager  │             │
│  │  Adapter    │   │  Pool        │◀──│  (Smart Retry)   │             │
│  └─────────────┘   └──────────────┘   └──────────────────┘             │
├─────────────────────────────────────────────────────────────────────────┤
│  Shared Infrastructure                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ DAG      │ │ State    │ │ Project  │ │ Error    │ │ Reflector    │ │
│  │ Engine   │ │ Machine  │ │ Memory   │ │ Recovery │ │ (Health)     │ │
│  │ (Indexed)│ │ (Unified)│ │ (Persist)│ │ (Circuit │ │ (Stall/     │ │
│  │          │ │          │ │          │ │  Breaker)│ │  Deadlock)   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────────────────────────┤
│  Tool Layer (Independent)                                               │
│  ToolOrchestrator + ToolCache + PriorityTaskQueue + TaskTimeout         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

| 原则 | 说明 |
|------|------|
| **Single Source of Truth** | DAG 节点状态 = StateMachine 状态，禁止双写 |
| **Fail Fast, Fail Loud** | 消除 `except Exception: pass`，强制日志 + 传播 |
| **Event-Driven > Polling** | 任务完成事件触发下游调度，而非 sleep 轮询 |
| **Structured > Stringly** | LLM 输出用 JSON schema， verdict 用 Enum |
| **Explicit > Implicit** | 全局单例 → 依赖注入容器，测试可 mock |

---

## 2. 分阶段实施计划

### Phase 1：止血与类型统一（1 周）
**目标**：消除已知的类型不一致、未实现接口、示例代码崩溃问题

### Phase 2：核心能力补全（2 周）
**目标**：补全停滞检测、超时控制、Reflector 健康检查、L3 验证可靠性

### Phase 3：架构重构（3-4 周）
**目标**：adapter 拆分、DAG 反向索引、事件驱动调度、ProjectMemory 持久化

### Phase 4：长期建设（4-6 周）
**目标**：单元测试覆盖、动态 DAG、任务优先级、可观测性增强

---

## 3. Phase 1：止血与类型统一

### 3.1 统一 VerificationResult

**现状**：`orchestrator.py` 和 `verifier/base.py` 各有一个 `VerificationResult`，`verdict` 字段类型不同（`str` vs `Verdict` Enum）。

**变更**：

```python
# src/pilotcode/orchestration/__init__.py
# 移除从 orchestrator 导入 VerificationResult
# 改为从 verifier 导入
from .verifier.base import VerificationResult, Verdict, BaseVerifier
```

```python
# src/pilotcode/orchestration/orchestrator.py
# 删除本文件的 VerificationResult 定义
# 从 verifier.base 导入
from .verifier.base import VerificationResult, Verdict
```

**影响面**：
- `orchestrator.py` 中 `_handle_verification_failure` 使用 `"REJECT"` 字符串比较，需改为 `Verdict.REJECT`
- `adapter.py` 中 L1/L2/L3 verifier 返回的 `verdict="APPROVE"` 需改为 `Verdict.APPROVE`
- `tests/test_orchestration.py` 可能引用旧类，需同步更新

**验收标准**：`grep -r "class VerificationResult" src/` 只剩 1 处。

### 3.2 合并/清理 ProjectMemory

**现状**：
- `orchestration/project_memory.py`：功能完整，跨任务共享记忆
- `orchestration/context/project_memory.py`：112 行，功能重叠

**变更**：

```python
# src/pilotcode/orchestration/context/project_memory.py
# 改为对上级 project_memory.py 的兼容层
from ..project_memory import ProjectMemory as _ProjectMemory

# 保留旧导入路径兼容，但标记为 deprecated
ProjectMemory = _ProjectMemory
```

或在 `__init__.py` 中统一导出：

```python
# 统一从 orchestration.project_memory 导入
from .project_memory import ProjectMemory, FileSnapshot, FailedAttempt
```

### 3.3 实现 TaskDecomposer 存根

**现状**：`examples/orchestration/` 中 4 个示例都导入 `TaskDecomposer`，但源码中不存在。

**方案 A（推荐）**：实现轻量级 TaskDecomposer

```python
# src/pilotcode/orchestration/decomposer.py
from enum import Enum, auto
from dataclasses import dataclass

class DecompositionStrategy(Enum):
    NONE = "none"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"

@dataclass
class DecompositionResult:
    strategy: DecompositionStrategy
    confidence: float  # 0-1
    reasoning: str
    subtasks: list[dict]

class TaskDecomposer:
    """Heuristic task decomposer (non-LLM fallback)."""
    
    def analyze(self, task: str) -> DecompositionResult:
        # 基于规则的判断：长度、关键词、复杂度
        word_count = len(task.split())
        has_and = " and " in task.lower() or "," in task
        has_then = " then " in task.lower() or "first" in task.lower()
        
        if word_count < 10 and not has_and:
            return DecompositionResult(
                strategy=DecompositionStrategy.NONE,
                confidence=0.9,
                reasoning="Task is simple and atomic",
                subtasks=[],
            )
        elif has_then:
            return DecompositionResult(
                strategy=DecompositionStrategy.SEQUENTIAL,
                confidence=0.7,
                reasoning="Task contains sequential keywords",
                subtasks=[],
            )
        else:
            return DecompositionResult(
                strategy=DecompositionStrategy.HIERARCHICAL,
                confidence=0.6,
                reasoning="Task is complex, needs hierarchical decomposition",
                subtasks=[],
            )
    
    def auto_decompose(self, task: str) -> DecompositionResult:
        return self.analyze(task)
```

**方案 B（备选）**：如果决定不用 TaskDecomposer，则在 `__init__.py` 中导出并抛 `NotImplementedError`，示例中捕获异常给出友好提示。

**验收标准**：`python examples/orchestration/basic_decomposition.py` 不再 ImportError。

### 3.4 消除裸 `except Exception: pass`

**清单**：

| 文件 | 位置 | 改进 |
|------|------|------|
| `tracker.py:308` | `_emit()` | `except Exception: logging.warning("Event callback failed", exc_info=True)` |
| `orchestrator.py:117` | `_notify()` | 同上，至少记录日志 |
| `adapter.py:784, 826` | `_explore_codebase()` | `except Exception as e: logger.debug("Exploration step failed: %s", e)` |
| `state_machine.py` | 回调 | 包装回调执行，记录失败但不阻断状态转换 |

---

## 4. Phase 2：核心能力补全

### 4.1 任务超时控制

**现状**：`_execute_task` 没有超时，`adapter.py` 的 LLM Worker 只有 `max_turns` 限制但无 wall-clock 超时。

**变更**：

```python
# task_spec.py
@dataclass
class TaskSpec:
    # ... existing fields ...
    timeout_seconds: float = 300.0  # 默认 5 分钟

# orchestrator.py
async def _execute_task(self, mission_id: str, node: DagNode) -> None:
    task = node.task
    try:
        await asyncio.wait_for(
            self._execute_task_inner(mission_id, node),
            timeout=task.timeout_seconds,
        )
    except asyncio.TimeoutError:
        sm = self.tracker.get_state_machine(mission_id, task.id)
        if sm:
            sm.transition(
                Transition.CANCEL,
                reason=f"Timeout after {task.timeout_seconds}s",
                actor="orchestrator",
            )
        self._cancel_downstream_tasks(mission_id, task.id)
        self._notify("task:timeout", {...})
```

**配置**：`OrchestratorConfig.default_timeout_seconds = 300`

### 4.2 停滞检测（Stall Detection）

**现状**：`reflector.py:_find_stalled_tasks` 是空实现。

**依赖前置**：`StateMachine` 需要记录状态进入时间戳。

```python
# state_machine.py
@dataclass
class StateChangeEvent:
    # ... existing fields ...
    timestamp: str  # ISO format (already exists)

class StateMachine:
    def __init__(self, task_id: str, ...):
        # ...
        self._state_entered_at: dict[TaskState, str] = {}
    
    def transition(self, ...):
        # ... existing logic ...
        self._state_entered_at[new_state] = datetime.now(timezone.utc).isoformat()
    
    def time_in_current_state(self) -> float:
        """Return seconds in current state."""
        entered = self._state_entered_at.get(self.state)
        if not entered:
            return 0.0
        from datetime import datetime
        dt = datetime.fromisoformat(entered)
        return (datetime.now(timezone.utc) - dt).total_seconds()
```

然后实现停滞检测：

```python
# reflector.py
STALL_THRESHOLD_SECONDS = 120  # 2 分钟无状态变化视为停滞

class Reflector:
    def _find_stalled_tasks(self, mission_id: str, tracker: MissionTracker) -> list[str]:
        stalled = []
        for task_id, sm in tracker._state_machines.get(mission_id, {}).items():
            if sm.state == TaskState.IN_PROGRESS and sm.time_in_current_state() > STALL_THRESHOLD_SECONDS:
                stalled.append(task_id)
        return stalled
```

### 4.3 Reflector 接入主循环

**变更**：在 `Orchestrator.run()` 中周期性调用 Reflector。

```python
# orchestrator.py
async def run(self, mission: Mission) -> dict[str, Any]:
    self.set_mission_plan(mission)
    mid = mission.mission_id
    
    # 初始化 Reflector
    from .rework.reflector import Reflector
    reflector = Reflector()
    last_health_check = asyncio.get_event_loop().time()
    HEALTH_CHECK_INTERVAL = 30  # 每 30 秒检查一次
    
    while not self.tracker.all_done(mid):
        # ... existing ready task logic ...
        
        # 周期性健康检查
        now = asyncio.get_event_loop().time()
        if now - last_health_check > HEALTH_CHECK_INTERVAL:
            health = reflector.check(mid, self.tracker)
            if not health.healthy:
                self._notify("mission:health_warning", {
                    "mission_id": mid,
                    "risks": health.risks,
                    "recommendations": health.recommendations,
                })
                # 如果有严重风险，考虑触发重设计
                if reflector.should_trigger_redesign(mid, self.tracker):
                    self._notify("mission:redesign_triggered", {...})
                    # 可选：触发 Mission 重规划
            last_health_check = now
        
        await asyncio.sleep(0.1)  # 降低轮询频率
```

### 4.4 L3 代码审查结构化输出

**现状**：字符串匹配 `"approve" in review.lower()`。

**变更**：要求 LLM 输出 JSON，使用 `response_format={"type": "json_object"}`（OpenAI/DeepSeek 兼容）。

```python
# adapter.py _code_review_verifier
review_prompt = (
    f"Review the following code changes...\n\n"
    "Respond ONLY with a JSON object in this exact format:\n"
    '{"verdict": "APPROVE|NEEDS_REWORK", "score": 0-100, "feedback": "concise review"}'
)

messages = [
    Message(role="system", content="You are a code reviewer. Output JSON only."),
    Message(role="user", content=review_prompt),
]

try:
    accumulated = ""
    async for chunk in client.chat_completion(
        messages=messages, temperature=0.2, stream=False,
        # 如果 API 支持
        response_format={"type": "json_object"},
    ):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        c = delta.get("content")
        if c:
            accumulated += c
    
    review_data = json.loads(accumulated)
    verdict_str = review_data.get("verdict", "NEEDS_REWORK").upper()
    score = float(review_data.get("score", 0))
    feedback = review_data.get("feedback", "No feedback provided")
    
    verdict = Verdict.APPROVE if verdict_str == "APPROVE" else Verdict.NEEDS_REWORK
    
    return VerificationResult(
        task_id=task.id,
        level=3,
        passed=(verdict == Verdict.APPROVE),
        score=score,
        feedback=feedback,
        verdict=verdict,
    )
except (json.JSONDecodeError, KeyError, ValueError) as e:
    # 回退到字符串匹配
    logger.warning("L3 JSON parse failed, falling back to string match: %s", e)
    # ... existing fallback logic ...
```

### 4.5 adapter.py 初步拆分

**现状**：922 行，承担 6+ 职责。

**Phase 2 先做的最小拆分**（不解耦所有功能，只分离出独立的模块）：

```
adapter.py (保留入口和协调逻辑)
├── planners/mission_planner.py    ← 提取 _plan_mission, _extract_json
├── verifiers/adapter_verifiers.py ← 提取 _simple_verifier, _test_verifier, _code_review_verifier
└── explorers/code_explorer.py     ← 提取 _explore_codebase
```

**具体**：

```python
# planners/mission_planner.py
class MissionPlanner:
    def __init__(self, context_budget: int = 16000):
        self.context_budget = context_budget
        self.strategy = ContextStrategySelector.select(context_budget)
        self.plan_adjuster = MissionPlanAdjuster(strategy=self.strategy)
    
    async def plan(self, user_request: str, exploration: dict | None = None) -> Mission:
        # _plan_mission 的核心逻辑移到这里
        ...
```

```python
# verifiers/adapter_verifiers.py
class AdapterL1Verifier:
    @staticmethod
    async def verify(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
        # _simple_verifier 逻辑
        ...

class AdapterL2Verifier:
    @staticmethod
    async def verify(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
        # _test_verifier 逻辑
        ...

class AdapterL3Verifier:
    @staticmethod
    async def verify(task: TaskSpec, exec_result: ExecutionResult) -> VerificationResult:
        # _code_review_verifier 逻辑（含 JSON 输出）
        ...
```

---

## 5. Phase 3：架构重构

### 5.1 DAG 反向索引与执行波次优化

**现状**：每次 `get_ready_tasks()` 遍历全部 edges，O(E)。

**变更**：

```python
# dag.py
class DagExecutor:
    def __init__(self, mission: Mission):
        # ... existing ...
        self._adj_in: dict[str, list[str]] = {}    # task -> dependencies
        self._adj_out: dict[str, list[str]] = {}   # task -> dependents
        self._ready_cache: list[str] | None = None
    
    def build(self) -> list[str]:
        # ... existing build logic ...
        # Build adjacency lists
        for task in self.nodes:
            self._adj_in[task] = []
            self._adj_out[task] = []
        for edge in self.edges:
            self._adj_in[edge.to_task].append(edge.from_task)
            self._adj_out[edge.from_task].append(edge.to_task)
        # Compute depths in O(V+E) via topo order
        for tid in self._topo_order:
            if self._adj_in[tid]:
                self.nodes[tid].depth = max(
                    self.nodes[d].depth for d in self._adj_in[tid]
                ) + 1
        return self._topo_order
    
    def get_ready_tasks(self) -> list[DagNode]:
        if self._ready_cache is not None:
            return self._ready_cache
        ready = []
        for node in self.nodes.values():
            if node.state != TaskState.PENDING:
                continue
            # O(in_degree) instead of O(E)
            deps_satisfied = all(
                self.nodes[dep].state in {TaskState.VERIFIED, TaskState.DONE}
                for dep in self._adj_in[node.task_id]
            )
            if deps_satisfied:
                ready.append(node)
        ready.sort(key=lambda n: (n.depth, self._topo_order.index(n.task_id)))
        self._ready_cache = ready
        return ready
    
    def update_task_state(self, task_id: str, state: TaskState) -> None:
        self.nodes[task_id].state = state
        self._ready_cache = None  # Invalidate cache
```

**收益**：`get_ready_tasks()` 从 O(VE) → O(V·avg_in_degree)。对于 100 任务、avg_in_degree=2 的 DAG，提升约 50 倍。

### 5.2 StateMachine ↔ DagNode 状态统一

**方案**：StateMachine 持有 DagNode 引用，状态变更自动同步。

```python
# state_machine.py
class StateMachine:
    def __init__(self, task_id: str, node: DagNode | None = None):
        self.task_id = task_id
        self._node = node
        self._state = TaskState.PENDING
        self._history: list[StateChangeEvent] = []
        self._callbacks: list[Callable[[StateChangeEvent], None]] = []
        self._state_entered_at: dict[TaskState, datetime] = {}
    
    @property
    def state(self) -> TaskState:
        return self._state
    
    @state.setter
    def state(self, value: TaskState):
        self._state = value
        if self._node is not None:
            self._node.state = value
    
    def transition(self, transition: Transition, reason: str = "", actor: str = "orchestrator") -> TaskState:
        key = (self._state, transition)
        if key not in TRANSITION_TABLE:
            raise InvalidTransitionError(self._state, transition)
        
        old_state = self._state
        new_state = TRANSITION_TABLE[key]
        
        # 使用 setter 自动同步 DagNode
        self.state = new_state
        
        event = StateChangeEvent(
            task_id=self.task_id,
            from_state=old_state,
            to_state=new_state,
            transition=transition,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            actor=actor,
        )
        self._history.append(event)
        self._state_entered_at[new_state] = datetime.now(timezone.utc)
        
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning("State change callback failed: %s", e)
        
        return new_state
```

**注册时绑定**：

```python
# tracker.py
for task in mission.all_tasks():
    node = dag.nodes.get(task.id)
    sm = StateMachine(task.id, node=node)  # 绑定 node
    sm.on_state_change(lambda evt, mid=mission.mission_id: self._on_state_change(mid, evt))
    self._state_machines[mission.mission_id][task.id] = sm
```

**删除冗余**：`tracker._on_state_change` 中不再需要 `dag.update_task_state()`。

### 5.3 事件驱动调度

**目标**：消除 `while` 循环中的 `asyncio.sleep(0.5)`。

```python
# orchestrator.py
class EventDrivenOrchestrator(Orchestrator):
    def __init__(self, config: OrchestratorConfig | None = None):
        super().__init__(config)
        self._task_completed_event = asyncio.Event()
        self._ready_queue: asyncio.Queue[DagNode] = asyncio.Queue()
    
    def _on_task_state_change(self, mission_id: str, event: StateChangeEvent) -> None:
        """Hook into state changes to trigger scheduling."""
        if event.to_state in {TaskState.DONE, TaskState.REJECTED, TaskState.CANCELLED}:
            # A task finished - its dependents may now be ready
            self._task_completed_event.set()
    
    async def run(self, mission: Mission) -> dict[str, Any]:
        self.set_mission_plan(mission)
        mid = mission.mission_id
        
        # Hook state changes for event-driven scheduling
        for task_id, sm in self.tracker._state_machines.get(mid, {}).items():
            sm.on_state_change(lambda evt: self._on_task_state_change(mid, evt))
        
        # Seed initial ready tasks
        for node in self.tracker.get_ready_tasks(mid):
            await self._ready_queue.put(node)
        
        active_workers: set[asyncio.Task] = set()
        
        while not self.tracker.all_done(mid):
            # Fill worker slots
            while len(active_workers) < self.config.max_concurrent_workers:
                try:
                    node = self._ready_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                if self._has_failed_dependency(mid, node):
                    self._cancel_downstream_tasks(mid, node.task_id)
                    continue
                
                task = asyncio.create_task(self._execute_task(mid, node))
                active_workers.add(task)
            
            if not active_workers:
                # Nothing running, wait for completion event
                if self.tracker.all_done(mid):
                    break
                await self._task_completed_event.wait()
                self._task_completed_event.clear()
                
                # Recompute ready tasks
                for node in self.tracker.get_ready_tasks(mid):
                    if node.state == TaskState.PENDING:
                        await self._ready_queue.put(node)
                continue
            
            # Wait for at least one worker to finish
            done, active_workers = await asyncio.wait(
                active_workers,
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            # Process completed tasks
            for task in done:
                try:
                    await task
                except Exception as e:
                    logger.exception("Task execution failed: %s", e)
            
            # Check for rework
            # ... existing rework logic ...
            
            # Enqueue newly ready tasks
            for node in self.tracker.get_ready_tasks(mid):
                if node.state == TaskState.PENDING:
                    await self._ready_queue.put(node)
        
        # ... existing summary logic ...
```

### 5.4 ProjectMemory 持久化

**变更**：ProjectMemory 支持 SQLite 持久化，与 MissionTracker 共享连接。

```python
# project_memory.py
class ProjectMemory:
    def __init__(self, project_path: str = "", db_path: str | None = None):
        self.project_path = project_path
        self.file_index: dict[str, FileSnapshot] = {}
        self.conventions: dict[str, str] = {}
        self.module_graph: dict[str, list[str]] = {}
        self.failed_attempts: list[FailedAttempt] = []
        self.architecture_notes: list[str] = []
        self.changed_files: list[str] = []
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self._db_path = db_path
        self._db_conn: sqlite3.Connection | None = None
        if db_path:
            self._init_db()
    
    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_conn = sqlite3.connect(self._db_path)
        self._db_conn.execute("PRAGMA journal_mode=WAL")
        self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS project_memory (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._db_conn.commit()
        self._load_from_db()
    
    def _persist(self) -> None:
        if not self._db_conn:
            return
        data = {
            "file_index": {k: v.to_dict() for k, v in self.file_index.items()},
            "conventions": self.conventions,
            "module_graph": self.module_graph,
            "failed_attempts": [f.to_dict() for f in self.failed_attempts],
            "architecture_notes": self.architecture_notes,
            "changed_files": self.changed_files,
        }
        self._db_conn.execute(
            "INSERT OR REPLACE INTO project_memory (key, data, updated_at) VALUES (?, ?, ?)",
            ("global", json.dumps(data), datetime.now(timezone.utc).isoformat()),
        )
        self._db_conn.commit()
    
    def record_file_read(self, path: str, content: str, summary: str = "") -> None:
        # ... existing logic ...
        self._persist()
```

### 5.5 依赖注入容器

**目标**：消除全局单例，使测试可 mock。

```python
# orchestration/container.py
from dataclasses import dataclass, field

@dataclass
class OrchestrationContainer:
    """DI container for orchestration components."""
    tracker: MissionTracker = field(default_factory=lambda: get_tracker())
    project_memory: ProjectMemory = field(default_factory=ProjectMemory)
    planner: MissionPlanner | None = None
    verifier_pipeline: VerificationPipeline | None = None
    rework_manager: ReworkManager | None = None
    reflector: Reflector = field(default_factory=Reflector)
    
    def __post_init__(self):
        if self.planner is None:
            self.planner = MissionPlanner()
        if self.verifier_pipeline is None:
            self.verifier_pipeline = VerificationPipeline()
        if self.rework_manager is None:
            self.rework_manager = ReworkManager(self.tracker)
```

**使用**：

```python
class MissionAdapter:
    def __init__(self, container: OrchestrationContainer | None = None, ...):
        self._container = container or OrchestrationContainer()
        self._orchestrator = Orchestrator(config=orch_config, container=self._container)
```

---

## 6. Phase 4：长期建设

### 6.1 单元测试覆盖

**优先测试模块**（按风险排序）：

| 模块 | 测试重点 | 预估用例数 |
|------|----------|------------|
| `dag.py` | 拓扑排序、循环检测、get_ready_tasks、关键路径 | 20 |
| `state_machine.py` | 所有有效/无效转换、历史记录、时间戳 | 15 |
| `tracker.py` | 注册、状态变更、快照、all_done | 15 |
| `orchestrator.py` | 执行循环、级联取消、智能重试 | 20 |
| `adapter.py` | 计划解析、Worker 执行、验证器 | 15 |
| `context_strategy.py` | 策略选择、计划调整 | 10 |
| `project_memory.py` | 文件索引、失效检测、持久化 | 10 |

**测试策略**：
- 使用 `AsyncMock` + `MagicMock(return_value=async_generator(...))` 模拟 LLM 调用
- 使用 `tmp_path` + monkeypatch 隔离 SQLite 数据库
- DAG 测试使用确定性任务图（线性、并行、菱形、循环）

### 6.2 任务优先级队列

**变更**：`BackgroundTaskQueue` 使用 `asyncio.PriorityQueue`。

```python
# services/task_queue.py
import heapq
from dataclasses import dataclass, field

@dataclass(order=True)
class PrioritizedTask:
    priority: int  # 数字越小优先级越高
    seq: int = field(compare=True)  # 打破平局的序列号
    task: Any = field(compare=False)

class PriorityTaskQueue:
    def __init__(self):
        self._queue: list[PrioritizedTask] = []
        self._seq = 0
        self._task_map: dict[str, Any] = {}
    
    def put(self, task_id: str, task: Any, priority: int = 5) -> None:
        self._seq += 1
        heapq.heappush(self._queue, PrioritizedTask(priority, self._seq, task))
        self._task_map[task_id] = task
    
    def get(self) -> Any:
        item = heapq.heappop(self._queue)
        del self._task_map[item.task.task_id]
        return item.task
```

**优先级规则**：
- P0 (Critical): 修复上游失败导致的阻塞任务
- P1 (High): 关键路径上的任务
- P2 (Normal): 默认
- P3 (Low): 探索性/可选任务

### 6.3 动态 DAG 修改

**场景**：Mission 执行中发现遗漏依赖，或 Reflector 触发重设计。

```python
# dag.py
class DagExecutor:
    def add_task(self, task: TaskSpec, dependencies: list[str]) -> None:
        """Runtime add task. Rebuilds topological order."""
        if task.id in self.nodes:
            raise ValueError(f"Task {task.id} already exists")
        self.nodes[task.id] = DagNode(task_id=task.id, task=task)
        for dep in dependencies:
            if dep not in self.nodes:
                raise ValueError(f"Unknown dependency: {dep}")
            self.edges.append(DagEdge(from_task=dep, to_task=task.id))
        self._built = False
        self.build()
    
    def remove_task(self, task_id: str) -> None:
        """Remove a task and its edges. Fails if dependents exist."""
        if task_id not in self.nodes:
            return
        dependents = self._adj_out.get(task_id, [])
        if any(self.nodes[d].state not in {TaskState.DONE, TaskState.CANCELLED} for d in dependents):
            raise ValueError(f"Cannot remove task {task_id}: has active dependents")
        del self.nodes[task_id]
        self.edges = [e for e in self.edges if e.from_task != task_id and e.to_task != task_id]
        self._built = False
        self.build()
```

### 6.4 可观测性增强

**指标收集**：

```python
# orchestration/telemetry.py
@dataclass
class MissionMetrics:
    mission_id: str
    started_at: datetime
    completed_at: datetime | None = None
    task_metrics: list[TaskMetric] = field(default_factory=list)
    total_tokens: int = 0
    total_rework_count: int = 0

@dataclass
class TaskMetric:
    task_id: str
    worker_type: str
    started_at: datetime
    completed_at: datetime
    token_usage: int
    turn_count: int
    verification_levels: list[int]
    success: bool
```

**OpenTelemetry 风格 trace**：

```python
# 在每个关键阶段打 span
with tracer.span("orchestrator.execute_task", task_id=task.id):
    result = await self._run_worker(task)
```

---

## 7. 风险与回滚策略

### 7.1 变更风险矩阵

| 变更 | 风险等级 | 回滚方案 |
|------|----------|----------|
| VerificationResult 统一 | 中 | 类型别名兼容层 |
| StateMachine 状态统一 | 高 | 保留旧 `update_task_state` 调用作为 fallback |
| 事件驱动调度 | 高 | 保留旧 `run()` 方法作为 `run_legacy()` |
| DAG 反向索引 | 低 | 算法等价，回滚到遍历 edges |
| adapter 拆分 | 中 | `__init__.py` 保留旧导入兼容 |
| ProjectMemory 持久化 | 低 | 默认 db_path=None，行为不变 |

### 7.2 兼容性保证

- 所有 public API（`MissionAdapter.run()`、`Orchestrator.run()`）的签名不变
- 内部重构通过 `__init__.py` 重新导出保持兼容
- 新增参数均有默认值

---

## 8. 验收标准

### Phase 1 完成标准
- [ ] `python -c "from pilotcode.orchestration import TaskDecomposer; TaskDecomposer()"` 成功
- [ ] `grep -r "class VerificationResult" src/pilotcode/orchestration/` 只剩 1 处
- [ ] `grep -rn "except Exception: pass" src/pilotcode/orchestration/` 返回 0 处
- [ ] 所有现有测试通过

### Phase 2 完成标准
- [ ] Reflector 接入主循环，每 30 秒健康检查一次
- [ ] 任务超时后自动 CANCEL 并级联取消下游
- [ ] L3 验证器使用 JSON 输出，fallback 到字符串匹配
- [ ] 停滞检测能识别超过 2 分钟无进展的任务
- [ ] adapter.py 行数 < 600（拆分出 planner/verifier/explorer）

### Phase 3 完成标准
- [ ] `get_ready_tasks()` 时间复杂度降至 O(V·avg_in_degree)
- [ ] StateMachine 和 DagNode 状态自动同步
- [ ] Orchestrator 主循环无 `asyncio.sleep()` 轮询
- [ ] ProjectMemory 支持 SQLite 持久化
- [ ] 全局单例可通过 DI 容器替换

### Phase 4 完成标准
- [ ] orchestration 模块测试覆盖率 > 70%
- [ ] BackgroundTaskQueue 支持优先级
- [ ] DagExecutor 支持运行时 add/remove task
- [ ] 每个 Mission 生成结构化 metrics 报告

---

## 附录 A：文件变更清单

### Phase 1
```
M src/pilotcode/orchestration/__init__.py          # 统一导出
M src/pilotcode/orchestration/orchestrator.py      # 删除 VerificationResult
M src/pilotcode/orchestration/verifier/base.py     # 确认唯一来源
A src/pilotcode/orchestration/decomposer.py        # 新增 TaskDecomposer
M src/pilotcode/orchestration/context/project_memory.py  # 兼容层
M src/pilotcode/orchestration/tracker.py           # 异常处理
M src/pilotcode/orchestration/orchestrator.py      # 异常处理
M src/pilotcode/orchestration/adapter.py           # 异常处理
```

### Phase 2
```
M src/pilotcode/orchestration/task_spec.py         # +timeout_seconds
M src/pilotcode/orchestration/orchestrator.py      # +超时控制
M src/pilotcode/orchestration/state_machine.py     # +时间戳
M src/pilotcode/orchestration/rework/reflector.py  # +停滞检测实现
M src/pilotcode/orchestration/adapter.py           # +Reflector hook
A src/pilotcode/orchestration/planners/__init__.py
A src/pilotcode/orchestration/planners/mission_planner.py
A src/pilotcode/orchestration/verifiers/adapter_verifiers.py
A src/pilotcode/orchestration/explorers/__init__.py
A src/pilotcode/orchestration/explorers/code_explorer.py
M src/pilotcode/orchestration/adapter.py           # 使用拆分出的模块
```

### Phase 3
```
M src/pilotcode/orchestration/dag.py               # +反向索引
M src/pilotcode/orchestration/state_machine.py     # +DagNode 绑定
M src/pilotcode/orchestration/tracker.py           # -冗余同步
M src/pilotcode/orchestration/orchestrator.py      # 事件驱动调度
M src/pilotcode/orchestration/project_memory.py    # +SQLite 持久化
A src/pilotcode/orchestration/container.py         # DI 容器
```

### Phase 4
```
A tests/unit/orchestration/test_dag.py
A tests/unit/orchestration/test_state_machine.py
A tests/unit/orchestration/test_tracker.py
A tests/unit/orchestration/test_orchestrator.py
M src/pilotcode/services/task_queue.py             # 优先级队列
M src/pilotcode/orchestration/dag.py               # 动态修改
A src/pilotcode/orchestration/telemetry.py         # 指标收集
```

---

*方案基于 `task_orchestration_analysis_report.md` 与代码实际状态综合设计。每阶段独立可交付，支持渐进式实施。*
