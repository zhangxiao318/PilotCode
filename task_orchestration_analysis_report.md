# PilotCode Task Orchestration — Comprehensive Analysis Report

> **Date:** 2026-04-26  
> **Scope:** `src/pilotcode/orchestration/`, `examples/orchestration/`, `examples/complex_scheduler/`, root-level analysis tools  
> **Sources:** 17 source files, 4 orchestration demos, 8 analysis modules, 2 scheduler variants

---

## 1. Executive Summary

The PilotCode orchestration system spans **three parallel, non-interoperable ecosystems** — Core engine, aspirational demos, and independent schedulers — plus a set of orphaned analysis tools. The **Core** engine (`src/pilotcode/orchestration/`) implements a mature P-EVR (Plan-Execute-Verify-Reflect) framework with LLM-driven decomposition, Kahn's-algorithm DAG execution, wave parallelism, cascade failure handling, and smart retry. Four orchestration **demos** (`examples/orchestration/`) import classes (`TaskDecomposer`, `AgentCoordinator`, `DecompositionStrategy`) that **do not exist**, rendering them non-functional API specifications. The **distributed scheduler** (`examples/complex_scheduler/`) contains a v1 with intentional design flaws and a documented-but-empty v2. Root-level **analysis tools** implement graph-based dependency and error diagnostics but are never wired into any execution path.

This report identifies **45 distinct deficiencies** across 7 categories, catalogs **14 reusable orchestration patterns**, and provides **13 prioritized recommendations** with an implementation roadmap.

---

## 2. Codebase Landscape

### 2.1 Core Orchestrator (`src/pilotcode/orchestration/` — 31 modules)

The production engine implementing the full P-EVR lifecycle:

| Layer | Key Components | Capability |
|-------|---------------|------------|
| **Plan** | `MissionAdapter` (922 lines), `SmartCoordinator` | LLM-driven decomposition with `ComplexityLevel` (1–5), codebase exploration via glob + file read |
| **Execute** | `DagExecutor` (264 lines), `Orchestrator` (720 lines), `WorkerRegistry` | Kahn's algorithm DAG with depth/wave grouping; `asyncio.Semaphore`-bounded concurrency (default 3) |
| **Verify** | L1/L2/L3 Verifiers (745 lines total) | Syntax/lint, test execution, LLM code review |
| **Reflect** | `_smart_retry()`, `Reflector` (224 lines) | Failure-text analysis + task adjustment; health checks (stall/deadlock detection stubbed) |
| **State** | `StateMachine` (11 states, 187 lines), `Tracker` (SQLite, 337 lines) | Structured snapshots, cascade cancellation, periodic cleanup |
| **Context** | `ContextStrategySelector` (436 lines), `ProjectMemory` (283 lines) | 3-tier adaptive strategies, cross-task shared memory |

**Strengths:** Cascade failure handling (auto-cancels downstream on upstream failure), wave-based parallelism via depth groups, smart retry with task adjustment, graceful shutdown with chain propagation.
**Weaknesses:** `adapter.py` (922 lines) and `orchestrator.py` (720 lines) are God Classes; manual `to_dict()`/`from_dict()` serialization with no validation; static concurrency (no auto-scaling); brittle keyword-based retry classification; `Reflector` not wired into main loop; stall detection is an empty stub; two conflicting `VerificationResult` and `ProjectMemory` class pairs.

### 2.2 Orchestration Demos (`examples/orchestration/` — 892 total lines)

| Demo | Lines | Focus | Key Pattern |
|------|-------|-------|-------------|
| `basic_decomposition.py` | 84 | `TaskDecomposer.analyze()` + `.auto_decompose()` | Smoke test of core contract |
| `real_world_usage.py` | 323 | 6 end-to-end scenarios | Progress callbacks, run-with-preview, forced strategy, auto-config |
| `auto_decomposition_demo.py` | 186 | Heuristic analysis of 8 test cases + 4 canonical patterns | "Will Decompose" decision layer |
| `complex_task_demo.py` | 299 | Stress-test with large tasks; all 3 scheduling strategies | Timeline simulation, A/B comparison, metrics catalog |

**Critical Finding:** All four demos import `TaskDecomposer`, `AgentCoordinator`, and `DecompositionStrategy` from `pilotcode.orchestration` — **none of these classes exist in source**. `SmartCoordinator` bridges to `MissionAdapter` but under a different name. The demos are aspirational API specifications, not runnable code.

### 2.3 Complex Schedulers (`examples/complex_scheduler/`)

