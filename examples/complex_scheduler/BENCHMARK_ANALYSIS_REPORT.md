# 性能基准与资源消耗综合分析报告

> **分析对象**: `examples/complex_scheduler/benchmark.py`  
> **对比对象**: `distributed_scheduler` vs `optimized_scheduler`  
> **分析日期**: 2025-01-21

---

## 一、总体评价：benchmark.py 设计存在致命缺陷

**综合评分: 1/10** — 该基准测试在当前形态下**不能产生任何有意义的性能数据**，更无法用于对比两个调度器。

### 致命问题一览

| 严重度 | 问题 | 影响 |
|--------|------|------|
| 🔴 致命 | 使用 `await asyncio.sleep(2.0)` 替代真正的任务完成等待 | 吞吐量数据完全无效 |
| 🔴 致命 | 只测试 `distributed_scheduler`，从未导入或测试 `optimized_scheduler` | 无法对比 |
| 🔴 致命 | 两个调度器 API 完全不兼容，即使想对比也无法直接替换 | 对比不可行 |
| 🟠 严重 | 无预热阶段，冷启动成本混入测量 | 数据偏悲观 |
| 🟠 严重 | 单次运行，无统计显著性 | 无法判断是否偶然 |
| 🟡 中等 | 仅覆盖 100 个 1ms 微任务这一种场景 | 场景覆盖极窄 |

---

## 二、逐行剖析 benchmark.py

### 2.1 虚假等待 — 最严重问题

```python
# benchmark.py 第 22-32 行
tasks = []
for i in range(num_tasks):
    task = await scheduler.submit(dummy_task, 0.001)
    tasks.append(task)

# 等待完成 — 问题: 没有任何真正的完成等待机制
await asyncio.sleep(2.0)          # ← 硬编码 sleep!

elapsed = time.time() - start
throughput = num_tasks / elapsed  # ← 这个数字毫无意义
```

**为什么这是致命缺陷：**

1. **如果任务在 0.5s 内全部完成**，则 `elapsed` 包含 1.5s 的死等待时间，吞吐量被严重低估。
   - 真实吞吐: 100/0.5 = 200 tasks/s
   - 测量吞吐: 100/2.0 = 50 tasks/s（**偏差 -75%**）

2. **如果任务在 3s 才完成**，则 sleep 结束时任务尚未完成，但 benchmark 已停止计时。
   - 测量吞吐偏高，且统计了未完成的任务。

3. **distributed scheduler 的 `submit()` 是异步非阻塞的**，提交 100 个任务本身只需几毫秒，但 `start()` 创建 worker 的开销、队列竞争、任务执行时间全部未知。2 秒是否足够？——**无法确定**。

4. **未验证完成数量**。没有调用 `get_stats()` 或 `scheduler.queue.get_stats()` 来检查实际完成了多少任务。可能 30% 的任务还卡在队列里就报告"完成"了。

### 2.2 只测一个调度器，标题暗示"对比"

```python
# benchmark.py 第 6 行
from distributed_scheduler import TaskScheduler, TaskPriority
#                           ↑ 只导入旧版，从未导入 optimized_scheduler
```

文件名叫 `benchmark.py`，上下文是 `distributed` vs `optimized` 的对比，但代码中：
- 没有 `from optimized_scheduler import OptimizedScheduler`
- 没有 A/B 对比运行
- 没有输出新旧差异

### 2.3 API 不兼容 — 对比在根本上不可行

两个调度器的 `submit()` 签名完全不同：

```python
# distributed scheduler — 直接传 callable
await scheduler.submit(dummy_task, 0.001)

# optimized scheduler — 需要 name + handler_path + registry
await scheduler.submit(
    name="benchmark-task",
    handler_path="benchmark.dummy",  # 需要先在 registry 注册
    input_data={"duration": 0.001},
)
```

这意味着：
- 不能简单替换 import 来做 A/B 测试
- `optimized_scheduler` 强制使用 `TaskRegistry` 注册 handler，benchmark 无法直接用 callable
- 任何对比都需要**重写 benchmark 代码**以适配两个 API

### 2.4 无预热（Warmup）

```python
async def benchmark_throughput():
    scheduler = TaskScheduler(min_workers=4, max_workers=4)
    await scheduler.start()       # ← 冷启动：创建 worker、启动 event loop tasks
    try:
        start = time.time()       # ← 立即开始计时，包含 JIT/缓存预热开销
```

Python 的 asyncio event loop、对象分配、worker coroutine 调度都有首次运行开销。标准做法是：
1. 先跑一轮不计时（warmup）
2. 再跑 N 轮计时取平均

### 2.5 单次运行，无统计

- 只跑 1 次，无 `min/max/avg/stddev/p50/p99`
- 无法判断结果是否稳定
- 无法检测异常值（如 GC 暂停导致的偶发延迟）

### 2.6 场景覆盖极窄

