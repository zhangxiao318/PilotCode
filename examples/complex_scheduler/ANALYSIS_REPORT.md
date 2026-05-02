# 调度器策略缺陷与资源管理分析报告

> 分析范围：`optimized_scheduler/scheduler.py`、`queue.py`、`registry.py`、`metrics.py`

---

## 一、总览

| 缺陷编号 | 严重级别 | 涉及文件 | 类别 |
|---------|---------|---------|------|
| D-01 | **严重** | queue.py + worker.py | 重试导致 double-add 泄漏 |
| D-02 | **严重** | registry.py + worker.py | 同步 handler 超时不可取消 |
| D-03 | **高** | queue.py | 延迟队列满时热循环 |
| D-04 | **高** | scheduler.py | 依赖关系从未检查 |
| D-05 | **中** | queue.py | PriorityQueue.task_done() 计数失衡 |
| D-06 | **中** | metrics.py | 缺少重试/超时/限流监控 |
| D-07 | **中** | scheduler.py | asyncio.Task 列表永不清理 |
| D-08 | **低** | queue.py | 缺少全局限流机制 |

---

## 二、逐项分析

### D-01（严重）：重试流程导致 _active_tasks 重复添加 & task_done 缺失

**涉及文件**：`queue.py:158-179`（fail 方法）、`worker.py:98-116`（_process_task 重试路径）

**问题描述**：

当任务执行失败且允许重试时，`worker._process_task()` 走以下路径：

```python
# worker.py 第 108-116 行
await self.queue.fail(instance, retry=True)     # ① fail(retry=True) 不从 _active_tasks 删除，不调 task_done
await asyncio.sleep(...)                         # ② 退避等待
await self.queue.submit(definition, instance)    # ③ submit() 再次加入 _active_tasks + put_nowait
```

`queue.fail(retry=True)` 的实现（queue.py:158-168）：

```python
async def fail(self, instance: TaskInstance, retry: bool = False) -> None:
    if retry:
        instance.retry_count += 1
        instance.status = TaskStatus.PENDING
        self._stats.retried += 1
        # 注意：不从 _active_tasks 删除，不调用 self._queue.task_done()
```

`queue.submit()` 的实现（queue.py:112-134）：

```python
self._queue.put_nowait(item)
async with self._lock:
    self._active_tasks[instance.instance_id] = (instance, definition)  # 重复添加！
    self._stats.current_size = len(self._active_tasks)
```

**三重重合后果**：

1. `asyncio.PriorityQueue._unfinished_tasks` 计数器永远递增（只有 get 的 +1，没有 task_done 的 -1），`queue.join()` 将永远阻塞；
2. `_active_tasks` 对同一 instance_id 重复覆盖，但原 queue item 已被消费且没有 task_done，语义混乱；
3. 若重试 N 次，计数器偏离 N，无法可靠追踪队列深度。

**风险**：长期运行后 PriorityQueue 内部计数器溢出语义错误，`join()` 永久卡死，资源追踪完全失效。

---

### D-02（严重）：同步 handler 超时不可取消 → 线程泄漏

**涉及文件**：`registry.py:52-56`、`worker.py:98-105`

**问题描述**：

`registry.execute()` 对同步 handler 使用 `run_in_executor`：

```python
# registry.py 第 52-56 行
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(
    None, lambda: handler(instance, **kwargs)  # 默认 ThreadPoolExecutor
)
```

`worker._process_task()` 用 `asyncio.wait_for()` 包裹：

```python
# worker.py 第 98-102 行
result = await asyncio.wait_for(
    self.registry.execute(definition.handler_path, instance, **definition.input_data),
    timeout=definition.execution_config.timeout_seconds,
)
```

**Python 已知限制**：`asyncio.wait_for()` 只能取消 asyncio 协程，**无法取消已提交到 ThreadPoolExecutor 的线程**。当同步 handler 超时时：