| Component | v1 (Distributed — implemented, intentional flaws) | v2 (Optimized — documented, not implemented) |
|-----------|-------------------------------------------------|----------------------------------------------|
| **Models** | `dataclass` with callable handlers (non-serializable) | Pydantic `TaskDefinition` (frozen) / `TaskInstance` (mutable) split |
| **Queue** | Manual `heapq` + `asyncio.Condition`, busy-wait polling | `asyncio.PriorityQueue` with event-driven notification |
| **Workers** | Fixed pool, sync handlers block event loop | Auto-scaling pool, `run_in_executor` offloading |
| **State** | In-memory dicts, O(n) linear scan | Pluggable `StateBackend` ABC, O(1) status-indexed lookups |
| **Scheduling** | 1s polling loop, linear scan | Dual-heap (priority + delayed), dynamic wait interval |
| **Metrics** | `print()` to stdout | `MetricsCollector` with circular buffers, percentiles |
| **Shutdown** | Cancels without awaiting in-progress work | Graceful drain with `asyncio.gather(return_exceptions=True)` |

### 2.4 Root-Level Analysis Tools (8 modules)

| Tool | Purpose | Status |
|------|---------|--------|
| `task_dependency_analysis.py` | DAG construction with cycle/undefined-dep detection (NetworkX) | **Orphaned** — duplicates Core's Kahn's but never called |
| `error_tracing_analysis.py` | Error causality graph with cascade/root-cause analysis | **Orphaned** — could inform smart retry but never wired |
| `exception_analysis.py` | Static audit identifying 5 exception-handling anti-patterns | Advisory only |
| `parallel_test.py` | Thread-safety demo with lock-based mutual exclusion | Demo harness, not a test suite |
| `scan_tools.py` | AI file discovery via `os.walk` | Single-threaded; silent `except: pass` |
| `full_demo.py` | Rich TUI showcase of all PilotCode features | Interactive demo |
| `run_single_instance.py` | SWE-bench harness runner | Single-instance only |
| `run_meta_analysis.py` | WebSocket client sending refactoring prompt to PilotCode | LLM-driven audit bridge |

---

## 3. Comparative Pattern Analysis

### 3.1 Decomposition Approaches

| Ecosystem | Model | Granularity | Discovery | LLM Integration |
|-----------|-------|-------------|-----------|-----------------|
| **Core** | `Mission → Phase → TaskSpec` with `ComplexityLevel` | Fine | `_explore_codebase()` | ✅ Full LLM planning |
| **Demos** | `DecompositionStrategy` enum + role-assigned subtasks | Medium | `analyze()` heuristics | ✅ Aspirational |
| **Schedulers** | Per-handler callable tasks | Fine | None (pre-decomposed) | ❌ |
| **Root Tools** | Static `{id, depends_on}` dicts | Coarse | Manual | ❌ |

### 3.2 Dependency Resolution

| Feature | Core (`dag.py`) | Root (`task_dependency_analysis.py`) | Schedulers |
|---------|-----------------|--------------------------------------|------------|
| Algorithm | Hand-rolled Kahn's | NetworkX `topological_sort` | None (bidirectional lists) |
| Cycle Detection | ✅ `ValueError` with cycle members | ✅ `nx.simple_cycles` | ❌ |
| Depth/Wave Groups | ✅ `get_execution_path()` | ❌ | ❌ |
| Cascade Cancellation | ✅ `_cancel_downstream_tasks()` | ❌ | ❌ |
| Critical Path | ✅ `get_critical_path()` | ❌ | ❌ |

### 3.3 Reusable Orchestration Patterns Catalog

| Pattern | Where Used | Maturity |
|---------|-----------|----------|
| Analyze-then-Decide | Demos, `SmartCoordinator` | Config-driven |
| Explore-then-Plan | Core (`MissionAdapter`) | LLM + filesystem |
| P-EVR Full Cycle | Core (`Orchestrator`) | Production |
| DAG + Wave Parallelism | Core (`DagExecutor`) | Kahn's + depth groups |
| Cascade Failure Handling | Core | Recursive cancellation |
| Smart Retry with Analysis | Core | Keyword-based (brittle) |
| Dual-Heap Scheduling | Scheduler v2 (spec) | Event-driven |
| Auto-Scaling Workers | Scheduler v2 (spec) | Fill-ratio thresholds |
| Pluggable State Backend | Scheduler v2 (spec), Core | ABC pattern |
| Progress Callbacks | Core, Demos | Event-driven |
| Circuit Breaker | `error_recovery.py` | Production |
| Retry with Jitter | `error_recovery.py` | Exponential backoff |
| Multi-Level Verification | Core Verifiers | L1→L2→L3 pipeline |
| Context-Adaptive Strategy | `context_strategy.py` | 3-tier token budgeting |

