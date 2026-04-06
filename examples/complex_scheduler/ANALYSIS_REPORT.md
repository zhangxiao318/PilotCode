# 分布式任务调度系统 - 架构分析报告

## 1. 系统概览

**代码规模**: 857 行 (6 个模块)
**测试覆盖**: 56 行 (基础测试，覆盖率 < 20%)
**主要问题数**: 35+ 个标记的架构问题

## 2. 架构问题分析

### 2.1 Task 类 (task.py) - 严重设计问题

#### 问题: 上帝类 (God Class)
```python
@dataclass
class Task:
    # 20+ 个字段，混合了多个职责
    # - 身份标识 (id, name)
    # - 执行逻辑 (handler, args, kwargs)
    # - 状态管理 (status, timestamps)
    # - 重试逻辑 (max_retries, retry_count, retry_delay)
    # - 依赖管理 (dependencies, dependents)
    # - 结果存储 (result, error, traceback)
    # - 元数据 (metadata, tags)
```

**影响**:
- 内存占用高 (每个任务携带所有字段)
- 序列化困难 (包含 Callable)
- 职责不清，难以维护

#### 问题: 继承滥用
```python
@dataclass  
class ScheduledTask(Task):  # 仅添加 cron_expression
class ChainedTask(Task):    # 仅添加 chain_results
class ParallelTask(Task):   # 添加 subtasks 列表
```

**影响**:
- 不必要的继承层次
- 基类被迫包含子类不需要的字段

#### 问题: 不可序列化
```python
def to_dict(self) -> dict:
    return {
        'handler': str(self.handler),  # 丢失可调用对象
        'args': list(self.args),       # 可能不可序列化
        'result': str(self.result),    # 可能很大
    }
```

**影响**:
- 无法持久化到数据库
- 无法通过网络传输
- 崩溃后状态丢失

### 2.2 TaskQueue (queue.py) - 并发和性能问题

#### 问题: 非线程安全
```python
async def submit(self, task: Task) -> bool:
    async with self._not_full:
        heapq.heappush(self._queue, ...)  # heapq 本身不是线程安全的
```

**影响**:
- 高并发时可能出现数据竞争
- 优先级队列可能损坏

#### 问题: 内存泄漏
```python
async def complete(self, task: Task, result: any = None) -> None:
    self._stats['completed'] += 1
    # task 仍然保存在 _task_map 中，永不清理！
```

**影响**:
- 长时间运行后内存耗尽
- 必须重启服务

#### 问题: 低效实现
```python
# 使用 list 作为队列基础 - O(n) 操作
self._queue: list[PrioritizedItem] = []

# 每次操作都需要 heapq.heappush/heappop - O(log n)
```

**影响**:
- 无法达到 1000+ TPS 要求

### 2.3 Worker (worker.py) - 资源管理问题

#### 问题: 没有优雅关闭
```python
async def stop(self) -> None:
    self._running = False
    if self._task:
        self._task.cancel()  # 强制取消，不等待当前任务完成
```

**影响**:
- 任务执行到一半被中断
- 数据可能处于不一致状态

#### 问题: 同步代码阻塞事件循环
```python
if asyncio.iscoroutinefunction(task.handler):
    result = await task.handler(*task.args, **task.kwargs)
else:
    result = task.handler(*task.args, **task.kwargs)  # 阻塞！
```

**影响**:
- 一个同步任务阻塞所有其他任务
- 无法达到延迟 < 100ms 的要求

### 2.4 Scheduler (scheduler.py) - 架构设计问题

#### 问题: God Class
```python
class TaskScheduler:
    # 管理：队列、工作池、状态、定时任务、链式任务、并行任务
    # 责任过多，难以测试和维护
```

#### 问题: 紧耦合
```python
def __init__(self, ...):
    # 内部创建依赖，无法注入 mock
    self.queue = TaskQueue(max_size=max_queue_size)
    self.workers = WorkerPool(queue=self.queue, ...)
    self.state = StateManager()
```

**影响**:
- 单元测试困难
- 无法独立替换组件

#### 问题: 低效轮询
```python
async def _scheduler_loop(self) -> None:
    while self._running:
        # O(n) 扫描所有定时任务
        for task in self._scheduled_tasks:
            if task.scheduled_at and task.scheduled_at <= now:
                ...
        await asyncio.sleep(self._scheduler_interval)  # 固定间隔
```

**影响**:
- CPU 浪费在空轮询
- 无法精确调度

### 2.5 StateManager (state.py) - 持久化问题

#### 问题: 纯内存存储
```python
def __init__(self, ...):
    self._tasks: dict[str, Task] = {}  # 内存中
    self._history: dict[str, list[dict]] = defaultdict(list)  # 历史也在内存
```

**影响**:
- 进程崩溃丢失所有数据
- 无法水平扩展

## 3. 性能瓶颈分析

| 组件 | 瓶颈 | 当前复杂度 | 目标 |
|------|------|-----------|------|
| TaskQueue.submit | heapq + lock | O(log n) | O(1) |
| Scheduler._scheduler_loop | 线性扫描 | O(n) | O(log n) |
| StateManager.get_tasks_by_status | 线性扫描 | O(n) | O(1) |
| Worker._execute_task | 同步阻塞 | - | 异步 |
| Task.to_json | 全字段序列化 | O(m) | O(1) |

## 4. 优化方案设计

### 4.1 架构重构

```
优化后架构:
┌─────────────────────────────────────────────────────────────┐
│                    TaskScheduler (协调者)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  TaskQueue  │  │  WorkerPool │  │   StateManager      │ │
│  │  (asyncio   │  │  (动态扩展)  │  │   (持久化支持)       │ │
│  │   Queue)    │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │TaskRegistry │  │  Scheduler  │  │   MetricsCollector  │ │
│  │ (任务定义)   │  │  (定时任务)  │  │   (性能指标)         │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 关键改进

#### 1. Task 分离
- 分离 TaskDefinition (可序列化) 和 TaskInstance (运行时)
- 使用 Pydantic 模型确保类型安全
- 处理器注册表模式，避免存储 Callable

#### 2. Queue 优化
- 使用 asyncio.PriorityQueue (线程安全)
- 实现延迟队列 (使用 asyncio 的延迟机制)
- 定期清理完成的任务

#### 3. Worker 改进
- 使用 asyncio.wait_for 实现超时
- 同步任务使用 run_in_executor
- 优雅关闭机制

#### 4. Scheduler 优化
- 使用堆结构存储定时任务 (O(log n))
- 事件驱动而非轮询
- 组件通过接口交互，支持依赖注入

#### 5. StateManager 持久化
- 支持多种后端 (内存、Redis、数据库)
- 异步保存/加载
- 定期快照

## 5. 测试策略

### 5.1 单元测试
- 每个组件独立测试
- 使用 mock 替代依赖
- 边界条件测试

### 5.2 集成测试
- 组件交互测试
- 故障恢复测试
- 并发安全测试

### 5.3 性能测试
- 吞吐量测试 (目标: 1000+ TPS)
- 延迟测试 (目标: < 100ms)
- 内存泄漏测试

### 5.4 压力测试
- 长时间运行测试
- 高负载测试
- 故障注入测试
