# Functional Patterns Analysis — Orchestration Across the Codebase

> Synthesizes Phase 1 analyses: root-level tools, orchestration demos, and complex schedulers.
> Cross-referenced with live source in `src/pilotcode/orchestration/`.

---

## 1. Task Decomposition Models

### 1.1 Comparison

| Layer | Model | Granularity | Who Decomposes | Discovery |
|-------|-------|-------------|----------------|-----------|
| **Root-level** (`task_dependency_analysis.py`) | Static task dicts `{id, depends_on}` | Coarse (5-task pipeline) | Manual / external | NetworkX graph after-the-fact |
| **Demos** (`examples/orchestration/`) | `DecompositionStrategy` enum (NONE, SEQUENTIAL, PARALLEL, HIERARCHICAL) | Medium — role-assigned subtasks with complexity stars | `TaskDecomposer.analyze()` + `.auto_decompose()` (LLM-backed) | Heuristic keyword matching + LLM |
| **Schedulers** (`complex_scheduler/`) | `v1`: Class hierarchy (`ScheduledTask`, `ChainedTask`, `ParallelTask`). `v2`: `TaskDefinition` (frozen) → `TaskInstance` (mutable) | Fine — per-handler callable | External — user calls `scheduler.submit()` | None — expects pre-decomposed input |
| **Core** (`src/pilotcode/orchestration/`) | P-EVR three-layer: `Mission → Phase → TaskSpec` with `ComplexityLevel` (1–5) | Fine — individual `TaskSpec` with acceptance criteria, constraints, context budget | `MissionAdapter._plan_mission()` — LLM generates JSON plan from user request | `MissionAdapter._explore_codebase()` — glob + top-level file read |

### 1.2 Key Differences

- **Root-level is offline analysis.** It consumes pre-decomposed task lists and produces diagnostics; no decomposition engine.
- **Demos define a forward-looking API contract** (`TaskDecomposer`, `AgentCoordinator`, `DecompositionStrategy`) but these classes do **not** exist in the source `__init__.py`. The demos are aspirational.
- **Schedulers are executor-oriented.** `v1` conflates task definition with handler callables in dataclasses (serialization-hostile). `v2` cleanly separates `TaskDefinition` (frozen blueprint) from `TaskInstance` (runtime state) via Pydantic.
- **Core is the real engine.** LLM-driven decomposition via `MissionAdapter`, backed by `auto_config.py` for global toggles. The `SmartCoordinator` bridges the demo API to `MissionAdapter`.

### 1.3 Effectiveness

| Concern | Rating | Notes |
|---------|--------|-------|
| **Granularity control** | ★★★★☆ | Core's `ComplexityLevel` + `context_budget` per task is strong. Scheduler's per-handler model is flexible but manual. |
| **LLM integration** | ★★★★☆ | Core's `_plan_mission()` prompts are structured and inject codebase exploration context. Good. |
| **Heuristic decision** | ★★★☆☆ | `should_auto_decompose()` is a simple length+score check. The demos' `analyze()` pattern promises richer heuristics but is unimplemented. |
| **Schema consistency** | ★★★★☆ | Core uses `TaskSpec`/`Mission` dataclasses with `to_dict()`/`from_dict()`. v2 scheduler uses Pydantic with validation. All serializable. v1 scheduler is the exception — callables in dataclasses. |

---

## 2. Dependency Resolution Approaches

### 2.1 Comparison

| Layer | Algorithm | Data Structure | Cycle Detection | Missing-Dep Detection |
|-------|-----------|----------------|-----------------|----------------------|
| **Root-level** (`task_dependency_analysis.py`) | Kahn's Algorithm (NetworkX `topological_sort`) | `nx.DiGraph` | ✅ `nx.simple_cycles` | ✅ `undefined_dependency` defects |
| **Demos** | Implicit — `result.subtasks[i].dependencies` is a list of task IDs | Flat `list[str]` per subtask | ❌ | ❌ |
| **Schedulers v1** | Bidirectional `dependencies`/`dependents` on `Task` dataclass | Python lists on dataclass | ❌ | ❌ |
| **Schedulers v2** | `dependencies: list[str]` validated at parse time | Pydantic field with validation | ❌ | ✅ (Pydantic validation) |
| **Core** (`dag.py`) | Kahn's Algorithm with depth calculation | `DagExecutor` with `_in_degree`, `_outgoing` dicts | ✅ `ValueError` with cycle members | ✅ `ValueError` for unknown deps |