---

## 4. Detailed Improvement Areas

### 4.1 Architecture Fragmentation (🔴 Critical — 9 deficiencies)

Three non-interoperable ecosystems with overlapping responsibilities. Demo imports reference non-existent classes (all 4 fail at `import`). Root-level analysis tools are orphaned. Three serialization styles (Core dataclass, Scheduler Pydantic, Root dict) with zero cross-compatibility. Two conflicting `VerificationResult` classes, two conflicting `ProjectMemory` classes. Scheduler v2 is documented but contains zero implementation files. `adapter.py` (922 lines) and `orchestrator.py` (720 lines) are God Classes needing decomposition into Planner / Executor / VerifierRegistry / ReworkManager.

### 4.2 Error Handling & Resilience (🔴 Critical — 10 deficiencies)

| Gap | Location | Consequence |
|-----|----------|-------------|
| Silent `except: pass` / `print(e)` | `scan_tools.py`, scheduler loops, worker loop | Errors invisible, impossible to debug |
| No timeout enforcement | `worker.py::_execute_task()` | Hung tasks block workers indefinitely |
| Sync handlers block event loop | worker.py (no `run_in_executor`) | One slow callable freezes ALL workers |
| No retry at scanner/demo level | `scan_tools.py`, all 4 demos | Transient failures become permanent |
| Shutdown cancels without await | `scheduler.py::stop()`, `worker.py::stop()` | Orphaned tasks in unknown state |
| Retry blocks caller | `queue.py::fail()` | Jams queue throughput |
| L3 review uses brittle string matching | `adapter.py` line 215 (`"approve" in review`) | LLM review results unreliable |
| Reflector not wired to main loop | `orchestrator.py` | No runtime health monitoring |
| Stall detection is empty stub | `reflector.py:175-180` | Cannot detect hung tasks |
| Inconsistent error returns | `orchestrator.py` (Result) vs `adapter.py` (dict) vs `agent_orchestrator.py` (string) | Callers handle 3 error formats |

### 4.3 Resource Management (🔴 Critical — 10 deficiencies)

Memory leaks: `_task_map` never cleaned, `_history` unbounded, `task.metadata` uncapped, dead-letter queue unbounded, `task.result` stores arbitrary-size data. No persistent state — `StateManager` memory-only, complete loss on restart. No backpressure — `queue.submit()` blocks indefinitely. O(n) `get_tasks_by_status()` linear scan. Read-then-write race on `update_status()`. Scanner reads all files into memory with no streaming or size cap.

### 4.4 Observability (🔴 Critical — 5 deficiencies)

`print()` used everywhere — no log levels, no JSON output, no aggregation. No correlation/trace IDs across task chains. Raw integer counters, no time-series or rate tracking. Metrics computed via expensive O(n) scan on every `get_stats()` call. No alerting mechanism for failure rate or queue depth thresholds.

### 4.5 Testing & Data Model (🔴 Critical — 11 deficiencies)

