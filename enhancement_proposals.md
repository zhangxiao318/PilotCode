# Enhancement Proposals — PilotCode Orchestration System

> Based on: `improvement_candidates.md` (45 deficiencies, 7 categories)
> Each proposal: problem → design → implementation → expected benefits

---

## Proposal 1 — Unify Three Fragmented Orchestration Ecosystems

**Deficiencies:** 3.1–3.3, 3.6, 6.1–6.3, 7.5 (Architecture, API Contract)

**Problem:** Three parallel ecosystems with zero interoperability: Core (`src/pilotcode/orchestration/`) has P-EVR + DAG execution; Demos (`examples/orchestration/`) import `TaskDecomposer`, `AgentCoordinator`, `DecompositionStrategy` which **don't exist** (all 4 demos fail at `import`); Scheduler v2 (`examples/complex_scheduler/optimized_scheduler/`) is **empty** — patterns documented but zero `.py` files.

**Design:**

- **1a.** Create `src/pilotcode/orchestration/decomposer.py` with `DecompositionStrategy` enum (NONE/SEQUENTIAL/PARALLEL/HIERARCHICAL), `TaskDecomposer` (thin wrapper around `MissionAdapter._plan_mission()`), and `AgentCoordinator` (thin wrapper around `Orchestrator` with progress callbacks). Export from `__init__.py`.
- **1b.** Populate 6 modules in `optimized_scheduler/`: `models.py` (Pydantic `TaskDefinition`/`TaskInstance`/`TaskResult` split), `queue.py` (`asyncio.PriorityQueue` + delayed-task heap), `worker.py` (auto-scaling pool with `run_in_executor`), `scheduler.py` (dual-heap with DI), `state.py` (`StateBackend` ABC + `MemoryBackend`), `metrics.py` (`MetricsCollector` with percentile buffers).
- **1c.** Migrate Core models from manual `to_dict()`/`from_dict()` dataclasses to Pydantic `BaseModel` for free validation + cross-ecosystem compatibility.

**Implementation:** (1) Create `decomposer.py` + update `__init__.py` exports. (2) Implement 6 scheduler v2 modules (~1,370 lines total). (3) Convert `task_spec.py` dataclasses to Pydantic with `.to_dict()` backward-compat. (4) Add `[project.optional-dependencies] scheduler = ["pydantic>=2.0"]`.

**Benefits:** 4 demos become runnable; production scheduler patterns become real code; single Pydantic serialization format across ecosystems; consistent API naming between demos and source.

---

## Proposal 2 — Robust Error Handling & Resilience Framework

**Deficiencies:** 1.1, 1.6, 2.1–2.8 (Concurrency, Error Handling)

**Problem:** Sync handlers block the asyncio event loop (one slow callable freezes ALL workers). `task.timeout` defined but never enforced — hung tasks block workers indefinitely. Silent `except Exception: pass` in scanner + scheduler loops. No retry at scanner/demo level. No cascade failure handling outside Core. `TaskScheduler.stop()` cancels without awaiting in-progress work.

**Design:**

- **2a. Timeout + executor offloading** in `worker.py::_execute_task()`: detect sync vs async handler; offload sync via `loop.run_in_executor(None, ...)`; wrap in `asyncio.wait_for(coro, timeout=task.timeout or 60.0)`; set `TaskStatus.TIMEOUT` on expiry.
- **2b. `RetryPolicy` dataclass** (new: `src/pilotcode/orchestration/retry.py`): `max_retries=3`, `base_delay=1.0`, `max_delay=60.0`, `multiplier=2.0`, `jitter=True`, `retryable_exceptions=(IOError, TimeoutError, ConnectionError)`. Wire into `scan_tools.py` (file I/O), `queue.py::fail()` (non-blocking async resubmit via `asyncio.create_task`), and `orchestrator.py::_smart_retry()`.
- **2c. Graceful shutdown protocol** in `scheduler.py::stop()`: set stop event → close queue → await in-progress tasks with `drain_timeout=30s` → cancel on timeout → clear registries → flush state. Workers get heartbeat-based `is_healthy()` (5s heartbeat interval, 15s max gap) instead of time-based 30s window.

