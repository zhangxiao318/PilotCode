# 任务编排功能缺点分析报告

> 基于 `src/pilotcode/orchestration/` (40 文件，8323 行)、示例、测试、文档的两轮全面审查
> 生成时间: 2026-05-02 | 第二轮深度审查: 2026-05-02

---

## 一、架构设计层面 (7 个问题)

### #1 🔴 致命 | `MissionAdapter` 上帝类 — SRP 严重违反

**文件:** `adapter.py` (1413 行)

一个类捆绑了 8 项职责：
- LLM 规划 (`_plan_mission`, ~200行)
- 代码库探索 (`_explore_codebase`)
- Worker Prompt 组装 (`_build_worker_prompt`)
- LLM Worker 循环 (`_llm_worker`)
- L1/L2/L3 验证器（三个 staticmethod）
- ProjectMemory 更新
- JSON 容错解析
- 权限回调设置

**后果:** 三个验证器是 static 方法，无法独立测试；新增验证级别必须改 MissionAdapter。

**修复:** 拆分为 `MissionPlanner` / `CodebaseExplorer` / `LlmWorker` / 独立 Verifier 类，引入构造函数依赖注入。

**状态:** ⬜ 未修复

---

### #2 🔴 致命 | 全局可变单例 — DIP 违反

**文件:** `tracker.py:322`, `smart_coordinator.py:55`(已删除), `auto_config.py:35`

```python
# tracker.py
_tracker: MissionTracker | None = None  # + get_tracker(), reset_tracker()

# auto_config.py
_auto_config = AutoDecompositionConfig()  # 模块加载时即实例化
```

**后果:** `pytest-xdist` 并行测试必然 flaky；任何模块都能隐式获得全局依赖。

**修复:** 移除 `get_tracker()`, `reset_tracker()`，全链路构造函数注入。

**状态:** 🟡 部分修复 — #21 已删除 `smart_coordinator` 单例，`tracker` 和 `auto_config` 仍待处理

---

### #3 🔴 高 | 基础设施具体依赖 — DIP 违反

**文件:** `adapter.py`

```python
from pilotcode.utils.model_client import get_model_client, Message
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_core_tools
from pilotcode.permissions.permission_manager import get_permission_manager
```

**后果:** 写 `_plan_mission` 单测需 mock 跨越 5+ 条模块路径。

**修复:** 构造函数注入。

**状态:** ⬜ 未修复

---

### #4 🔴 高 | Worker/Verifier 选择逻辑重复 — DRY 违反

**文件:** `orchestrator.py:370`, `context_strategy.py:336`

两处各自实现完全相同的 `ComplexityLevel → worker_type` 映射。新增 worker 类型必须改两处。

**修复:** 提取到单一 `WorkerSelector` 模块。

**状态:** ⬜ 未修复

---

### #5 🟡 中 | `Orchestrator` 混合调度、验证、重试 — SRP 违反

**文件:** `orchestrator.py` (880 行)

一个类包含：DAG 事件循环、级联失败检测、智能重试（`_analyze_failure` 用手写 `if/elif` 关键词匹配）、验证管道、Worker 分发。

**修复:** 提取 `VerificationPipeline` + `RetryPolicy` + `CascadeFailureHandler`。

**状态:** ⬜ 未修复

---

### #6 🟡 中 | 魔术整数的验证器注册 — OCP 违反

**文件:** `orchestrator.py`, `context_strategy.py`, `adapter.py`

```python
self._verifier_registry: dict[int, Callable[...]] = {}
orch.register_verifier(1, ...)  # L1
orch.register_verifier(2, ...)  # L2
orch.register_verifier(3, ...)  # L3
```

新增"安全扫描"级别需同时改 4 个文件的布尔字段 + if-block。

**修复:** 提取 `VerificationLevel` 枚举 + `VerificationPipeline`。

**状态:** ⬜ 未修复

---

### #7 🟡 中 | Phase 级依赖形同虚设

**文件:** `dag.py`, `context_strategy.py`

`Phase` 定义了 `dependencies` 字段表示 phase 间依赖，但 `DagExecutor.build()` 只在 `TaskSpec.dependencies` 级别构建 DAG。Phase 级依赖被静默丢弃。

**修复:** 消费 Phase.dependencies，或移除该字段。

**状态:** ⬜ 未修复

---

## 二、实现细节层面 (8 个问题)

### #8 🟡 中 | ReworkContext 定义但基本未使用

