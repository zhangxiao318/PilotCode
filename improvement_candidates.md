# Improvement Candidates — Synthesized Deficiency Catalog

> Synthesized from: `functional_patterns_analysis.md`, `error_parallel_analysis.md`,
> `codebase_analysis_root.md`, `codebase_analysis_demos.md`, `codebase_analysis_scheduler.md`.

---

## 1. Concurrency & Parallelism Gaps

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 1.1 | **Sync handlers block asyncio event loop** — no `run_in_executor` offloading | `examples/complex_scheduler/distributed_scheduler/worker.py::Worker._execute_task()` | One synchronous handler freezes all workers; throughput drops to zero |
| 1.2 | **Fixed worker pool, no auto-scaling** — v1 scheduler hard-codes worker count | `distributed_scheduler/scheduler.py::TaskScheduler`, `distributed_scheduler/worker.py::WorkerPool` | Cannot adapt to load spikes; idle workers waste resources at low load |
| 1.3 | **Polling-based scheduling (1s loop)** instead of event-driven notification | `distributed_scheduler/scheduler.py::_scheduler_loop()` | Adds up to 1s latency; wastes CPU on idle cycles |
| 1.4 | **No wave-parallelism awareness** outside Core — flat priority queue only | `distributed_scheduler/queue.py`, `distributed_scheduler/scheduler.py`, all orchestration demos | Tasks that could run in parallel are serialized; demo `strategy="parallel"` override has no real execution engine behind it |
| 1.5 | **Scanner fully single-threaded** — `os.walk` with no concurrency | `scan_tools.py::scan_ai_tools()` | Blocking I/O on large directory trees; no parallelism for file I/O |
| 1.6 | **No timeout enforcement in worker execution** — `task.timeout` field defined but never applied | `distributed_scheduler/worker.py::_execute_task()` | Hung tasks block worker indefinitely with no recovery path |
| 1.7 | **Core semaphore is static** (`max_concurrent_workers` configurable but not adaptive) | `src/pilotcode/orchestration/` orchestrator | No load-based concurrency adjustment; must be tuned manually |

---

## 2. Error Handling & Failure Recovery

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 2.1 | **Silent exception swallowing** — `except Exception: pass` or `print(e)` only | `scan_tools.py` (unreadable files), `distributed_scheduler/scheduler.py::_scheduler_loop()`, `distributed_scheduler/scheduler.py::_monitor_loop()`, `distributed_scheduler/worker.py::_run_loop()` | Errors invisible; data silently lost; impossible to debug production failures |
| 2.2 | **No retry at scanner or demo level** | `scan_tools.py`, all 4 `examples/orchestration/*.py` demos | Transient I/O failures become permanent data loss |
| 2.3 | **Retry blocks caller with `asyncio.sleep()`** — no async retry queue | `distributed_scheduler/queue.py::fail()` | Retry logic ties up the queue operation; jams throughput |
| 2.4 | **No cascade failure handling outside Core** | `distributed_scheduler/scheduler.py`, `distributed_scheduler/task.py` (Chain/Parallel tasks), orchestration demos | Failure of upstream task leaves downstream tasks orphaned or blocked forever |
| 2.5 | **Core's `_smart_retry()` uses brittle keyword matching** on error strings | `src/pilotcode/orchestration/orchestrator.py::_smart_retry()` | Misses failures with unexpected error messages; no ML/embedding-based classification |
| 2.6 | **`TaskScheduler.stop()` cancels without awaiting in-progress work** | `distributed_scheduler/scheduler.py::stop()`, `distributed_scheduler/worker.py::stop()` | Tasks left in unknown state; `_chained_tasks` and `_parallel_tasks` registries never cleaned |
| 2.7 | **Worker health check is time-based (`30s`), not heartbeat-based** | `distributed_scheduler/worker.py::is_healthy()` | Blocked worker appears healthy; no accurate deadlock detection |
| 2.8 | **`to_json()` has no try/except for non-serializable data** (callables in args/kwargs) | `distributed_scheduler/task.py::to_json()` | Crashes at serialization boundary; breaks any persistence or log pipeline |

---