### 2.2 Key Differences

- **Root-level and Core use the same algorithm** (Kahn's), but root-level uses NetworkX (heavy dependency) while Core is a hand-rolled implementation (~100 lines) with no external graph library. Core's implementation is leaner and more appropriate for a runtime engine.
- **Core adds depth tracking and wave grouping** — `get_execution_path()` returns `list[list[str]]` grouping tasks by topological depth for parallel wave execution. Root-level only produces a flat topological order.
- **Core adds cascade failure handling** — `_has_failed_dependency()` + `_cancel_downstream_tasks()` recursively cancels tasks that depend on failed upstream tasks. This is absent from all other layers.
- **Demos lack dependency resolution entirely** — the `dependencies` field exists in the data model but no resolution logic is evident.
- **Scheduler v2 validates at parse time** via Pydantic, which catches missing references early but does not do runtime cycle detection.

### 2.3 Effectiveness

| Concern | Rating | Notes |
|---------|--------|-------|
| **Cycle detection** | ★★★★☆ | Core and root-level both detect cycles. Core raises `ValueError` with cycle-member set. |
| **Runtime cascade handling** | ★★★★★ | Core is unique: auto-cancels downstream on upstream failure. Critical for real-world robustness. |
| **Critical path** | ★★★★☆ | Core's `get_critical_path()` enables bottleneck identification. Unique across entire codebase. |
| **Missing-dep detection** | ★★★☆☆ | Core and root-level detect undefined deps at DAG build time. Demos and schedulers do not. |
| **Reusability** | ★★★☆☆ | Core's `DagExecutor` takes any `Mission`; root-level's `TaskDependencyAnalyzer` takes any `list[dict]`. Both reusable. But they are not shared — root-level is standalone. |

---

## 3. Execution Ordering

### 3.1 Comparison

| Layer | Execution Model | Concurrency | Scheduling | Re-execution |
|-------|-----------------|-------------|------------|--------------|
| **Root-level** | Static topological order only | None | N/A | N/A |
| **Demos** | `AgentCoordinator.execute(task, auto_decompose=True)` — delegate to core | Via coordinator (async gather) | Callback-driven (`on_progress`) | Implicit via "Bug Fix" manual loop |
| **Schedulers v1** | Polling `_scheduler_loop` at 1s intervals | Fixed `WorkerPool` size | Priority heap (`heapq`) + delay deque | Exponential backoff with blocking sleep |
| **Schedulers v2** | Event-driven with `asyncio.PriorityQueue` | Auto-scaling `WorkerPool` | Dual-heap: priority queue + delayed heap | Exponential backoff with `asyncio.sleep` |
| **Core** | `asyncio.Semaphore`-bounded concurrent execution | Configurable `max_concurrent_workers` (default 3) | DAG readiness polling at 0.5s; wave parallelism via depth groups | Smart retry with failure analysis + task adjustment |

### 3.2 Key Differences

- **Event-driven vs. Polling:** Core polls at 0.5s (checking `tracker.get_ready_tasks()`), which is acceptable for development-scale missions. Scheduler v2 uses `asyncio.PriorityQueue` with native async notification — better for high-throughput.
- **Wave parallelism:** Core's `get_execution_path()` returns tasks grouped by depth; each wave can run fully parallel. Schedulers lack wave awareness — they process from a flat priority queue.
- **Smart retry:** Core's `_smart_retry()` analyzes failure text (keyword matching on error strings), adjusts the task (reduces max_lines for syntax errors, adds must_use for missing files), and re-executes. Schedulers do naive exponential backoff only. Demos have no retry logic.
- **Graceful shutdown:** Core's `cancel_mission()` and `cancel_downstream_tasks()` provide clean cancellation. Scheduler v2 has `stop()` with `asyncio.gather(return_exceptions=True)`. Scheduler v1 cancels without awaiting in-progress work.

### 3.3 Effectiveness

| Concern | Rating | Notes |
|---------|--------|-------|
| **Concurrency control** | ★★★★☆ | Core's `Semaphore` is simple and effective. Scheduler v2's `PriorityQueue` is more sophisticated. |
| **Wave-aware parallelism** | ★★★★★ | Core's `get_execution_path()` is unique and enables optimal parallel scheduling. |
| **Retry intelligence** | ★★★★☆ | Core's failure analysis + task adjustment is more advanced than scheduler's blind backoff. But keyword-matching is brittle. |
| **Graceful shutdown** | ★★★★☆ | Core and scheduler v2 both handle it; Core also propagates cancellation through dependency chains. |
| **Progress observability** | ★★★★☆ | Core's `on_progress` callbacks + `MissionSnapshot` provide structured state. Scheduler v2's `MetricsCollector` adds percentile tracking. |

---

## 4. Overall Orchestration Patterns

### 4.1 Pattern Catalogue

```
┌──────────────────────────────────────────────────────────────────────┐
│  PATTERN                   WHERE USED          MATURITY              │
├──────────────────────────────────────────────────────────────────────┤
│  Analyze-then-Decide       Demos, SmartCoord   ★★★ (config-driven)   │
│  Explore-then-Plan         Core (MissionAdapter) ★★★★★ (LLM+filesys) │
│  Plan-Execute-Verify-      Core (Orchestrator) ★★★★★ (full P-EVR)    │
│  Reflect                                                             │
│  DAG-based Dependency       Core (DagExecutor),  ★★★★ (Kahn's)       │
│  Resolution                 Root (NetworkX)                          │
│  Wave-based Parallelism     Core (DagExecutor)  ★★★★ (depth groups)  │
│  Cascade Failure Handling   Core (Orchestrator) ★★★★ (recursive)     │
│  Smart Retry with Analysis  Core (Orchestrator) ★★★ (keyword-match)  │
│  Preview-before-Execute     Demos (SmartCoord)  ★★ (unimplemented)   │
│  Dual-Heap Scheduling       Scheduler v2        ★★★★★ (prod-ready)   │
│  Auto-Scaling Workers       Scheduler v2        ★★★★★ (fill-ratio)   │
│  Pluggable State Backend    Scheduler v2, Core  ★★★★ (ABC pattern)   │
│  Global Config Toggle       Demos, Core         ★★★ (auto_config.py) │
│  Progress Callbacks         Core, Demos         ★★★★ (event-driven)  │
│  Error Graph Tracing        Root-level          ★★ (standalone tool) │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Reuse Analysis

| Shared Concept | Reused? | Details |
|----------------|---------|---------|
| **DAG + topological sort** | Partially | Core hand-rolls Kahn's; Root uses NetworkX. Same algorithm, different implementations — no code sharing. |
| **Task state machine** | Yes | Core's `StateMachine` with 11 states is used by `Orchestrator`, `Tracker`, and `DagExecutor`. |
| **Worker abstraction** | Yes | Core has `_worker_registry` dict (callable injection). Scheduler v2 has `TaskRegistry` singleton. Same pattern, different APIs. |
| **Observer/callback pattern** | Yes | Core's `on_progress()` + `_event_callbacks` in Tracker. Demos' `coordinator.on_progress()`. Scheduler v2's `MetricsCollector.add_callback()`. |
| **Dependency injection** | Yes | Scheduler v2 constructor-injects config, backend, registry. Core injects worker/verifier callables. |
| **Serialization** | Partial | Core's dataclasses have `to_dict()`/`from_dict()`. Scheduler v2 uses Pydantic. Root-level uses plain dicts. No unified serialization format. |
| **TaskDecomposer / AgentCoordinator** | No | Referenced by demos but not implemented. `SmartCoordinator` + `MissionAdapter` fill the gap but under a different API. |

### 4.3 Scalability Assessment

| Dimension | Root-level | Demos | Scheduler v1 | Scheduler v2 | Core |
|-----------|-----------|-------|-------------|-------------|------|
| **Task volume** | ~100s (static) | ~100s | ~1000s (memory-bound) | ~10K+ (indexed, pluggable DB) | ~1000s (SQLite, in-memory DAG) |
| **Concurrent workers** | 1 | N/A | Fixed | Auto-scale | Configurable (default 3) |
| **State persistence** | None | None | Memory-only | Pluggable ABC | SQLite via Tracker |
| **Memory efficiency** | Good | N/A | Poor (unbounded history) | Good (circular buffers, cleanup) | Good (SQLite WAL, cleanup loop) |
| **Observability** | Print | Rich console | `print()` | Percentiles + callbacks | Events + snapshots |

### 4.4 Flexibility Assessment

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Pluggable workers** | ★★★★★ | Core's `register_worker()` + Scheduler v2's `TaskRegistry` — both support arbitrary handlers |
| **Pluggable verifiers** | ★★★★☆ | Core's L1/L2/L3 verifier registry (3 levels). Scheduler has no verification layer. |
| **Pluggable state backend** | ★★★★☆ | Scheduler v2's `StateBackend` ABC. Core uses SQLite directly (less flexible). |
| **Strategy selection** | ★★★☆☆ | Core has `ContextStrategySelector` (3 strategies). Demos have `DecompositionStrategy` enum (4 strategies). But strategy-to-execution mapping is hard-coded. |
| **Cross-layer integration** | ★★☆☆☆ | Root-level analysis tools are not wired into Core. Demos import non-existent classes. Scheduler is a separate codebase. Three separate ecosystems. |

---

## 5. Critical Gaps & Recommendations

### 5.1 Missing Bridge: Demos ↔ Core

The demos import `TaskDecomposer`, `AgentCoordinator`, and `DecompositionStrategy` from `pilotcode.orchestration`, but these do not exist.

**Recommendation:** Either (a) implement these as thin wrappers around `MissionAdapter`/`Orchestrator` (similar to `SmartCoordinator`), or (b) update the demos to use `SmartCoordinator`/`MissionAdapter` directly.

### 5.2 Root-level Analysis Tools Are Orphaned

`task_dependency_analysis.py`, `error_tracing_analysis.py`, and `exception_analysis.py` implement useful graph-based diagnostics but are never called by the orchestrator.

**Recommendation:** Integrate `TaskDependencyAnalyzer` as a pre-flight validation step in `DagExecutor.build()`. Feed `ErrorTracingAnalyzer` results into `_smart_retry()` for richer root-cause analysis.

### 5.3 Scheduler vs. Orchestrator: Two Worlds

The optimized scheduler (`examples/complex_scheduler/optimized_scheduler/`) implements production-grade patterns (auto-scaling, dual-heap, percentile metrics) that the core orchestrator lacks. The core orchestrator implements P-EVR patterns (verify-reflect, cascade handling, smart retry) that the scheduler lacks.

**Recommendation:** Extract the scheduler's `WorkerPool` auto-scaling and `MetricsCollector` into the orchestrator. Extract the orchestrator's `DagExecutor` and `VerificationResult` pipeline into the scheduler. These should not be separate codebases.

### 5.4 Serialization Fragmentation

Three serialization styles exist: plain dataclass `to_dict()` (Core), Pydantic `BaseModel` (Scheduler v2), and plain `dict` (Root-level). No cross-compatibility.

**Recommendation:** Standardize on Pydantic for all task/spec models across the codebase (Core is already using dataclasses with manual serialization — migrating to Pydantic would add validation for free).

---

## 6. Summary

The codebase contains **three parallel orchestration ecosystems** at different maturity levels:

1. **Core** (`src/pilotcode/orchestration/`) — Production P-EVR framework with LLM-driven planning, DAG execution, smart retry, and cascade handling. The most architecturally complete.

2. **Demos** (`examples/orchestration/`) — Forward-looking API examples that reference classes not yet implemented. Serve as requirements/specifications for the demo-layer API.

3. **Schedulers** (`examples/complex_scheduler/`) — Independent scheduling library with strong concurrency patterns but no verification layer and no LLM integration. A reference implementation showing production scalability patterns.

4. **Root-level tools** — Standalone diagnostic utilities using graph theory for dependency and error analysis. Not integrated into any execution path.

**The strongest patterns** — DAG-based execution, cascade failure handling, and wave parallelism — are concentrated in Core. **The strongest production engineering** — auto-scaling, dual-heap scheduling, and percentile metrics — is in Scheduler v2. Merging these strengths would create a uniquely capable orchestration system.
