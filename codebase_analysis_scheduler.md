# Complex Scheduler — Codebase Analysis

> Generated: 2026-04-26 | Scope: `examples/complex_scheduler/`

---

## 1. Overview

The complex_scheduler directory contains two task-scheduling implementations:

| Variant | Path | Intent |
|---|---|---|
| **Distributed Scheduler** | `distributed_scheduler/` | Initial implementation with intentional design issues for refactoring |
| **Optimized Scheduler** | `optimized_scheduler/` | Production-grade rewrite addressing those issues |

Both follow a layered architecture: **Task definition → Queue → Worker pool → Scheduler → State/Metrics**.

---

## 2. Distributed Scheduler (v1)

### 2.1 Component Map

| Module | Responsibility | Lines |
|---|---|---|
| `task.py` | Task data model, priority/status enums, sub-task hierarchies | 138 |
| `queue.py` | Priority queue with delay/dead-letter sub-queues | 129 |
| `worker.py` | Single worker + fixed-size pool | 162 |
| `scheduler.py` | Orchestrator: submit, scheduling loop, monitor loop | 173 |
| `state.py` | In-memory state tracking with history | 102 |
| `__init__.py` | Public API exports | 19 |

### 2.2 Architecture

```
                    ┌─────────────────────────┐
                    │     TaskScheduler        │  ← God class
                    │  - submit/submit_sched.  │
                    │  - submit_chain/parallel │
                    │  - _scheduler_loop()     │
                    │  - _monitor_loop()       │
                    └───┬───────┬───────┬──────┘
                        │       │       │
              ┌─────────▼┐  ┌───▼───┐  ┌▼──────────┐
              │TaskQueue │  │Worker │  │StateManager│
              │(heapq)   │  │ Pool  │  │(mem only)  │
              └──────────┘  └───────┘  └────────────┘
```

- **Monolithic**: `TaskScheduler` creates its own dependencies internally — `TaskQueue`, `WorkerPool`, `StateManager` are hard-wired, not injected.
- **Scheduler** owns three special-task registries (`_scheduled_tasks`, `_chained_tasks`, `_parallel_tasks`) in addition to queue orchestration.
- **WorkerPool** creates a fixed number of `Worker` instances at start; no dynamic scaling.

### 2.3 Concurrency Model

- **Primitive**: `asyncio.Lock` with `asyncio.Condition` wrappers (`_not_empty`, `_not_full`).
- **Busy-waiting**: Worker polls at `poll_interval=0.1s` when queue is empty.
- **Synchronous handlers block the event loop**: In `_execute_task()`, sync callables run on the asyncio thread with no `run_in_executor`.
- **No graceful shutdown**: `Worker.stop()` cancels the loop task but doesn't wait for the current task to complete, leaving it in an unknown state.
- **Silent exception swallowing**: `_scheduler_loop` and `_monitor_loop` catch all exceptions and `print()` them.
- **No backoff**: Workers re-poll at fixed interval on errors.

### 2.4 State Management

- `StateManager` stores everything in plain `dict` and `defaultdict`, all in memory — no persistence.
- `_history` grows unbounded (full timeline per task, never trimmed).
- `get_tasks_by_status()` does a **linear scan** over all tasks.
- `cleanup()` modifies a dict while iterating (via `list(keys())` pattern) — no atomicity guarantees.
- `_counters` are simple integers, no time-series or rate tracking.

### 2.5 Scheduling Algorithm

- **Polling-based**: `_scheduler_loop` runs at `1.0s` interval, linearly scanning `_scheduled_tasks` list.
- **Priority queue**: Uses `heapq` with negated priority value. Priority inversion possible because all tasks with same priority are not FIFO-ordered.
- **Delay queue**: `_delay_queue` is a `deque` separate from the heap — not integrated with priority ordering.
- **Retry**: Exponential backoff (`retry_delay * 2^retry_count`) with blocking `asyncio.sleep()` inside `fail()`.
- **Dead-letter queue**: Unbounded list — no pagination, no max size.
- **Chain/Parallel**: Dependencies tracked bidirectionally in `Task` dataclass via `dependencies`/`dependents` lists; no cycle detection.

