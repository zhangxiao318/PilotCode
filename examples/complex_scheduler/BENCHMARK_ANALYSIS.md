# 性能基准与资源消耗综合分析

> 分析范围：`benchmark.py`、`comparison_chart.py`、`distributed_scheduler/` vs `optimized_scheduler/`  
> 结论：**benchmark.py 设计存在严重缺陷，comparison_chart.py 数据为硬编码假数据，无法支撑任何性能结论。**

---

## 一、benchmark.py 设计缺陷逐条分析

### B-00（致命）：benchmark.py 根本无法运行 — 类型不匹配崩溃

**实测结果**（2025-01）：直接运行 `python3 benchmark.py` 立即崩溃：

```
AttributeError: 'int' object has no attribute 'value'
  File "benchmark.py", line 26: task = await scheduler.submit(dummy_task, 0.001)
  File "distributed_scheduler/scheduler.py", line 71: await self.queue.submit(task)
  File "distributed_scheduler/queue.py", line 61: priority=-task.priority.value
```

**根因**：`benchmark.py` 调用 `scheduler.submit(dummy_task, 0.001)`，`scheduler.submit()` 签名中 `priority: int = 2`，直接传给 `Task(priority=priority)`（int 2）。但 `queue.submit()` 中访问 `task.priority.value` 时期望 `TaskPriority` 枚举类型，int 无 `.value` 属性。

**影响**：benchmark.py 连一次运行都无法完成，更谈不上有效的性能测量。任何基于此 benchmark 的对比数据必然是虚假的。

### B-01（致命）：只测试 distributed，从未对比 optimized

```python
# benchmark.py 第4行
from distributed_scheduler import TaskScheduler, TaskPriority
# ↑ 只 import 旧版，optimized_scheduler 从未被引用
```

benchmark 的目标是对比两个调度器性能，但代码中完全不存在 `OptimizedScheduler` 的导入或使用。`comparison_chart.py` 声称的 "Throughput: 50→1000 TPS (20x)" 没有任何基准测试支撑。

### B-02（致命）：用盲等替代真正的完成检测

```python
# benchmark.py 第32-33行
# Wait for completion - ISSUE: No actual waiting mechanism
await asyncio.sleep(2.0)  # ← 硬编码 2 秒盲等

elapsed = time.time() - start
throughput = num_tasks / elapsed
```

问题：
- 如果任务在 0.5s 内全部完成，额外浪费 1.5s，拉低吞吐量数值
- 如果任务需要 3s 才能完成，只等了 2s，漏计未完成任务，**虚假拉高吞吐量**
- 100 个 0.001s 的 `dummy_task` 在 4 workers 下，理论上约 0.025s 完成，2s 盲等使测量值偏差 ~80x

### B-03（严重）：无 warmup

```python
# benchmark.py 第17-19行
scheduler = TaskScheduler(min_workers=4, max_workers=4)
await scheduler.start()

# 直接开始测量，无 warmup
start = time.time()
```

Python asyncio event loop、heapq、对象分配等都需要 warmup。首次运行受 JIT/内存分配影响，不应计入测量。

### B-04（严重）：单次运行，无统计分析

没有多次迭代、没有均值/方差/标准差/P50/P99。一次运行的测量值完全不可靠（可能受 OS 调度抖动影响）。

### B-05（中等）：使用 `time.time()` 而非 `time.monotonic()`

`time.time()` 受系统时间调整（NTP、闰秒）影响，可能产生负耗时。benchmark 应使用 `time.monotonic()` 或 `time.perf_counter()`。

### B-06（严重）：缺少关键场景覆盖

| 缺失场景 | 重要性 | 说明 |
|----------|--------|------|
| 高并发（1000+ 任务） | 高 | 当前仅 100 个任务，无法暴露队列/堆的 O(n) 退化 |
| 长任务（>10s） | 高 | 无法暴露超时处理、worker 阻塞问题 |
| 混合优先级 | 中 | 无法暴露优先级反转 |
| 任务失败/重试 | 高 | 无法暴露 D-01 重试泄漏 |
| 延迟/调度任务 | 中 | 无法暴露 D-03 热循环 |
| 并发提交 | 中 | 无法暴露竞态条件 |
| 背压/队列满 | 高 | 无法暴露 D-03/D-08 问题 |