## 3. Code Duplication & Architecture Fragmentation

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 3.1 | **Three parallel orchestration ecosystems** with overlapping responsibilities | Core (`src/pilotcode/orchestration/`), Demos (`examples/orchestration/`), Scheduler v1 (`examples/complex_scheduler/distributed_scheduler/`) | Features invented independently in each; no shared evolution; users must choose one |
| 3.2 | **DAG + topological sort implemented twice** — Core hand-rolls Kahn's; Root-level uses NetworkX | `src/pilotcode/orchestration/dag.py::DagExecutor`, `task_dependency_analysis.py::TaskDependencyAnalyzer` | Two codebases to maintain; NetworkX is a heavy dependency for standalone analysis |
| 3.3 | **`TaskDecomposer` / `AgentCoordinator` imported by demos but not implemented** | `examples/orchestration/basic_decomposition.py`, `real_world_usage.py`, `auto_decomposition_demo.py`, `complex_task_demo.py` — all import from `pilotcode.orchestration` | All 4 demos fail at import time; demos are aspirational specifications, not runnable code |
| 3.4 | **Three serialization styles, zero cross-compatibility** | Core: `dataclass.to_dict()` / `from_dict()`; Scheduler v2: Pydantic `BaseModel`; Root-level: plain `dict` | Cannot pass a task spec from scheduler to orchestrator; every boundary needs manual conversion |
| 3.5 | **Root-level analysis tools are orphaned** — not wired into any execution path | `task_dependency_analysis.py`, `error_tracing_analysis.py`, `exception_analysis.py` | Sophisticated graph-based validation exists but orchestrator never invokes it |
| 3.6 | **Scheduler v2 (optimized) directory is empty** — production patterns exist only in documentation | `examples/complex_scheduler/optimized_scheduler/` (no `.py` files found) | Auto-scaling, dual-heap, percentile metrics, pluggable backends are described but not implemented |

---

## 4. Scalability & Resource Management

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 4.1 | **`_task_map` never cleaned** — completed tasks remain in queue index forever | `distributed_scheduler/queue.py::TaskQueue._task_map` | Unbounded memory growth; OOM under sustained load |
| 4.2 | **`_history` per task grows unbounded** — full timeline, never trimmed | `distributed_scheduler/state.py::StateManager._history` | Memory grows linearly with uptime × task count |
| 4.3 | **`task.metadata` dict unbounded** — no size limit on arbitrary attached data | `distributed_scheduler/task.py::Task.metadata` | One task with large metadata consumes disproportionate memory |
| 4.4 | **`task.result` stores arbitrary-size result with no cap** | `distributed_scheduler/task.py::Task.result`, `to_dict()` includes `str(self.result)` | Large results cause OOM or serialization crash |
| 4.5 | **Dead-letter queue unbounded** — no pagination, max size, or replay mechanism | `distributed_scheduler/queue.py::TaskQueue._dead_letter_queue` | Failed tasks accumulate without bound; no way to drain or replay |
| 4.6 | **`submit()` blocks indefinitely on backpressure** — no timeout, no rejection | `distributed_scheduler/queue.py::submit()` (waits on `_not_full.wait()`) | System overwhelmed with no degradation strategy; callers hang forever |
| 4.7 | **No persistent state** — `StateManager` is memory-only, all lost on restart | `distributed_scheduler/state.py` | Complete state loss on crash or restart; no recovery possible |
| 4.8 | **`get_tasks_by_status()` does O(n) linear scan every call** | `distributed_scheduler/state.py::StateManager.get_tasks_by_status()` | Degrades linearly with task count; unusable beyond a few hundred tasks |
| 4.9 | **`read-then-write` race condition on `update_status()`** — not atomic | `distributed_scheduler/state.py::StateManager.update_status()` | Concurrent status updates from multiple workers can silently corrupt state |
| 4.10 | **Scanner reads all files into memory** — no streaming, no size cap | `scan_tools.py::scan_ai_tools()` | OOM on large repositories with many AI-related files |

---

## 5. Testing & Observability

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 5.1 | **`print()` used everywhere instead of structured logging** | `scan_tools.py`, `distributed_scheduler/scheduler.py`, `distributed_scheduler/worker.py`, `distributed_scheduler/state.py`, `exception_analysis.py`, `task_dependency_analysis.py` | No log levels, no JSON output, no correlation IDs, no aggregation possible |
| 5.2 | **No correlation / trace IDs propagated across task chains** | All scheduler + demo modules | Cannot trace a request through chain of dependent tasks |
| 5.3 | **Raw integer counters, no time-series or rate tracking** | `distributed_scheduler/state.py::_counters`, `distributed_scheduler/queue.py::_stats` | Cannot compute throughput, error rate, or latency percentiles |
| 5.4 | **Metrics computed via expensive aggregation on every `get_stats()` call** | `distributed_scheduler/scheduler.py::get_stats()` | Every metrics query rescans all tasks; O(n) per call |
| 5.5 | **No alerting mechanism** — no failure-rate or queue-depth thresholds | All modules | Operators cannot detect degradation without manual inspection |
| 5.6 | **All 4 orchestration demos are analysis-only** — no execution, no error-path testing | `examples/orchestration/basic_decomposition.py`, `auto_decomposition_demo.py`, `complex_task_demo.py` | Demos validate decomposition heuristics but never prove end-to-end execution works |
| 5.7 | **Mock agents in demos never fail** — no failure-path coverage | `examples/orchestration/real_world_usage.py::MockModelClient` | Happy-path-only testing; real failure modes untested |
| 5.8 | **No unit tests found** for scheduler, state manager, or queue | `examples/complex_scheduler/distributed_scheduler/` (no `test_*.py`) | Zero regression safety; refactoring is high-risk |
| 5.9 | **`parallel_test.py` is a demo harness, not a test suite** — no assertions, no CI integration | `parallel_test.py` | Demonstrates race conditions but doesn't enforce safety |

