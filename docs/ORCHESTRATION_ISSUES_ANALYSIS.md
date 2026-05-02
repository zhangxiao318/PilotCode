# 任务编排功能缺点分析报告

> 基于 `src/pilotcode/orchestration/` (16 模块，~3500 行)、示例、测试、文档的全面审查
> 生成时间: 2026-05-02

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

## 四、工程化与体验层面 (5 个问题)

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
| 架构设计 | 7 | 2 | 2 | 3 | 0.5 (#2 部分) |
| 实现细节 | 8 | 0 | 1 | 7 | 0 |
| 测试质量 | 3 | 0 | 2 | 1 | 0 |
| 工程化 | 5 | 0 | 0 | 5 | 1 |
| **合计** | **23** | **2** | **5** | **16** | **1.5** |

---

## 建议修复顺序

### 第一阶段（架构重构，1-2 周）
1. 拆分 `MissionAdapter` → `MissionPlanner` + `CodebaseExplorer` + `LlmWorker` + Verifier (#1)
2. 消除全局单例：`tracker`、`auto_config` 改为构造函数注入 (#2, #18)
3. 提取 `ILlmClient` 接口，使核心路径可单测 (#3, #16)

### 第二阶段（质量加固，1 周）
4. 提取 `VerificationPipeline` + `RetryPolicy` + `CascadeFailureHandler` (#5, #6)
5. 统一 Worker 选择逻辑 (#4)
6. 真正的 ReworkContext 使用 + 合法状态机 Transition (#8, #10)

### 第三阶段（完善，1 周）
7. 取消传播 (#13)、Heath Check 干预 (#14)、幂等性 (#22)
8. 统一 Memory 层 (#23)、Serialization 版本控制 (#15)
9. 重构示例代码、同步文档 (#17, #19)

---

> 本文件记录的是分析时点（2026-05-02）的全量问题清单。
> 继续处理时，优先从标记为 ⬜ 的未修复项开始。