**文件:** `rework/rework_context.py`, `orchestrator.py`

`ReworkContext` 定义了 `preserve`、`must_change`、`lessons_learned`、`ReworkSeverity`、`ReworkAttempt`，但 `Orchestrator._smart_retry()` 完全不用它——通过直接拼接字符串到 `adjusted_task.objective`。

**修复:** 在 `_smart_retry` 中真正使用 ReworkContext。

**状态:** ⬜ 未修复

---

### #9 🟡 中 | `_analyze_failure` 的脆弱关键词分类器

**文件:** `orchestrator.py`

```python
if "file not found" in combined or "no such file" in combined:
    ...
elif "permission" in combined or "access denied" in combined:
    ...
elif "syntax" in combined or "indent" in combined or "unexpected" in combined:
    ...
```

非英语错误信息被归类为 `unknown`；未利用已有的 `VerificationResult.feedback` 结构化信息。

**修复:** 使用 LLM 分类或结构化错误匹配。

**状态:** ⬜ 未修复

---

### #10 🟡 中 | `_smart_retry` 的状态机绕过

**文件:** `orchestrator.py`

```python
sm.state = TaskState.PENDING  # 暴力回置，绕过合法 Transition
```

跳过了 `NEEDS_REWORK → RESUME → IN_PROGRESS` 路径，状态变更历史不完整。

**修复:** 使用合法的状态机 Transition。

**状态:** ⬜ 未修复

---

### #11 🟡 中 | 代码文件扩展名硬编码在两处

**文件:** `orchestrator.py:430`, `adapter.py:200`

两份相同的 `_code_exts` 元组。新增语言支持需两处同步。

**修复:** 提取到共享模块。

**状态:** ⬜ 未修复

---

### #12 🟡 中 | Plan Prompt 异常庞大且内嵌 JSON Schema

**文件:** `adapter.py` (`_plan_mission`)

system prompt 超过 65 行，内嵌 JSON Schema 和 "CRITICAL RULES"。消耗宝贵的 context budget。

**修复:** Schema 与指令分离，按需注入。

**状态:** ⬜ 未修复

---

### #13 🔴 高 | 缺少任务级取消传播

**文件:** `orchestrator.py`, `adapter.py`

`Orchestrator.run()` 中接收了 `cancel_event` 但主循环 `while not self.tracker.all_done(mid)` 内没有检查。一旦进入执行阶段，外部取消信号不会终止正在运行的 worker。

**修复:** 在 DAG 主循环中周期性检查 cancel_event。

**状态:** ⬜ 未修复

---

### #14 🟡 中 | Health Check 仅记录不干预

**文件:** `orchestrator.py` (Reflector)

`Reflector` 检测到 risk 时只发 `mission:health_warning` 通知，`should_trigger_redesign()` 搭配 `mission:redesign_triggered` 事件，但没有代码监听并触发重新规划。

**修复:** 添加实际的 redesign 触发逻辑。

**状态:** ⬜ 未修复

---

### #15 🟡 中 | Serialization 缺乏版本控制

**文件:** `tracker.py`

`Mission.to_dict()` / `Mission.from_dict()` 没有 schema 版本字段。旧持久化数据会静默解析失败。

**修复:** 添加 `schema_version` 字段 + 迁移逻辑。

**状态:** ⬜ 未修复

---

## 三、测试与质量层面 (3 个问题)

### #16 🔴 高 | 核心路径几乎不可单测

**文件:** `tests/test_orchestration.py` (1106 行)

P-EVR 最关键的三步（Plan、Execute 的 LLM 循环、L3 Review）完全依赖集成测试/E2E。现有单测只覆盖无 LLM 的纯逻辑单元。

**修复:** 引入 `ILlmClient` 接口，用 mock 覆盖核心路径。

**状态:** ⬜ 未修复

---

### #17 🟡 中 | 示例代码的代码坏味 (12 个已记录)

**文件:** `examples/orchestration/` 四个 demo 文件 (892 行)

12 个 code smells：4 个硬编码值、3 个错误处理缺失、2 个 God Function、2 个紧耦合、1 个重复代码。

**修复:** 重构示例代码，提取共享 mock。

**状态:** 🟡 部分修复 — #21 已更新两个 demo 文件

---

### #18 🔴 高 | 测试中的 `reset_tracker()` 补丁

**文件:** `tests/test_orchestration.py`

```python
@pytest.fixture
def tracker():
    t = MissionTracker()
    yield t
    from pilotcode.orchestration.tracker import reset_tracker
    reset_tracker()
```