Zero unit tests for scheduler, state manager, queue, or worker modules. All 4 demos are analysis-only (no execution testing). Mock agents never fail (happy-path only). `parallel_test.py` is a demo harness, not an assertion-based suite. Callables stored in dataclass fields (can't JSON-serialize). No Pydantic validation on v1 task models. `QueueStats` returns mutable internals. Core uses manual `to_dict()`/`from_dict()` with no validation. Three different `dependencies` list formats across ecosystems.

---

## 5. Actionable Recommendations

### 5.1 P0 — Immediate (Week 1)

| # | Action | Effort |
|---|--------|--------|
| R1 | **Create `decomposer.py`** — `DecompositionStrategy` enum, `TaskDecomposer` (wraps `MissionAdapter._plan_mission()`), `AgentCoordinator` (wraps `Orchestrator`). Export from `__init__.py`. | 2 days |
| R2 | **Unify `VerificationResult`** — Remove duplicate in `orchestrator.py`; use `verifier/base.py` definition with `Verdict` enum. | 0.5 day |
| R3 | **Unify `ProjectMemory`** — Merge `orchestration/project_memory.py` and `context/project_memory.py` into single module. | 0.5 day |

### 5.2 P1 — Short-Term (Weeks 2–3)

| # | Action | Effort |
|---|--------|--------|
| R4 | **Add timeout + executor offloading** — `asyncio.wait_for` in `_execute_task()`; detect sync handlers → `loop.run_in_executor`. | 1 day |
| R5 | **Replace silent exception swallowing** — Replace `except: pass` / `print(e)` with `logger.exception()` in all modules. | 0.5 day |
| R6 | **Add structured logging** — Introduce `structlog`-based `OrchestrationLogger` with `ContextVar` correlation IDs; replace all `print()`. | 1 day |
| R7 | **Implement stall detection** — Record timestamps in `StateMachine`; implement `_find_stalled_tasks()`; wire `Reflector.check()` into `Orchestrator.run()`. | 1 day |
| R8 | **Fix L3 review parsing** — Require structured JSON output (`{"verdict": "APPROVE|NEEDS_REWORK", ...}`). | 0.5 day |

### 5.3 P2 — Medium-Term (Month 2)

| # | Action | Effort |
|---|--------|--------|
| R9 | **Split `adapter.py`** — Extract `MissionPlanner`, `WorkerExecutor`, `VerifierRegistry`, `ProjectExplorer` into separate modules. | 3 days |
| R10 | **Create `RetryPolicy` & `StateBackend`** — New `retry.py` (exponential backoff, jitter, retryable exceptions) + `persistence.py` (ABC + `MemoryBackend` + `SqliteBackend`). | 2 days |
| R11 | **Fix memory leaks** — Cap `_history` at 100/task, `task.metadata` at 10KB, `task.result` at 1MB; cap dead-letter queue at 1000; add `queue.submit(timeout=5.0)` with `QueueFull`. | 1 day |
| R12 | **Integrate analysis tools** — Port `detect_cycles()` and `detect_undefined_deps()` into `DagExecutor.build()` as pre-flight validation. Port `classify_root_cause()` into `retry.py` to replace brittle keyword-matching in `_smart_retry()`. | 2 days |

### 5.4 P3 — Long-Term (Month 3+)

| # | Action | Effort |
|---|--------|--------|
| R13 | **Implement optimized scheduler v2** — Populate 6 modules (`models.py`, `queue.py`, `worker.py`, `scheduler.py`, `state.py`, `metrics.py`) with dual-heap, auto-scaling, percentile metrics (~1,370 lines). | 3 days |
| — | Migrate Core models to Pydantic (free validation, single serialization format) | 2 days |
| — | Add verification layer to scheduler (bridge Core's L1/L2/L3 as post-execution hooks) | 1 day |
| — | Create test suite: `tests/test_queue.py`, `test_state.py`, `test_scheduler.py`, `test_worker.py`, `test_retry.py` (pytest + pytest-asyncio) | 3 days |
| — | Introduce DI container to replace 6 global singletons | 2 days |
| — | Unify error handling to `Result[T]` pattern across all modules | 2 days |

### 5.5 Implementation Roadmap

```
Week 1:     R1-R3 (decomposer.py, unified VerificationResult, unified ProjectMemory)
Week 2-3:   R4-R8 (timeout, logging, stall detection, L3 fix)
Month 2:    R9-R12 (adapter split, retry/state, memory leaks, tool integration)
Month 3+:   R13 + Pydantic migration + test suite + DI container
```

**New modules (6):** `decomposer.py`, `logging.py`, `metrics.py`, `retry.py`, `persistence.py`, `validation.py`  
**Populated (6):** `optimized_scheduler/` (models, queue, worker, scheduler, state, metrics)  
**Modified:** 14 files across Core, scheduler v1, root-level tools  
**New tests:** 5 files  
**New dependencies:** `structlog`, `aiosqlite` (pure Python)

---

## Appendix: Deficiency Summary

| Category | Count | Critical (🔴) |
|----------|-------|--------------|
| Architecture & Integration | 9 | 6 |
| Error Handling & Resilience | 10 | 8 |
| Resource Management | 10 | 8 |
| Observability | 5 | 5 |
| Testing | 7 | 6 |
| Data Model & Serialization | 4 | 4 |
| **Total** | **45** | **37** |

> *All recommendations are self-contained — each can be implemented and merged independently.*  
> *Supporting detail in: `enhancement_proposals.md`, `improvement_candidates.md`, `functional_patterns_analysis.md`, `error_parallel_analysis.md`, `codebase_analysis_scheduler.md`.*