**Implementation:** (1) Create `retry.py`. (2) Modify `worker.py` — `asyncio.wait_for` + `run_in_executor` + heartbeat. (3) Modify `scheduler.py` — drain-then-stop. (4) Modify `queue.py` — async retry. (5) Modify `scan_tools.py` — wrap I/O with `RetryPolicy`. (6) Add `CancelledError` handling in all async loops.

**Benefits:** Zero event-loop blocking; hung tasks cannot block workers; transient I/O failures recover with jitter; no orphaned tasks on shutdown; accurate deadlock detection within 15s.

---

## Proposal 3 — Persistent State & Memory Management

**Deficiencies:** 4.1–4.10, 7.1–7.3 (Resource Mgmt, Data Model)

**Problem:** `_task_map` never cleaned → OOM. `_history` per task grows unbounded. `StateManager` memory-only → complete data loss on restart. `get_tasks_by_status()` does O(n) linear scan. `update_status()` has read-then-write race condition. `task.result` stores arbitrary-size data with no cap.

**Design:**

- **3a. `StateBackend` ABC** (new: `src/pilotcode/orchestration/persistence.py`): abstract `save/get/get_by_status/delete/cleanup`. `MemoryBackend` with `asyncio.Lock` + `dict[TaskStatus, set[id]]` index for O(1) status lookups. `SqliteBackend` with WAL mode for persistent storage.
- **3b. Bounded collections:** clear `queue._task_map` on terminal status; cap `state._history` at 100 entries/task (FIFO); cap `task.metadata` at 10KB (reject oversized); cap `task.result` at 1MB (truncate with `[TRUNCATED]`); cap dead-letter queue at 1000 entries (drop oldest); `queue.submit()` accepts `timeout=5.0` and raises `QueueFull` instead of blocking forever.
- **3c. Atomic CAS transitions:** `update_status(task_id, new_status, expected=None)` uses `asyncio.Lock` + compare-and-swap to prevent concurrent corruption.

**Implementation:** (1) Create `persistence.py` with ABC + two backends. (2) Add `aiosqlite` to requirements. (3) Modify `state.py` — inject backend, add CAS lock. (4) Modify `queue.py` — size caps, submit timeout, `_task_map` cleanup. (5) Modify `task.py` — metadata/result size validation. (6) Add periodic cleanup coroutine (every 5 min, delete terminal tasks >1hr old). (7) Add `QueueFull` exception.

**Benefits:** Survive restarts via SQLite; bounded memory prevents OOM under sustained load; CAS eliminates status-update races; graceful backpressure via `submit(timeout=)`; O(1) status queries.

---

## Proposal 4 — Structured Observability & Logging Framework

**Deficiencies:** 5.1–5.5 (Observability)

**Problem:** `print()` everywhere — no levels, no JSON, no aggregation. No correlation IDs across task chains. Raw integer counters, no time-series or rates. Metrics computed via O(n) scan on every `get_stats()` call. No alerting mechanism.

**Design:**

- **4a. Structured logging** (new: `src/pilotcode/orchestration/logging.py`): `structlog`-based `OrchestrationLogger` with `ContextVar` for `correlation_id` propagation. Replace all `print()` in `scan_tools.py`, scheduler modules (5 files), state manager, and analyzers with `logger.info/warning/error/exception`.
- **4b. `MetricsCollector`** (new: `src/pilotcode/orchestration/metrics.py`): circular buffers (deque, maxlen=1000) for execution times, wait times, success/failure. `PerformanceSnapshot` dataclass: throughput, p50/p99 latency, queue depth, active workers, error rate. `add_alert_handler(threshold, callback)` for thresholds: `error_rate > 0.1`, `queue_depth > 1000`, `p99_latency > 30s`.
- **4c. Correlation-ID injection:** `bind_correlation(mission_id)` at mission creation, propagated through DAG executor → worker dispatch → state transitions → verifier pipeline.

**Implementation:** (1) Add `structlog` to requirements. (2) Create `logging.py` + `metrics.py`. (3) Refactor 7+ files: replace `print()` with structured logging. (4) Inject `correlation_id` in `Orchestrator._execute_phase()` and scheduler `submit()`. (5) Wire `MetricsCollector.record()` into every task completion path. (6) Add `AlertThreshold` config dataclass.