忘记调用 `reset_tracker()` 的测试会污染后续测试。

**修复:** 消除全局单例（同 #2），用构造函数注入。

**状态:** ⬜ 未修复

---

## 四、第二轮深度审查 — 新发现问题 (11 个问题)

> 第二轮审查覆盖了第一轮未深入分析的 24 个文件（`adaptive_edit.py`, `coordinator.py`, `decomposer.py`, `integration.py`, `report.py`, `results.py`, `state_machine.py`, `task_spec.py`, `telemetry.py`, `verifier/`, `verifiers/`, `workers/` 等），发现以下新增问题。

---

### #24 🔴 致命 | `verifier/` 与 `verifiers/` 两套验证器目录并存且职责重叠

**文件:** `verifier/` (4 文件, 570 行) vs `verifiers/` (2 文件, 400 行)

两套完全独立的验证器实现：

| 目录 | 风格 | L1 | L2 | L3 |
|------|------|-----|-----|-----|
| `verifier/` | OOP (继承 `BaseVerifier`) | `StaticAnalysisVerifier` | `TestRunnerVerifier` (693行) | `CodeReviewVerifier` |
| `verifiers/` | 函数式 (async function) | `l1_simple_verifier` | `l2_test_verifier` | `l3_code_review_verifier` + `simplified_l3_verifier` + `static_analysis_l3_verifier` |

**更糟的是:** `adapter.py` 混用两套：
```python
from .verifiers.adapter_verifiers import l1_simple_verifier, l3_code_review_verifier  # verifiers/
from .verifier.level2_tests import TestRunnerVerifier  # verifier/
```
L1 和 L3 来自 `verifiers/`，但 L2 来自 `verifier/`。L2 和 L3 各有 2-3 个并行实现，无人知道哪个是权威版本。

**后果:** 新增验证逻辑时不知道该加到哪个目录；两个 L2 实现行为可能不一致。

**修复:** 选择一套（推荐 `verifier/` 的 OOP 风格），删除另一套，统一导入。

**状态:** ⬜ 未修复

---

### #25 🔴 致命 | 所有 4 个 Worker 类都是占位符 — 从未真正调用 LLM

**文件:** `workers/simple_worker.py`, `workers/standard_worker.py`, `workers/complex_worker.py`, `workers/debug_worker.py`

```python
class SimpleWorker(BaseWorker):
    async def execute(self, task, context):
        prompt = self._build_prompt(task, context)
        # Simulate execution
        # In production: call LLM with prompt, parse structured output
        outputs = {path: f"# Generated by SimpleWorker for {task.id}\n" for path in task.outputs}
        return ExecutionResult(task_id=task.id, success=True, output=..., artifacts=outputs)
```

4 个 Worker 全部只构建 prompt 并返回伪造的 `ExecutionResult`。**真正的 LLM 执行发生在 `MissionAdapter._llm_worker()` (320行)**，完全绕过了 Worker 抽象。

**后果:** Worker 注册机制 (`Orchestrator._worker_registry`) 是死代码；复杂度分层 (simple/standard/complex/debug) 名存实亡——所有任务都走同一个 `_llm_worker()`。

**修复:** 将 `_llm_worker` 逻辑注入到 Worker 子类中，或删除 Worker 抽象层让 adapter 直接调用 LLM。

**状态:** ⬜ 未修复

---

### #26 🔴 高 | `coordinator.py` 的 `AgentCoordinator` 和 `TaskExecutor` 是纯存根

**文件:** `coordinator.py` (111 行)

```python
class AgentCoordinator:
    async def execute(self, task, auto_decompose=False, strategy=None):
        await asyncio.sleep(0.01)  # Tiny delay for demo
        return CoordinatorResult(status="completed", summary=f"Executed: {task[:60]}...")
```

两个类用 `asyncio.sleep(0.01)` 模拟执行并返回虚构结果。注释称"backward-compatible wrapper"，但任何意外使用此类的代码路径都会静默产生虚假成功。

**修复:** 删除 `coordinator.py`，让示例代码直接使用 `MissionAdapter`。

**状态:** ⬜ 未修复

---

### #27 🟡 中 | `adapter.py` 方法内延迟导入 — 循环依赖症状

**文件:** `adapter.py:89`, `adapter.py:173`, `adapter.py:177`