| 场景 | 是否覆盖 | 为什么重要 |
|------|---------|-----------|
| 100 个 1ms 微任务 | ✅ 唯一场景 | 过于简单 |
| 高并发 (1000+ 任务) | ❌ | 测试队列扩展性 |
| 长任务 (1s+) | ❌ | 测试 worker 不阻塞 |
| 混合优先级 | ❌ | 测试优先级调度正确性 |
| 突发提交 (burst) | ❌ | 测试背压和动态扩缩 |
| 定时任务 | ❌ | 测试 heap 调度 vs 轮询 |
| 链式/并行任务 | ❌ | 测试依赖解析 |
| 内存压力测试 | ❌ | 测试 `_task_map` 泄漏 |

---

## 三、分布式调度器性能瓶颈分析

通过代码审查识别出的实际性能问题：

### 3.1 队列层

```python
# queue.py - 手动管理 asyncio.Lock + Condition
self._lock = asyncio.Lock()
self._not_empty = asyncio.Condition(self._lock)
self._not_full = asyncio.Condition(self._lock)
```

- 使用 `list` + `heapq` 而非 `asyncio.PriorityQueue`，需要手动加锁
- `Condition` 嵌套在同一个 `Lock` 上，通知时持有锁 → **惊群效应**
- `_task_map` 从不清理 → 内存泄漏，随任务数线性增长
- `complete()` 不删 `_task_map` 条目 → 泄漏确认

### 3.2 Worker 层

```python
# worker.py - 轮询间隔 100ms
self.poll_interval = 0.1  # ← 对比 optimized 的 10ms
```

- 100ms 轮询间隔意味着空队列时响应延迟至少 100ms
- `_run_loop` 中 `except Exception` 吞掉所有异常
- `_execute_task` 无超时控制，长任务会永久占用 worker
- `WorkerPool.stop()` 是**串行**停止：`for worker in self.workers: await worker.stop()`

### 3.3 调度器层

```python
# scheduler.py - 两个后台轮询循环
self._tasks.append(asyncio.create_task(self._scheduler_loop()))  # 1s 间隔轮询
self._tasks.append(asyncio.create_task(self._monitor_loop()))    # 5s 间隔打印
```

- `_scheduler_loop` 每秒线性扫描所有定时任务 → O(n) 每 1s
- `_monitor_loop` 只是 `print()`，无实际监控价值但消耗资源
- `stop()` 中 `asyncio.gather(*self._tasks)` 若一个 task 已异常则可能丢失其他 task 的取消

### 3.4 预期性能损失汇总

| 瓶颈 | 机制 | 预期影响 |
|------|------|---------|
| list + heapq + 手动锁 | 队列操作 | ~2-3x 慢于 asyncio.PriorityQueue |
| 100ms 轮询 | worker 空闲等待 | 空载时 100ms 额外延迟 |
| `_task_map` 泄漏 | 内存 | 长时间运行内存持续增长 |
| 串行 stop | worker 关闭 | N 个 worker 停止时间 = N × 单 worker 停止时间 |
| 无超时 | 任务执行 | 一个慢任务阻塞整个 worker |
| 固定 sleep(2.0) | 基准测试 | 测量值无效，见第二节 |

---

## 四、优化版调度器的性能改进

### 4.1 已解决的瓶颈

| 旧版问题 | 优化版方案 | 改进幅度 |
|---------|-----------|---------|
| list+heapq+手动锁 | `asyncio.PriorityQueue`（C 实现） | 显著 |
| 100ms 轮询 | 10ms + `asyncio.wait_for` 超时 | 响应快 10x |
| 串行 stop | `asyncio.gather(*workers)` 并行 | N 倍加速 |
| 无任务超时 | `asyncio.wait_for(..., timeout=)` | 避免永久阻塞 |
| `_task_map` 不清理 | `del self._active_tasks[id]` | 消除泄漏 |
| 无背压 | `put_nowait` + `QueueFull` 异常 | 可预测行为 |
| 固定轮询调度 | heap 定时 + 动态 sleep | O(log n) 替代 O(n) |

### 4.2 优化版新增的基准测试能力

优化版内置了 `MetricsCollector`，支持：
- `record_task_complete(wait_time_ms, execution_time_ms, success)` — 精确记录
- 百分位延迟 (p50, p99)
- 吞吐量 (tasks/sec over sliding window)
- 成功率

这些都是 benchmark.py 完全缺失的能力。

---

## 五、虚假优化检测（是否符合"抢跑/虚假优化"判断标准）

### 5.1 什么是"抢跑"（benchmark cheating）

"抢跑"指基准测试在设计上偏向某一实现，例如：
- 测试 A 时包含冷启动，测试 B 时用预热数据
- 测试 A 在慢机器上跑，B 在快机器上跑
- 故意选择对 A 不利的 workload

### 5.2 当前 benchmark 是否存在抢跑？

**不存在传统意义的"抢跑"，因为没有对比**。benchmark.py 只测了一个调度器，所以不存在偏向问题。

