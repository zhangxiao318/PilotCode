# 异常处理与健壮性缺陷全面审查报告

> 审查范围：项目所有 `.py` 文件，聚焦核心调度代码与入口脚本  
> 审查日期：2025-07-17  
> 审查方法：静态代码分析，逐文件检查 try-except 使用

---

## 缺陷总览

| 编号 | 严重程度 | 文件 | 缺陷类型 | 后果 |
|------|---------|------|----------|------|
| **DEFECT-1** | 🔴 CRITICAL | `run_single_instance.py` | JSON 解析无异常处理 | 程序崩溃 |
| **DEFECT-2** | 🔴 CRITICAL | `distributed_scheduler/scheduler.py` | 异常被吞没（bare print） | 静默失败 |
| **DEFECT-3** | 🔴 CRITICAL | `distributed_scheduler/worker.py` | 异常被吞没 + 裸 except | 任务丢失 |
| **DEFECT-4** | 🟠 HIGH | `distributed_scheduler/task.py` | `json.dumps` 无异常处理 | 静默崩溃 |
| **DEFECT-5** | 🟠 HIGH | `full_demo.py` | 裸 except 吞没所有异常 | 静默失败 |
| **DEFECT-6** | 🟠 HIGH | `cli.py` | 网络/文件异常被静默吞没 | 配置静默错误 |
| **DEFECT-7** | 🟡 MEDIUM | `optimized_scheduler/scheduler.py` | 通用 Exception 吞没 | 调度循环静默死掉 |
| **DEFECT-8** | 🟡 MEDIUM | `optimized_scheduler/queue.py` | 延迟队列循环吞没异常 | 延迟任务丢失 |
| **DEFECT-9** | 🟡 MEDIUM | `optimized_scheduler/state.py` | 清理循环吞没异常 | 内存泄漏 |
| **DEFECT-10** | 🟡 MEDIUM | `benchmark.py` | 零异常处理 | 基准测试崩溃 |

---

## 详细缺陷分析

---

### DEFECT-1: `run_single_instance.py` — JSON 文件加载无异常处理

**文件**: `/home/zx/mycc/PilotCode/run_single_instance.py:17-21`

```python
def load_instance_cached(instance_id: str):
    if os.path.exists(CACHE_JSON):
        with open(CACHE_JSON) as f:
            dataset = json.load(f)       # ← 可能抛出 JSONDecodeError
    else:
        from swebench.harness.utils import load_swebench_dataset
        dataset = load_swebench_dataset(...)  # ← 可能抛出网络/导入异常
    for inst in dataset:
        if inst["instance_id"] == instance_id:
            return inst
    return None
```

**问题**:
1. `json.load(f)` 没有 `try-except` 包裹。如果缓存文件损坏（半写、磁盘满、进程被杀），`json.JSONDecodeError` 会导致程序直接崩溃。
2. `load_swebench_dataset()` 涉及网络下载，无重试或超时处理。
3. 文件存在性检查 (`os.path.exists`) 与 `open()` 之间存在 TOCTOU 竞态条件。

**建议修复**:
```python
def load_instance_cached(instance_id: str):
    if os.path.exists(CACHE_JSON):
        try:
            with open(CACHE_JSON) as f:
                dataset = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARN] Cache file corrupt ({e}), re-downloading...")
            os.remove(CACHE_JSON)  # 删除损坏的缓存
            from swebench.harness.utils import load_swebench_dataset
            dataset = load_swebench_dataset(...)
    ...
```

---

### DEFECT-2: `distributed_scheduler/scheduler.py` — 调度循环异常被吞没

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/distributed_scheduler/scheduler.py:135-150`

```python
async def _scheduler_loop(self) -> None:
    while self._running:
        try:
            now = datetime.now()
            for task in self._scheduled_tasks:
                if task.scheduled_at and task.scheduled_at <= now:
                    if task.status == TaskStatus.PENDING:
                        await self.queue.submit(task)
            await asyncio.sleep(self._scheduler_interval)
        except Exception as e:
            # ISSUE: Silent failure
            print(f"Scheduler error: {e}")    # ← 只打印，不记录，不恢复
```

```python
async def _monitor_loop(self) -> None:
    while self._running:
        try:
            stats = self.workers.get_stats()
            print(f"Workers: {stats}")
            await asyncio.sleep(self._monitor_interval)
        except Exception as e:
            print(f"Monitor error: {e}")      # ← 同上