### B-07（中等）：缺少指标维度

只测量了吞吐量（tasks/sec），以下关键指标完全缺失：
- P50/P99 延迟
- 内存使用（peak/resident）
- CPU 使用率
- 队列深度变化
- 错误率
- worker 利用率

### B-08（严重）：`comparison_chart.py` 数据完全虚构

```python
# comparison_chart.py 第15-16行
before = [50, 500, 200, 80]    # 吞吐量、延迟、内存、CPU
after = [1000, 50, 50, 40]     # 声称 20x 提升
```

这些数据**没有一行来自实测**。benchmark.py 只测 distributed（且只测吞吐量一个指标），optimized 的四个指标从未被测量过。该 chart 是纯粹的"演示图"，不是真实性能报告。

---

## 二、两版调度器性能特性对比（基于代码分析）

### 2.1 架构差异

| 维度 | distributed (旧) | optimized (新) |
|------|-----------------|---------------|
| 队列结构 | `list` + `heapq`（O(n) 非线程安全） | `asyncio.PriorityQueue`（O(log n)，原生异步安全） |
| worker 取任务 | 阻塞 get，无超时，靠 `poll_interval` 睡眠 | `wait_for(timeout=1.0)`，可取消 |
| 调度循环 | 固定 1s 轮询 + 线性扫描 | heap 事件驱动 + 动态 sleep |
| 序列化 | `json.dumps(self.to_dict())` 含 callable | Pydantic BaseModel，不含 callable |
| worker 停止 | 顺序逐个 stop | `asyncio.gather` 并发 stop |
| 依赖注入 | 内部创建（不可 mock） | 构造函数注入（可测试） |
| 自动扩缩 | 无 | 基于队列填充率的 auto-scale |

### 2.2 潜在性能瓶颈

#### distributed 版本

| 瓶颈 | 位置 | 严重度 | 说明 |
|------|------|--------|------|
| O(n) 堆操作 | `queue.py:47 heapq.heappush` | **严重** | list 上的 heapq 在大规模下退化 |
| busy waiting | `worker.py:60 asyncio.sleep(poll_interval)` | **高** | 无任务时浪费 CPU |
| 同步 handler 阻塞 | `worker.py:89 handler(*args)` | **严重** | 同步代码直接调用，阻塞 event loop |
| 顺序 stop | `worker.py:129` 逐个 stop | **中** | 大批 worker 停止慢 |
| 无超时执行 | `worker.py:71 _execute_task` | **高** | 任务可无限运行 |
| 内存泄漏 | `queue.py:90 _task_map` 从不清理 completed | **高** | 长期运行 OOM |
| 线性扫描调度 | `scheduler.py:139` 轮询所有 scheduled | **中** | 大量 scheduled 任务时退化 |

#### optimized 版本

| 瓶颈 | 位置 | 严重度 | 说明 |
|------|------|--------|------|
| D-01 重试 double-add | `queue.py` + `worker.py` | **严重** | `_active_tasks` 重复添加 + `task_done` 缺失 → `join()` 永久阻塞 |
| D-02 同步 handler 超时泄漏 | `registry.py:52-56` | **严重** | `run_in_executor` 无法被 `wait_for` 取消 → 线程泄漏 |
| D-03 延迟队列热循环 | `queue.py:250-255` | **高** | 主队列满时每 100ms 无效 pop/push |
| D-04 依赖从未检查 | `scheduler.py` | **高** | `dependencies` 字段完全未被使用 |
| D-05 task_done 不对称 | `queue.py` | **中** | `fail()` 不调用 `task_done()` → `join()` 卡死 |
| worker pool 未启用 auto-scale | `worker.py` | **中** | `_auto_scale()` 方法存在但从未在 `start()` 中启动 |

---

## 三、测量偏差分析

### 3.1 benchmark.py 的测量偏差

假设 distributed scheduler 的 4 个 worker 处理 100 个 0.001s 任务：

```
理论最小时间 = 100 × 0.001 / 4 = 0.025s （完美并行）
实际时间 ≈ 0.025 + overhead（调度、队列操作、asyncio 开销）
```