但如果有人**试图用这个 benchmark 来"证明" optimized 比 distributed 好**，那就存在严重的**测量偏差**：

| 偏差类型 | 具体情况 |
|---------|---------|
| **固定 sleep 偏差** | `sleep(2.0)` 对不同调度器掩盖真实差异。假设 distributed 用 0.6s 完成，optimized 用 0.3s 完成，两者测量值都是 `100/2.0=50 tasks/s` |
| **API 切换偏差** | 切换到 optimized 需要重写 benchmark，任何改动都可能引入新偏差 |
| **无统计偏差** | 单次运行受系统负载波动影响极大 |

### 5.3 判断

- **不存在故意抢跑**：benchmark 没有"偏向"任何一方，因为它根本没有做对比
- **存在严重的测量无效性**：`sleep(2.0)` 使得任何吞吐量数字都不可信
- **如果要在当前形态下对比**：结果将是**虚假等价**——两个调度器都会显示 50 tasks/s（因为 `sleep(2.0)` 占主导），完全抹杀性能差异

---

## 六、修复建议

### 6.1 最小修复（使当前 benchmark 可用）

```python
async def benchmark_throughput():
    scheduler = TaskScheduler(min_workers=4, max_workers=4)
    await scheduler.start()

    # 预热
    for _ in range(10):
        await scheduler.submit(dummy_task, 0.001)
    await asyncio.sleep(0.5)

    try:
        num_tasks = 100
        start = time.perf_counter()  # 使用 perf_counter 而非 time.time

        tasks = []
        for i in range(num_tasks):
            task = await scheduler.submit(dummy_task, 0.001)
            tasks.append(task)

        # 真正等待所有任务完成
        timeout = 30.0
        deadline = time.perf_counter() + timeout
        while True:
            stats = scheduler.queue.get_stats()
            if stats["completed"] + stats["failed"] >= num_tasks:
                break
            if time.perf_counter() > deadline:
                print(f"WARNING: timeout after {timeout}s, "
                      f"completed={stats['completed']}, failed={stats['failed']}")
                break
            await asyncio.sleep(0.01)  # 10ms 轮询

        elapsed = time.perf_counter() - start
        throughput = num_tasks / elapsed
        stats = scheduler.queue.get_stats()

        print(f"Tasks: submitted={num_tasks}, "
              f"completed={stats['completed']}, failed={stats['failed']}")
        print(f"Time: {elapsed:.3f}s, Throughput: {throughput:.1f} tasks/sec")

    finally:
        await scheduler.stop()
```

### 6.2 完整修复（生产级 benchmark）

需要覆盖以下维度：

1. **多场景**: 微任务 / 长任务 / 混合优先级 / 突发 / 高并发
2. **统计 rigor**: 每种场景跑 10+ 轮，报告 mean ± stddev
3. **双调度器**: 统一适配层后对比 distributed vs optimized
4. **资源监控**: 记录内存峰值、asyncio task 数量
5. **正确等待**: 使用 `get_stats()` 轮询 + 超时，而非 `sleep(2.0)`
6. **预热**: 每种场景先跑 1 轮不计时
7. **隔离**: 每次运行前后清理状态，避免交叉污染

### 6.3 统一 API 适配层

由于两个调度器 API 不同，需要一个适配层：

```python
# 统一接口
class SchedulerAdapter:
    async def start(self): ...
    async def stop(self): ...
    async def submit_task(self, duration: float) -> str: ...  # 返回 task_id
    async def wait_all(self, task_ids: list[str], timeout: float) -> dict: ...  # 返回 stats

class DistributedAdapter(SchedulerAdapter):
    # 封装 TaskScheduler

class OptimizedAdapter(SchedulerAdapter):
    # 封装 OptimizedScheduler + 自动注册 handler
```

---

## 七、结论

| 维度 | 结论 |
|------|------|
| benchmark 能否产生有效数据？ | ❌ 不能。`sleep(2.0)` 使数据无效 |
| benchmark 能否对比两个调度器？ | ❌ 不能。只测了一个，且 API 不兼容 |
| 是否存在抢跑/虚假优化？ | 不存在抢跑（因为没有对比），但测量方法本身会产生**虚假等价** |
| distributed 有性能瓶颈吗？ | ✅ 有。队列锁竞争、100ms 轮询、内存泄漏、串行 stop |
| optimized 改进了吗？ | ✅ 是。asyncio.PriorityQueue、10ms 轮询、并行 stop、超时控制 |
| 代码层面能看出性能差异吗？ | ✅ 可以。但 benchmark 无法验证，需要重写 |
| 建议 | **彻底重写 benchmark.py**，按第六节方案进行 |

**一句话总结**: `benchmark.py` 当前形态是一个**安慰剂基准测试**——它会产生数字，但这些数字与调度器的真实性能无关。`sleep(2.0)` 主导了测量结果，使得两个调度器无论实际快慢都会显示相似的"吞吐量"。