```python
# 在 __init__ 里
from pilotcode.utils.config import get_global_config

# 在 _select_verifier 方法里
from .verifiers.adaptive_verifiers import simplified_l3_verifier
from .verifiers.adaptive_verifiers import static_analysis_l3_verifier
```

5+ 处 import 埋在方法体内以规避循环导入。这是模块边界设计不良的经典症状。

**修复:** 随 #1 拆分 MissionAdapter 后自然消失。

**状态:** ⬜ 未修复（依赖 #1）

---

### #28 🟡 中 | `verifier/level2_tests.py` (693行) — 验证器层的上帝类

**文件:** `verifier/level2_tests.py`

单个 `TestRunnerVerifier` 类包含：6 语言支持 (Python/C/C++/Rust/Go/JS)、临时目录管理、pytest/coverage 集成、项目构建验证、测试发现。693 行全在一个文件。

**修复:** 按语言拆分为独立 test runner 模块。

**状态:** ⬜ 未修复

---

### #29 🟡 中 | `report.py` 与 `telemetry.py` 完全未集成

**文件:** `report.py` (237 行), `telemetry.py` (64 行)

- `report.py` 提供 6 个 `format_*()` 函数生成人类可读字符串
- `telemetry.py` 定义了结构化的 `TaskMetric` / `MissionMetrics` 数据类
- 两个模块互不引用：格式化报告从不包含结构化指标，telemetry 数据从未被持久化或渲染

**修复:** 让 `format_*()` 消费 `MissionMetrics`，或合并为一个 `reporting` 子包。

**状态:** ⬜ 未修复

---

### #30 🟡 中 | `decomposer.py` 的启发式分解器生产环境不可用

**文件:** `decomposer.py` (204 行)

`TaskDecomposer` 基于关键词匹配（"and"/"then"/"refactor"/"fix"）分解任务，置信度 0.6-0.9 但实际策略粗糙。文档自称 "lightweight implementation" 和 "full LLM-driven decomposer can be added later"——但从未被集成到真正的 LLM 规划流程中。

**修复:** 集成 LLM 驱动的分解器或删除此模块。

**状态:** ⬜ 未修复

---

### #31 🟡 中 | `state_machine.py` 定义完善但 `orchestrator.py` 中仍有暴力绕过

**文件:** `state_machine.py` (225 行), `orchestrator.py` (多处)

`StateMachine` 实现了完整的 Transition Table (19 个转换)、`StateChangeEvent` 历史、回调机制。但 #10 已记录 `orchestrator._smart_retry()` 通过 `sm.state = TaskState.PENDING` 暴力绕过 Transition。此外：

- `orchestrator.py` 中有 7 处直接设置 `.state` 而非通过 `.transition()`
- `StateMachine.is_terminal()` 返回 `True` 对于 REJECTED，但 REJECTED 可以 transition 到 NEEDS_REWORK

**修复:** 全面审查 `orchestrator.py` 中所有 `.state =` 赋值，改用 `.transition()`。

**状态:** ⬜ 未修复（关联 #10）

---

### #32 🟡 中 | `auto_config.py` 全局单例仍待消除

**文件:** `auto_config.py:35`

```python
_auto_config = AutoDecompositionConfig()  # 模块加载时实例化
```

以及配套的 4 个全局函数 (`get_auto_config()`, `configure_auto_decomposition()`, `enable_auto_decomposition()`, `disable_auto_decomposition()`)。这是 #2 中提到的两个全局单例之一，仍未修复。

**修复:** 移除全局实例，改为构造函数注入。

**状态:** ⬜ 未修复（关联 #2）

---

### #33 🟡 中 | `context/project_memory.py` 与根级 `project_memory.py` 并存

**文件:** `project_memory.py` (435 行), `context/project_memory.py` (38 行)

这是 #23 的具体化：根级 `project_memory.py` 是 dataclass-based (435 行)，`context/project_memory.py` 持久化到 `.pilotcode/project_memory.json` (38 行)。根级有 `update_from_discovery()` 方法，context 级有 `get_project_memory()` 向后兼容函数——两套 API。

**修复:** 统一为单一 `ProjectMemory` 实现。

**状态:** ⬜ 未修复（关联 #23）

---

### #34 🟡 中 | `adaptive_edit.py` 的 `EditValidator.validate()` 包含副作用（自动修复文件）

**文件:** `adaptive_edit.py:84-106`

```python
# Try auto-fix
source = path.read_text(...)
fixed_source = lib.apply_auto_fixes(source, file_matches)
if fixed_source != source:
    path.write_text(fixed_source, ...)  # 副作用！静默修改文件
```