```

**问题**:
1. `except Exception` 捕获了 `asyncio.CancelledError`（Python 3.8-），导致 `stop()` 中的 `task.cancel()` 失效。
2. 异常仅被 `print()`，无日志记录、无告警、无指标递增。运维人员永远不知道调度循环出错了。
3. 循环继续运行，但内部状态可能已经不一致（例如某个 `task.scheduled_at` 比较抛了 `TypeError`）。
4. 如果 `self.queue.submit(task)` 抛出异常（如队列满时的死锁），该 task 及其之后的所有 task 都会被跳过。

**建议修复**:
```python
async def _scheduler_loop(self) -> None:
    while self._running:
        try:
            now = datetime.now()
            for task in self._scheduled_tasks:
                try:
                    if task.scheduled_at and task.scheduled_at <= now:
                        if task.status == TaskStatus.PENDING:
                            await self.queue.submit(task)
                except Exception as task_error:
                    logger.error(f"Failed to schedule task {task.id}: {task_error}")
                    self._failed_scheduling += 1
            await asyncio.sleep(self._scheduler_interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.critical(f"Scheduler loop fatal error: {e}", exc_info=True)
            await asyncio.sleep(1.0)
```

---

### DEFECT-3: `distributed_scheduler/worker.py` — Worker 异常处理导致任务静默丢失

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/distributed_scheduler/worker.py:64-75`

```python
async def _run_loop(self) -> None:
    while self._running:
        try:
            task = await self.queue.get()
            if task is None:
                await asyncio.sleep(self.poll_interval)
                continue
            self.current_task = task
            self.last_heartbeat = datetime.now()
            await self._execute_task(task)
            self.tasks_processed += 1
            self.current_task = None
        except Exception as e:
            # ISSUE: Catches everything, may hide bugs
            print(f"Worker error: {e}")
            await asyncio.sleep(self.poll_interval)
```

**问题**:
1. **最严重**: 如果 `self.queue.get()` 成功返回了一个 task，但随后 `await self._execute_task(task)` 之前的任何代码抛出异常，该 task **已经被从队列中取出但永远不会被标记为完成或失败**。这是一个经典的 at-least-once 语义破坏。
2. 异常后 `self.current_task` 保持为旧值，`self.last_heartbeat` 不更新，导致健康检查误报。
3. `except Exception` 同样捕获 `CancelledError`，阻止优雅关闭。
4. `self.tasks_processed` 不递增但 task 已从队列移除，指标失真。

**特别危险的代码路径** (`_execute_task`):
```python
async def _execute_task(self, task: Task) -> None:
    try:
        ...
        if asyncio.iscoroutinefunction(task.handler):
            result = await task.handler(*task.args, **task.kwargs)
        else:
            result = task.handler(*task.args, **task.kwargs)  # ← 同步调用阻塞事件循环！
        await self.queue.complete(task, result)
    except Exception as e:
        error_msg = str(e)
        task.error_traceback = traceback.format_exc()
        await self.queue.fail(task, error_msg)
        self.tasks_failed += 1
```

**问题**: 同步 handler 直接调用会阻塞整个事件循环。如果同步 handler 耗时 10 秒，该 worker 在 10 秒内无法处理任何其他任务。应该使用 `run_in_executor`。

**建议修复**:
```python
async def _run_loop(self) -> None:
    while self._running:
        task = None
        try:
            task = await self.queue.get()
            if task is None:
                await asyncio.sleep(self.poll_interval)
                continue
            self.current_task = task
            self.last_heartbeat = datetime.now()
            await self._execute_task(task)
            self.tasks_processed += 1
        except asyncio.CancelledError:
            if task is not None:
                await self.queue.fail(task, "Worker cancelled")
            raise
        except Exception as e:
            logger.error(f"Worker {self.worker_id} error: {e}", exc_info=True)
            if task is not None:
                await self.queue.fail(task, f"Worker error: {e}")
                self.tasks_failed += 1
            await asyncio.sleep(self.poll_interval)
        finally:
            self.current_task = None
```

---

### DEFECT-4: `distributed_scheduler/task.py` — `to_json()` 无异常处理

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/distributed_scheduler/task.py:85-87`

```python
def to_json(self) -> str:
    """ISSUE: No error handling for non-serializable data."""
    return json.dumps(self.to_dict())
```

**问题**:
1. `to_dict()` 包含 `list(self.args)` 和 `dict(self.kwargs)`。如果 `args` 包含 `bytes`、`set`、`datetime`、自定义对象等不可 JSON 序列化的类型，`json.dumps()` 抛出 `TypeError`。
2. 没有任何 try-except 包裹，调用者如果依赖这个方法（如持久化 state、发送到网络），会直接崩溃。
3. `result` 字段使用 `str(self.result)` 作为退化方案，但这可能产生不可解析的字符串。

**建议修复**:
```python
def to_json(self, default=str) -> str:
    try:
        return json.dumps(self.to_dict(), default=default)
    except (TypeError, ValueError) as e:
        # Fallback: serialize only safe fields
        safe = {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "error": str(e),
        }
        return json.dumps(safe)
```

---

### DEFECT-5: `full_demo.py` — 裸 except 吞没所有异常

**文件**: `/home/zx/mycc/PilotCode/full_demo.py:58-60`

```python
try:
    sample = None
    if tool.name == "Bash":
        from pilotcode.tools.bash_tool import BashInput
        sample = BashInput(command="echo test")
    elif tool.name in ["FileRead", "FileWrite", "FileEdit"]:
        sample = tool.input_schema(file_path="test.txt")
    elif "Task" in tool.name:
        from pilotcode.tools.task_tools import TaskCreateInput
        sample = TaskCreateInput(description="test")
    is_ro = tool.is_read_only(sample) if sample else False
    is_c = tool.is_concurrency_safe(sample) if sample else False
except:          # ← 裸 except，捕获 KeyboardInterrupt、SystemExit 等
    is_ro = False
    is_c = False
```

**问题**:
1. `except:` (裸 except) 捕获所有异常，包括 `KeyboardInterrupt`、`SystemExit`、`GeneratorExit`、`MemoryError`。这是 Python 中最危险的反模式之一。
2. 即使只是某个工具类的构造器签名变更导致 `TypeError`，也会被静默吞没，表格中该工具显示为 `is_ro=False, is_c=False`，用户无法区分"不支持"和"代码bug"。
3. 调试极其困难：没有任何日志输出。

**建议修复**:
```python
try:
    ...
except Exception as e:
    logger.debug(f"Failed to probe tool {tool.name}: {e}")
    is_ro = False
    is_c = False
```

---

### DEFECT-6: `cli.py` — 多处异常被静默吞没

**文件**: `/home/zx/mycc/PilotCode/src/pilotcode/cli.py`

**6a. `_is_local_url` (line 63-65)**:
```python
try:
    host = urlparse(url).hostname or ""
except Exception:
    return False      # ← 静默吞没，将无效 URL 视为非本地
```

**问题**: URL 解析失败的真正原因被隐藏。如果传入的 URL 是空字符串或格式错误，应该让调用者知道。

**6b. `check_configuration` (line 207-210)**:
```python
except Exception as e:
    console.print(f"[yellow]Warning: Could not verify LLM: {e}[/yellow]")
    return True         # ← 静默降级为"已配置"
```

**问题**: 如果验证过程失败（例如配置文件损坏、SSL 证书错误），程序直接假设配置可用并继续。这可能导致后续 LLM 调用以更隐晦的方式失败。

**6c. `_probe_and_update_local_config` (line 289)**:
```python
except Exception as e:
    console.print(f"[dim]Could not probe local model: {e}[/dim]")
    # ← 无后续处理，静默忽略
```

**6d. `_quick_probe` (line 305-308)**:
```python
except Exception as e:
    err = str(e)[:120]
    console.print(f"[dim]  ✗ Error: {err}[/dim]")
    return False, err
```

**问题**: 虽然这里返回了 `(False, err)`，但调用方（`main` 函数）在所有情况下都会继续启动程序，只有用户手动选择"不继续"才会退出。

---

### DEFECT-7: `optimized_scheduler/scheduler.py` — 调度循环吞没异常

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/optimized_scheduler/scheduler.py:242-258`

```python
async def _scheduled_task_loop(self) -> None:
    while self._running:
        try:
            ...
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            break
        except Exception:               # ← 通用异常吞没
            await asyncio.sleep(1.0)    # ← 无日志
```

**问题**: 虽然比旧版多了 `CancelledError` 的正确处理，但 `except Exception` 仍然吞没所有未预期的错误。没有日志、没有告警、没有指标。

**同样的问题出现在**:
- `_metrics_loop` (line 273-278): `except Exception: await asyncio.sleep(1.0)`
- `queue.py:_delayed_loop` (line 268-270): `except Exception: await asyncio.sleep(1.0)`
- `state.py:_cleanup_loop` (line 168-170): `except Exception: await asyncio.sleep(60.0)`
- `metrics.py:_collect_loop` (line 150-152): `except Exception: await asyncio.sleep(1.0)`
- `worker.py:_auto_scale` (line 274-276): `except Exception: await asyncio.sleep(1.0)`

**共 6 处相同的反模式**，分布在 optimized_scheduler 的多个模块中。

---

### DEFECT-8: `optimized_scheduler/queue.py` — 延迟队列满时任务可能丢失

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/optimized_scheduler/queue.py:256-262`

```python
for item in ready:
    self._sequence += 1
    item.sequence = self._sequence
    try:
        self._queue.put_nowait(item)       # ← QueueFull 可能
    except asyncio.QueueFull:
        async with self._delayed_lock:
            heapq.heappush(self._delayed, (now, item))  # ← 重新推入延迟队列
        break
```

**问题**: 当主队列满时，已准备好的延迟任务被重新推入延迟队列，时间戳设为 `now`。下一个循环周期（100ms 后）会再次尝试。但如果在高负载下：`put_nowait` 持续失败 → 这些任务被无限延迟 → start_time 越来越不准确。应该使用带超时的 `put()` 或增加指数退避。

---

### DEFECT-9: `optimized_scheduler/state.py` — `MemoryBackend.get_by_status` 缺乏一致性保护

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/optimized_scheduler/state.py:73-76`

```python
async def get_by_status(self, status: TaskStatus) -> list[TaskInstance]:
    async with self._lock:
        ids = list(self._by_status.get(status, []))
        return [self._tasks[i] for i in ids if i in self._tasks]
```

**问题**: 虽然用 `async with self._lock` 保护了读取，但 `if i in self._tasks` 的防御性检查说明了设计上已经预期到不一致的可能。在极高并发下，`_by_status` 和 `_tasks` 之间可能短暂不一致，但当前代码只做了静默丢弃——没有任何日志记录这种异常情况。

---

### DEFECT-10: `benchmark.py` — 完全无异常处理

**文件**: `/home/zx/mycc/PilotCode/examples/complex_scheduler/benchmark.py:42-44`

```python
if __name__ == "__main__":
    asyncio.run(benchmark_throughput())
```

**问题**:
1. 没有任何 try-except。如果 `scheduler.start()` 失败（例如端口冲突）、任何 task 的 handler 抛出未捕获异常、`scheduler.stop()` 失败——整个脚本崩溃且没有任何诊断信息。
2. `await asyncio.sleep(2.0)` 是一个"猜测"的等待时间，没有实际的完成检测机制。如果调度器慢于预期，基准测试会得到错误的结果；如果快于预期，会浪费时间。

---

## 共性问题总结

| 反模式 | 出现次数 | 影响 |
|--------|---------|------|
| `except Exception: print(...)` 吞没异常 | 4 处 | 静默失败，无告警 |
| `except Exception: await asyncio.sleep(N)` 吞没异常 | 6 处 | 后台循环静默死掉 |
| `except:` 裸 except | 1 处 | 捕获系统级异常 |
| `json.load/dumps` 无异常处理 | 3 处 | 程序崩溃 |
| 文件 I/O 无异常处理 | 4 处 | 程序崩溃 |
| `asyncio.CancelledError` 被 `except Exception` 错误捕获 | 3 处 | 优雅关闭失效 |

## 优先级建议

1. **立即修复**: DEFECT-1, DEFECT-2, DEFECT-3 — 这些会导致程序崩溃或任务静默丢失。
2. **尽快修复**: DEFECT-4, DEFECT-5, DEFECT-6 — 这些在特定条件下触发崩溃。
3. **计划修复**: DEFECT-7 ~ DEFECT-10 — 这些在极端情况下才会触发，但应加入日志和告警。