---

## 6. API Contract & Integration Gaps

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 6.1 | **Demos import non-existent classes** — `TaskDecomposer`, `AgentCoordinator`, `DecompositionStrategy` | `examples/orchestration/basic_decomposition.py` (lines 8–13), `real_world_usage.py`, `auto_decomposition_demo.py`, `complex_task_demo.py` | All demos fail at `import`; "example code" is de facto API specification with no implementation |
| 6.2 | **`SmartCoordinator` bridges demo API to `MissionAdapter` but under different naming** | `src/pilotcode/orchestration/smart_coordinator.py` vs. demo imports of `AgentCoordinator` | Users who read demos cannot find the classes they expect |
| 6.3 | **No unified `Strategy` enum** — demos have `DecompositionStrategy` (NONE/SEQUENTIAL/PARALLEL/HIERARCHICAL); Core has `ContextStrategySelector` (3 strategies) | `examples/orchestration/` vs. `src/pilotcode/orchestration/context_strategy.py` | Two strategy systems with no mapping between them |
| 6.4 | **`auto_config.py` toggles referenced by demos but unclear if wired to Core** | `examples/orchestration/real_world_usage.py` (Example 6), `auto_decomposition_demo.py` (Demo 4) | Global config may or may not affect actual orchestrator behavior |
| 6.5 | **Scheduler v1's `ScheduledTask`/`ChainedTask`/`ParallelTask` abuse inheritance from `Task`** | `distributed_scheduler/task.py` | Fragile class hierarchy; `isinstance` checks litter execution paths; hard to extend |
| 6.6 | **Core verifier has 3 levels (L1/L2/L3) but scheduler has no verification layer at all** | `src/pilotcode/orchestration/verifier/` vs. `examples/complex_scheduler/` | Scheduler tasks complete without quality verification; no P-EVR loop possible |

---

## 7. Data Model & Serialization Issues

| # | Deficiency | Files / Modules | Impact |
|---|-----------|----------------|--------|
| 7.1 | **Callables stored in dataclass fields** — `handler`, `args`, `kwargs` cannot be JSON-serialized | `distributed_scheduler/task.py::Task` (dataclass with `handler: Optional[Callable]`) | Breaks all persistence, logging, and IPC; `to_dict()` uses `str()` fallback producing useless output |
| 7.2 | **No Pydantic validation on task models** — plain `@dataclass` with no field constraints | `distributed_scheduler/task.py` | Invalid task specs (negative retries, empty IDs) propagate silently to execution |
| 7.3 | **`QueueStats` returns raw internal dict** — exposes mutable internals to caller | `distributed_scheduler/queue.py::get_stats()` | Caller can accidentally mutate queue state; no encapsulation |
| 7.4 | **Core uses manual `to_dict()`/`from_dict()` on dataclasses** — no validation, no type coercion | `src/pilotcode/orchestration/` (TaskSpec, Mission, etc.) | Manual serialization is error-prone; field renaming breaks all consumers |
| 7.5 | **Three different `dependencies` list formats** — no shared schema | Core: `list[str]` in `TaskSpec`; Scheduler v1: bidirectional `dependencies`/`dependents` on `Task`; Demos: `list[str]` in subtask dict | Dependency graph cannot be shared across ecosystem boundaries |

---

## 8. Summary: Top-10 Cross-Cutting Deficiencies

| Rank | Deficiency | Category | Severity |
|------|-----------|----------|----------|
| 1 | Three fragmented orchestration ecosystems with no interoperability | Architecture | 🔴 Critical |
| 2 | Demo imports reference non-existent classes — demos are non-functional | API Contract | 🔴 Critical |
| 3 | Silent exception swallowing across scanner + scheduler | Error Handling | 🔴 Critical |
| 4 | No timeout enforcement on task execution | Concurrency | 🔴 Critical |
| 5 | Memory leaks: `_task_map`, `_history`, `metadata`, dead-letter queue | Resource Mgmt | 🔴 Critical |
| 6 | Sync handlers block asyncio event loop — no offloading | Concurrency | 🔴 Critical |
| 7 | No persistent state — complete data loss on restart | Resource Mgmt | 🔴 Critical |
| 8 | Root-level analysis tools (DAG, error tracing) orphaned — never integrated | Integration | 🔴 Critical |
| 9 | `print()` everywhere, no structured logging, no correlation IDs | Observability | 🔴 Critical |
| 10 | Zero unit tests for scheduler, state, or queue modules | Testing | 🔴 Critical |

---

*Generated from synthesis of all 5 codebase analysis documents. Total: 45 distinct deficiencies across 7 categories.*