### 2.6 Key Issues (Intentional)

1. Task `dataclass` mixes handler callables with serialisable fields — can't JSON-serialize properly.
2. `to_dict()` includes `str(self.handler)` and `str(self.result)` as fallbacks.
3. No timeout enforcement for individual task execution.
4. Memory leak: completed tasks remain in `_task_map` in the queue.
5. `QueueStats` returned as raw internal dict (exposes mutable internals).
6. `ScheduledTask`, `ChainedTask`, `ParallelTask` abuse inheritance from `Task`.

---

## 3. Optimized Scheduler (v2)

### 3.1 Component Map

| Module | Responsibility | Lines |
|---|---|---|
| `models.py` | Pydantic models: `TaskDefinition`, `TaskInstance`, `TaskResult`, `ExecutionConfig` | 179 |
| `queue.py` | `asyncio.PriorityQueue`-based queue with delayed-task heap and stats | 277 |
| `worker.py` | `Worker` + `WorkerPool` with auto-scaling and graceful shutdown | 295 |
| `scheduler.py` | `OptimizedScheduler` with config injection and scheduled-task heap | 284 |
| `state.py` | Pluggable backend (`StateBackend` ABC, `MemoryBackend`) + `StateManager` | 172 |
| `registry.py` | `TaskRegistry` singleton — decouples task definitions from handlers | 134 |
| `metrics.py` | `MetricsCollector` with percentile calculation and circular buffers | 156 |
| `__init__.py` | API exports + version `2.0.0` | 58 |

### 3.2 Architecture

```
               ┌─────────────────────────────────┐
               │       OptimizedScheduler         │
               │  (SchedulerConfig injected)      │
               └──┬──────────┬──────────┬─────────┘
                  │          │          │
       ┌──────────▼┐  ┌──────▼──────┐  ┌▼──────────────┐
       │ TaskQueue  │  │ WorkerPool  │  │ StateManager  │
       │(PriQueue)  │  │(auto-scale) │  │(pluggable BE) │
       └────────────┘  └─────────────┘  └───────────────┘
              │               │                │
       ┌──────▼──────┐ ┌──────▼──────┐  ┌──────▼──────┐
       │TaskRegistry │ │  Metrics    │  │StateBackend │
       │(singleton)  │ │  Collector  │  │  (ABC)      │
       └─────────────┘ └─────────────┘  └─────────────┘
```

### 3.3 Concurrency Model

- **`asyncio.PriorityQueue`**: Native async queue with built-in thread safety and backpressure (`put_nowait`/`QueueFull`).
- **Event-driven architecture**: Workers use `queue.get(timeout=1.0)` instead of busy-polling. Queue internally uses `asyncio.Event` for notification.
- **`asyncio.Lock`** for shared mutable state (delayed heap, active-task map, worker pool registry).
- **`asyncio.wait_for`** for per-task timeout enforcement.
- **Graceful shutdown**: `stop()` sets `_stop_event`, cancels tasks, `asyncio.gather` with `return_exceptions=True`.
- **Thread-pool offloading**: `registry.execute()` detects sync handlers and runs them via `loop.run_in_executor(None, ...)`.
- **Auto-scaling loop**: `WorkerPool._auto_scale()` runs at cooldown interval, uses fill-ratio thresholds (0.8 up, 0.3 down).

### 3.4 Models & Serialization

- **Separation of immutable/mutable state**:
  - `TaskDefinition` (`ConfigDict(frozen=True)`) — immutable task blueprint with Pydantic validation.
  - `TaskInstance` (`ConfigDict(validate_assignment=True)`) — mutable runtime state.
  - `TaskResult` (`ConfigDict(frozen=True)`) — immutable execution outcome.
- **No callables in models**: `handler_path: str` stored instead of the function itself — resolved at runtime via `TaskRegistry`.
- **`ExecutionConfig`** encapsulates timeout, retry, backoff, resource limits as a frozen config object.
- **Computed properties**: `execution_time_ms`, `wait_time_ms`, `is_terminal` derived from timestamps.

### 3.5 State Management