名为 "validate" 的方法实际上会静默修改源文件（Knowhow auto-fix）。调用者无法预知验证会产生副作用。

**修复:** 将 `validate()` 拆分为纯检查 + 显式 `auto_fix()`。

**状态:** ⬜ 未修复

---

## 五、工程化与体验层面 (5 个问题)

### #19 🟡 中 | 模块职责文档与实际代码脱节

**文件:** `CORE_ABSTRACTIONS.md`, `ARCHITECTURAL_COMPLIANCE.md`

文档描述的理想架构与实现现状有显著偏差（如 ReworkContext 在文档中存在但代码中基本不用）。

**修复:** 同步文档或同步代码。

**状态:** ⬜ 未修复

---

### #20 🟡 中 | 过度的复杂度层级

`VERY_COMPLEX` 和 `COMPLEX` 映射到同一个 worker，5 个级别→3 种 worker，增加了概念负担。

**修复:** 压缩复杂度层级，或让每个级别有实际差异。

**状态:** ⬜ 未修复

---

### #21 ✅ 已修复 | `SmartCoordinator` 是薄的包装器

**文件:** `smart_coordinator.py` (已删除)

67 行纯透传层，`src/` 中零调用方。已消除，逻辑内聚到 `MissionAdapter._should_explore_and_plan()`。

**状态:** ✅ 已修复

---

### #22 🟡 中 | 缺少任务执行的幂等性保证

`VERIFIED` 状态假设永久有效，无机制标记任务需重新执行。

**修复:** 添加 `STALE` 状态或 `force_reverify` 标记。

**状态:** ⬜ 未修复

---

### #23 🟡 中 | 两层 Memory 系统并存且概念重叠

- `src/pilotcode/orchestration/project_memory.py` — dataclass-based
- `src/pilotcode/orchestration/context/project_memory.py` — 持久化到 `.pilotcode/project_memory.json`

两套概念相近但字段不完全一致。

**修复:** 统一为一套 Memory 系统。

**状态:** ⬜ 未修复

---

## 修复汇总统计

| 层次 | 总数 | 致命 | 高 | 中 | 已修复 |
|------|------|------|-----|-----|--------|
| 架构设计 (第一轮) | 7 | 2 | 2 | 3 | 0.5 (#2 部分) |
| 实现细节 (第一轮) | 8 | 0 | 1 | 7 | 0 |
| 测试质量 (第一轮) | 3 | 0 | 2 | 1 | 0 |
| 第二轮深度审查 | 11 | 2 | 1 | 8 | 0 |
| 工程化 | 5 | 0 | 0 | 5 | 1 |
| **合计** | **34** | **4** | **6** | **24** | **1.5** |

---

## 建议修复顺序

### 第一阶段（架构重构，1-2 周）
1. 拆分 `MissionAdapter` → `MissionPlanner` + `CodebaseExplorer` + `LlmWorker` + Verifier (#1)
2. 消除全局单例：`tracker`、`auto_config` 改为构造函数注入 (#2, #18, #32)
3. 提取 `ILlmClient` 接口，使核心路径可单测 (#3, #16)
4. 合并 `verifier/` 与 `verifiers/` 目录，消除重复的 L2/L3 实现 (#24)
5. 将 `_llm_worker` 逻辑迁移到 Worker 子类，或删除 Worker 抽象层 (#25)

### 第二阶段（质量加固，1 周）
6. 提取 `VerificationPipeline` + `RetryPolicy` + `CascadeFailureHandler` (#5, #6)
7. 统一 Worker 选择逻辑 (#4)
8. 真正的 ReworkContext 使用 + 合法状态机 Transition (#8, #10, #31)
9. 删除 `coordinator.py` 存根 (#26)
10. 拆分 `verifier/level2_tests.py` (#28)

### 第三阶段（完善，1 周）
11. 取消传播 (#13)、Heath Check 干预 (#14)、幂等性 (#22)
12. 统一 Memory 层 (#23, #33)、Serialization 版本控制 (#15)
13. 集成 `report.py` 与 `telemetry.py` (#29)
14. 重构 `EditValidator.validate()` 消除副作用 (#34)
15. 重构示例代码、同步文档 (#17, #19)

---

> 本文件记录的是分析时点（2026-05-02）的全量问题清单。
> 继续处理时，优先从标记为 ⬜ 的未修复项开始。