- `wait_for` 抛出 `TimeoutError`，worker 标记任务为 TIMEOUT；
- 但线程**继续在后台运行**，持有内存、锁、连接等资源；
- 线程池默认 `max_workers = min(32, os.cpu_count() + 4)`，一旦耗尽，所有后续同步任务（包括正常的）都会被阻塞。

**触发场景**：提交多个带同步 handler（如数据库查询、HTTP 请求未设超时）的任务，设置较短 timeout（如 5s），handler 实际执行 300s+。每超时一个就泄漏一个线程，最终线程池空竭。

**风险**：线程资源耗尽 → 系统级阻塞，所有同步任务积压，且无法自动恢复。

---

### D-03（高）：延迟队列满时热循环（Tight Spin）

**涉及文件**：`queue.py:239-261`（_delayed_loop）

**问题描述**：

```python
# queue.py 第 250-255 行
except asyncio.QueueFull:
    # Put back in delayed queue
    async with self._delayed_lock:
        heapq.heappush(self._delayed, (now, item))  # now = 当前时间
    break
```

当主队列满时，延迟任务被重新塞回 `_delayed`，时间戳设为 `now`（当前时间）。下一次循环（100ms 后）该任务立刻再次满足 `<= now` 条件，再次尝试 push，再次失败，再次塞回……形成：

```
100ms → pop → QueueFull → push(now) → break
100ms → pop → QueueFull → push(now) → break
...无限循环
```

**风险**：CPU 空转（每 100ms 一次无效操作），延迟任务永远无法进入主队列 → **所有延迟任务长期阻塞**。

---

### D-04（高）：任务依赖关系从未检查

**涉及文件**：`scheduler.py:115-151`（submit 方法）、`models.py:64`（dependencies 字段）

**问题描述**：

`TaskDefinition` 定义了 `dependencies: list[str]` 字段用于声明前置任务 ID，但整个调度系统中：

- `scheduler.submit()` — 不检查依赖是否满足；
- `queue.submit()` — 不检查依赖；
- `queue.get()` — 不检查依赖；
- `worker._process_task()` — 不检查依赖。

任务一旦提交就进入队列，worker 取到后直接执行，完全无视依赖关系。

**风险**：依赖图形同虚设，任务可能在依赖未完成时执行，导致数据不一致或运行时错误。

---

### D-05（中）：PriorityQueue.task_done() 调用不对称

**涉及文件**：`queue.py:150-155`（complete 方法）、`queue.py:158-179`（fail 方法）

**问题描述**：

`queue.get()` 从 `asyncio.PriorityQueue` 取出 item（内部 `_unfinished_tasks += 1`）。只有 `queue.complete()` 调用了 `self._queue.task_done()`。`queue.fail()` 无论 `retry=True/False` 都不调用 `task_done()`。

这导致：
- 非重试失败任务的 `task_done` 缺失；
- 重试任务的 `task_done` 也缺失（且被再次 `put_nowait`，计数器再次 +1）。

**风险**：任何依赖 `queue.join()` 的关闭/等待逻辑将永久阻塞。

---

### D-06（中）：MetricsCollector 缺少关键故障指标

**涉及文件**：`metrics.py`

**问题描述**：

`MetricsCollector` 记录的数据：
- `_wait_times`、`_execution_times`、`_results`（成功/失败布尔值）、`_task_times`

**缺失的指标**：
- 重试次数 / 重试率
- 超时次数 / 超时率
- 限流触发次数
- 队列满拒绝次数
- 线程池使用率
- worker 健康度趋势

`PerformanceMetrics` 中 `success_rate` 基于 `_results` 计算，但重试成功的任务在 `_results` 中如何记录完全不可见。

**风险**：运维人员无法从 metrics 中发现 D-01（重试泄漏）、D-02（线程泄漏）、D-03（热循环）等问题，监控盲区大。

---

### D-07（中）：scheduler._tasks 列表只增不减

**涉及文件**：`scheduler.py:224-242`（_scheduled_task_loop）、`scheduler.py:244-267`（_metrics_loop）

**问题描述**：