- **`StateBackend` ABC** defines abstract interface: `save`, `get`, `get_by_status`, `delete`, `cleanup`.
- **`MemoryBackend`**: In-memory implementation with `asyncio.Lock` and `dict[TaskStatus, set[str]]` index for O(1) status lookups.
- **`StateManager`**: High-level wrapper with caching stats and periodic cleanup loop (`_cleanup_loop` every 5 min).
- Cleanup iterates only on `is_terminal` tasks with a stale `completed_at` — safe for large datasets.

### 3.6 Scheduling Algorithm

- **Dual-heap architecture**:
  1. **Main priority heap** (`asyncio.PriorityQueue[QueueItem]`): Immediate tasks, priority-ordered with sequence tie-breaker for FIFO.
  2. **Delayed heap** (`list[tuple[datetime, QueueItem]]`): Future-scheduled tasks sorted by `scheduled_at`. A background coroutine (`_delayed_loop`) at 100ms polls and moves ready items.
- **Dynamic scheduling interval**: `_scheduled_task_loop` computes `wait_time` from the next scheduled task's delta, capped at 1.0s, with `asyncio.wait_for`.
- **Retry logic in worker**: Max retries configurable, exponential backoff `retry_delay * multiplier^retry_count`, async sleep between retries, resubmit via `queue.submit()`.
- **Timeout**: `asyncio.wait_for(registry.execute(...), timeout=exec_config.timeout_seconds)` — sets status to `TIMEOUT` on expiry.

### 3.7 Metrics & Observability

- **`MetricsCollector`**: Circular buffers (deque, maxlen=1000) for wait times, execution times, result booleans.
- **Percentile calculation**: Linear interpolation for p50/p99 on sorted snapshots.
- **Throughput**: Tasks per second computed over trailing 60-second window.
- **Callbacks**: `add_callback()` supports external metrics sinks.
- **`_metrics_loop`**: Periodic aggregation combining queue stats + worker stats into `PerformanceMetrics`.

### 3.8 Key Improvements over v1

| Concern | v1 (Distributed) | v2 (Optimized) |
|---|---|---|
| **Serialization** | `dataclass` with callables, `str()` fallback | Pydantic `BaseModel`, `handler_path` string |
| **Queue primitives** | Manual `heapq` + `Condition` | `asyncio.PriorityQueue` |
| **FIFO ordering** | Not guaranteed at same priority | `sequence` tie-breaker field |
| **Timeout enforcement** | None | `asyncio.wait_for` per task |
| **Sync handler safety** | Blocks event loop | `run_in_executor` |
| **State persistence** | Memory-only, no interface | Pluggable `StateBackend` ABC |
| **Status indexing** | Linear scan `O(n)` | `dict[TaskStatus, set[id]]` — `O(1)` |
| **Worker scaling** | Fixed at startup | Auto-scale based on fill ratio |
| **Graceful shutdown** | Cancels task immediately | Awaits in-progress work, configurable timeout |
| **Metrics** | `print()` to stdout | Percentile buffers, callbacks, structured snapshots |
| **Dependency injection** | Internal construction | Constructor injection of config, backend, registry |
| **Delayed tasks** | Separate `deque`, not priority-aware | Heap sorted by `scheduled_at` |

---

## 4. Comparative Summary

| Dimension | Distributed Scheduler | Optimized Scheduler |
|---|---|---|
| **Architecture** | Monolithic god class, hard-wired deps | Clean DI, pluggable backends |
| **Concurrency** | `asyncio.Condition`, busy-wait, sync blocking | `asyncio.PriorityQueue`, `run_in_executor`, event-driven |
| **State** | Plain dicts, no index, unbounded history | ABC backend, status-indexed, periodic cleanup |
| **Models** | Dataclass with callables, no validation | Pydantic frozen/mutable split, `handler_path` |
| **Scheduling** | Polling every 1s, linear scan | Event-driven with heap, dynamic wait interval |
| **Observability** | Ad-hoc prints | Structured `PerformanceMetrics`, percentiles, callbacks |
| **Resilience** | No timeout, silent errors | Per-task timeout, `TimeoutError` status, retry backoff |
| **Scalability** | Fixed worker count | Auto-scale with fill-ratio thresholds |