benchmark 用 `await asyncio.sleep(2.0)` 盲等，测得的 elapsed 接近 2.0s：

```
报告吞吐量 = 100 / 2.0 = 50 TPS
实际吞吐量 ≈ 100 / 0.05 = 2000 TPS （40x 差异！）
```

**这个 50 TPS 恰好是 `comparison_chart.py` 中 "Before" 的吞吐量数值。** 这强烈暗示 chart 数据来源于 benchmark 的 bug 结果，而非真实性能。

### 3.2 test_optimized_scheduler.py 的性能测试

optimized 版本的 `TestPerformance.test_throughput`（第 798-828 行）有类似问题：

```python
start = asyncio.get_event_loop().time()
for i in range(num_tasks):
    await scheduler.submit(...)  # 串行提交！

while counter[0] < num_tasks:
    await asyncio.sleep(0.01)  # 轮询等待
elapsed = ...
```

- 提交是串行的（`await`），不是并发提交——测量包含了提交耗时
- 用轮询等待而非事件驱动
- 断言 `tps > 50`，门槛过低

但至少用了 `event_loop.time()`（等价于 `monotonic`），比 benchmark.py 的 `time.time()` 略好。

---

## 四、评估结论

### 4.1 基准测试设计：不合格

| 评估维度 | 评分 | 说明 |
|----------|------|------|
| 覆盖场景 | 1/10 | 仅 1 个场景（100 短任务），无高并发/长任务/失败/延迟 |
| 测量方法 | 2/10 | 盲等、无 warmup、单次运行、`time.time()` |
| 对比完整性 | 0/10 | 只测旧版，从未测新版 |
| 指标维度 | 1/10 | 仅吞吐量 |
| 统计严谨性 | 0/10 | 无均值/方差/百分位 |
| 数据真实性 | 0/10 | comparison_chart.py 全为硬编码假数据 |

**总评：benchmark.py 不具备任何有效的基准测试能力。`comparison_chart.py` 的数据是虚构的，不应在任何正式场合引用。**

### 4.2 是否存在"抢跑"或"虚假优化"？

- **"抢跑"（early signal）**：不适用。benchmark 没有对比测试，不存在一个版本提前结束测量的情况。
- **"虚假优化"**：存在。`comparison_chart.py` 声称的 20x 吞吐量提升（50→1000 TPS）可能来源于 benchmark 的盲等 bug：2s 固定等待导致旧版测量吞吐量被压低到 ~50 TPS，而 optimized 的 TPS 数据无任何来源。两者均无法反映真实性能。

### 4.3 两版调度器的真实性能关系（代码层面推断）

optimized 版本在架构上确实有改进（异步优先队列、并发 worker 停止、依赖注入），但存在 D-01~D-05 五个关键缺陷，其中 D-01（重试泄漏）和 D-02（线程泄漏）在生产环境中可能导致比旧版更严重的故障。

**在修复 D-01~D-05 之前，两个版本都无法可靠地进行性能基准测试。**

---

## 五、修复建议

### 5.1 benchmark.py 重写要点

```
1. 同时 import 两个调度器
2. 使用 time.perf_counter() 或 loop.time()
3. 每个场景至少 warmup 1 次 + 测量 5 次
4. 用事件/条件变量检测完成，而非盲等
5. 覆盖场景：
   - 短任务吞吐量（100/1000/10000 任务）
   - 长任务延迟（P50/P99）
   - 混合优先级
   - 任务失败+重试
   - 并发提交
6. 指标：TPS、P50/P99 延迟、内存峰值、CPU 使用率
7. 与纯 asyncio.gather() baseline 对比
```

### 5.2 comparison_chart.py 修复

必须从 benchmark 实测数据生成图表，删除所有硬编码数值。

### 5.3 优先级排序

1. **立即**：修复 D-01（重试泄漏）和 D-05（task_done 不对称）——这两个缺陷使 benchmark 无法正确运行
2. **高优先级**：修复 D-02（线程泄漏）、D-03（热循环）、D-04（依赖检查）
3. **然后**：重写 benchmark.py
4. **最后**：用实测数据更新 comparison_chart.py