```python
# scheduler.py start() 方法
self._tasks.append(asyncio.create_task(self._scheduled_task_loop()))
self._tasks.append(asyncio.create_task(self._metrics_loop()))

# stop() 方法
for task in self._tasks:
    task.cancel()
await asyncio.gather(*self._tasks, return_exceptions=True)
# 取消后没有清理列表
```

如果 `start() → stop() → start()` 被多次调用（如测试或热重启），`_tasks` 列表不断追加新 task，旧 task（已 cancel）仍保留引用。

**风险**：内存缓慢泄漏 + 重复 stop 时尝试 cancel 已完成的 task（虽然不会崩溃，但是不良实践）。

---

### D-08（低）：全局缺少限流机制

**涉及文件**：`scheduler.py`、`queue.py`

**问题描述**：

系统没有任何限流保护：
- 无提交速率限制 — 客户端可瞬间提交 10000 个任务；
- 无执行速率限制 — worker 无 per-handler 速率限制；
- 无重试速率限制 — 失败任务可瞬间全部进入重试。

虽然 `queue.max_size` 提供背压，但仅限主队列；`_delayed` 和 `_scheduled` 堆无限增长。

**风险**：突发流量下系统可能被打垮，且没有优雅降级机制。

---

## 三、最严重场景：导致任务长期阻塞或资源泄漏

### 场景 A：重试任务永久泄漏 + join 死锁（D-01 + D-05）

```
1. 提交一个会失败且 max_retries=3 的任务
2. Worker 取出执行 → 失败 → fail(retry=True) → 无 task_done
3. Worker sleep → submit → put_nowait + _active_tasks 重复添加
4. 另一个 Worker（或同一 Worker）再次取出 → 再次失败 → 再次泄漏
5. 3 次重试后 → fail(retry=False) → 依然无 task_done
6. PriorityQueue._unfinished_tasks = 4（1 次初始 get + 3 次重试 get），task_done = 0
7. 任何调用 queue.join() 的代码永久阻塞
```

### 场景 B：同步 Handler 超时耗尽线程池（D-02）

```
1. 提交 20 个使用同步 handler 的任务，timeout=5s
2. handler 实际执行时间 600s（如未设超时的 HTTP 请求）
3. 5s 后全部超时 → 20 个线程泄漏在后台继续运行
4. 默认线程池 max_workers ≈ 12（8 核机器），第 13 个同步任务提交时阻塞
5. Worker 被阻塞在 run_in_executor，无法处理其他任务
6. 队列堆积 → 系统不可用
```

### 场景 C：延迟队列热循环死锁（D-03）

```
1. 主队列 max_size=100，已满
2. 提交 200 个延迟任务（scheduled_at = 未来时间）
3. 延迟时间到达 → _delayed_loop 尝试移入主队列
4. QueueFull → 重新塞回 _delayed，时间戳=now
5. 100ms 后再次尝试 → 再次 QueueFull → 无限循环
6. 所有延迟任务永久阻塞在 _delayed 中
7. CPU 空转
```

---

## 四、修复建议（摘要）

| 缺陷 | 建议修复方向 |
|------|-------------|
| D-01 | `fail(retry=True)` 应调用 `task_done()` 并从 `_active_tasks` 删除；`submit()` 应检查幂等性 |
| D-02 | 同步 handler 使用专用线程池 + `concurrent.futures.Future.cancel()` + 设置线程内超时 |
| D-03 | 延迟重入时加指数退避；或扩大 `_delayed` 容量；QueueFull 时阻塞等待而非塞回 |
| D-04 | 在 `queue.get()` 或 `_process_task()` 前检查依赖状态，不满足则重新入队 |
| D-05 | 所有终结路径（complete/fail/timeout）统一调用 `task_done()` |
| D-06 | 增加 `record_retry`、`record_timeout`、`record_queue_full` 方法 |
| D-07 | `stop()` 末尾清空 `_tasks` 列表；或使用 `AsyncExitStack` 管理生命周期 |
| D-08 | 增加 Token Bucket 限流器，在 `submit()` 入口检查 |