**Benefits:** JSON logs ingestible by ELK/Loki/Datadog; end-to-end traceability via correlation IDs; O(1) metrics snapshots via circular buffers; automatic threshold-based alerting.

---

## Proposal 5 — Integrated Analysis & Validation Pipeline

**Deficiencies:** 3.5, 5.6–5.9, 6.5–6.6 (Integration, Testing)

**Problem:** Root-level tools (`task_dependency_analysis.py`, `error_tracing_analysis.py`, `exception_analysis.py`) implement graph-based diagnostics but are **never called** by the orchestrator. Scheduler v1 has no verification layer. Zero unit tests for scheduler/state/queue modules. All demos test only happy paths; `parallel_test.py` is a harness, not a test suite.

**Design:**

- **5a. Pre-flight DAG validation** (new: `src/pilotcode/orchestration/validation.py`): port `detect_cycles()` and `detect_undefined_deps()` from `task_dependency_analysis.py` using Core's existing Kahn's algorithm (no NetworkX). Call `_validate_dependencies()` in `DagExecutor.build()` — raise `DependencyValidationError` with defect list before execution begins.
- **5b. Graph-based smart retry** (modify `orchestrator.py`): port `build_error_chain()` and `classify_root_cause()` from `error_tracing_analysis.py` into `retry.py`. Replace brittle keyword-matching in `_smart_retry()` with root-cause classification: `MISSING_FILE` → add `must_use`; `SYNTAX_ERROR` → expand context budget; `DEPENDENCY_FAILURE` → cascade-skip instead of retry.
- **5c. Scheduler verification layer** (new: `verifier/scheduler_verifier.py`): bridge Core's L1/L2/L3 verifiers into scheduler — `StaticVerifier` (syntax/lint), `TestVerifier` (run tests), `ReviewVerifier` (LLM review). Wire as post-execution hook in `scheduler.py::_execute_task()`.
- **5d. Test suite:** `tests/test_queue.py`, `test_state.py`, `test_scheduler.py`, `test_worker.py`, `test_retry.py` using `pytest` + `pytest-asyncio`. Cover submit/get/fail/backpressure, CRUD/CAS/cleanup/persistence, chain/parallel/stop/retry, execute/timeout/health, backoff/jitter/max-retries.

**Implementation:** (1) Create `validation.py` with ported cycle/dep detection. (2) Add `_validate_dependencies()` call in `DagExecutor.build()`. (3) Port error-chain analysis into `retry.py`. (4) Replace keyword-matching in `_smart_retry()`. (5) Create `scheduler_verifier.py`. (6) Create `tests/` with 5 test files. (7) Add `pytest`, `pytest-asyncio`, `pytest-cov` to dev deps.

**Benefits:** Dependency bugs caught at DAG-build time; smart retry uses root-cause analysis instead of brittle string matching; scheduler gains P-EVR quality verification; test suite provides regression safety for refactoring; orphaned analysis tools become integrated engine components.

---

## Summary

| # | Proposal | Effort | Impact | Prerequisites |
|---|----------|--------|--------|---------------|
| 1 | Unify Ecosystems | Large | 🔴 Critical | None |
| 2 | Resilience Framework | Medium | 🔴 Critical | None |
| 3 | Persistent State | Medium | 🔴 Critical | Proposal 2 (CAS) |
| 4 | Observability | Medium | 🟡 High | Proposal 1 (single target) |
| 5 | Validation Pipeline | Medium | 🟡 High | Proposals 1, 2 |

**New modules:** `decomposer.py`, `logging.py`, `metrics.py`, `retry.py`, `persistence.py`, `validation.py` (6 files)
**Populated modules:** `optimized_scheduler/` (6 files)
**Modified modules:** 14 across Core, scheduler v1, root-level tools
**New tests:** 5 files (queue, state, scheduler, worker, retry)
**New deps:** `structlog`, `aiosqlite` (pure Python, no system deps)

*All proposals are self-contained — each can be implemented and merged independently.*
