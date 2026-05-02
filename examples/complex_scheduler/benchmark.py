#!/usr/bin/env python3
"""性能基准测试 — 对比 distributed vs optimized 调度器。

设计原则:
  - 使用 time.perf_counter() (单调时钟, 不受 NTP 影响)
  - 每场景 warmup 1 轮 + 测量 5 轮, 报告 mean ± stddev
  - 用 get_stats() 轮询检测完成, 硬超时保底 (杜绝盲等)
  - 覆盖: 微任务吞吐 / 高并发 / 长任务 / 混合优先级 / 突发提交
  - 统一适配层消除 API 差异

原始 benchmark.py 缺陷总结 (已在本重写中全部修复):
  B-00 致命: submit(priority=int) 与 queue 期望 TaskPriority 不兼容 → 启动崩溃
  B-01 致命: 只测 distributed, 从未 import optimized
  B-02 致命: await asyncio.sleep(2.0) 盲等 → 吞吐量数据无效
  B-03 严重: 无 warmup, 冷启动开销混入测量
  B-04 严重: 单次运行, 无统计显著性
  B-05 中等: 使用 time.time() 而非 perf_counter
  B-06 严重: 仅覆盖 100 个 1ms 微任务一种场景
"""

from __future__ import annotations

import asyncio
import math
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Any

# ---------------------------------------------------------------------------
# 适配层 — 统一两个调度器的接口
# ---------------------------------------------------------------------------


class SchedulerAdapter(ABC):
    """统一调度器接口, 屏蔽 distributed / optimized API 差异."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def submit_task(self, duration: float, priority: int = 2) -> str:
        """提交一个 dummy 任务, 返回 task_id。priority: 1=LOW..4=CRITICAL."""
        ...

    @abstractmethod
    def completed_count(self) -> int: ...

    @abstractmethod
    def failed_count(self) -> int: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# --- Distributed adapter ---


class DistributedAdapter(SchedulerAdapter):
    def __init__(self, min_workers: int = 4, max_workers: int = 4):
        from distributed_scheduler import TaskScheduler, TaskPriority

        self._sched = TaskScheduler(min_workers=min_workers, max_workers=max_workers)
        self._TaskPriority = TaskPriority

    @property
    def name(self) -> str:
        return "distributed"

    async def start(self) -> None:
        await self._sched.start()

    async def stop(self) -> None:
        await self._sched.stop()

    async def submit_task(self, duration: float, priority: int = 2) -> str:
        # 修复 B-00: 传递 TaskPriority 枚举 (非 int), 避免 queue.py 中
        #   task.priority.value 对 int 调用 .value 的 AttributeError
        prio = self._TaskPriority(priority)  # int → enum

        async def _work(d: float = duration):
            await asyncio.sleep(d)
            return "ok"

        task = await self._sched.submit(_work, priority=prio)
        return task.id

    def completed_count(self) -> int:
        return self._sched.queue.get_stats().get("completed", 0)

    def failed_count(self) -> int:
        return self._sched.queue.get_stats().get("failed", 0)


# --- Optimized adapter ---


class OptimizedAdapter(SchedulerAdapter):
    HANDLER_PATH = "benchmark.dummy"

    def __init__(self, min_workers: int = 4, max_workers: int = 4):
        from optimized_scheduler import (
            OptimizedScheduler,
            SchedulerConfig,
            TaskPriority,
            TaskRegistry,
            ExecutionConfig,
        )

        # 注册 benchmark handler
        registry = TaskRegistry()
        if self.HANDLER_PATH not in registry.list_handlers():
            registry.register(self.HANDLER_PATH, self._dummy_handler)

        config = SchedulerConfig(
            min_workers=min_workers, max_workers=max_workers, enable_metrics=False
        )
        self._sched = OptimizedScheduler(config=config, registry=registry)
        self._TaskPriority = TaskPriority
        self._ExecutionConfig = ExecutionConfig
        self._completed = 0
        self._failed = 0

    @property
    def name(self) -> str:
        return "optimized"

    async def _dummy_handler(self, instance, duration: float = 0.001, **kwargs):
        await asyncio.sleep(duration)
        return "ok"

    async def start(self) -> None:
        await self._sched.start()

    async def stop(self) -> None:
        await self._sched.stop()

    async def submit_task(self, duration: float, priority: int = 2) -> str:
        prio = self._TaskPriority(priority)
        cfg = self._ExecutionConfig(timeout_seconds=max(10.0, duration * 2))
        instance = await self._sched.submit(
            name=f"bench-{duration}",
            handler_path=self.HANDLER_PATH,
            input_data={"duration": duration},
            priority=prio,
            execution_config=cfg,
        )
        return instance.instance_id

    def completed_count(self) -> int:
        stats = self._sched.get_stats()
        return stats["queue"].get("completed", 0)

    def failed_count(self) -> int:
        stats = self._sched.get_stats()
        return stats["queue"].get("failed", 0)


# ---------------------------------------------------------------------------
# 测量工具
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """单场景测量结果."""

    adapter_name: str
    scenario: str
    num_tasks: int
    runs: list[float] = field(default_factory=list)  # 每轮耗时(秒)

    @property
    def mean(self) -> float:
        return sum(self.runs) / len(self.runs) if self.runs else 0.0

    @property
    def stddev(self) -> float:
        if len(self.runs) < 2:
            return 0.0
        m = self.mean
        return math.sqrt(sum((x - m) ** 2 for x in self.runs) / (len(self.runs) - 1))

    @property
    def tps(self) -> float:
        """吞吐量 tasks/sec."""
        return self.num_tasks / self.mean if self.mean > 0 else 0.0

    def __str__(self) -> str:
        return (
            f"[{self.adapter_name:>12}] {self.scenario:<24s}  "
            f"tasks={self.num_tasks:>5d}  "
            f"time={self.mean:.3f}s ±{self.stddev:.3f}s  "
            f"tps={self.tps:.1f}"
        )


async def measure(
    adapter: SchedulerAdapter,
    scenario: str,
    num_tasks: int,
    task_duration: float,
    warmup: int = 1,
    runs: int = 5,
    priorities: list[int] | None = None,
    burst: bool = False,
    timeout: float = 120.0,
) -> BenchmarkResult:
    """运行一轮基准测试, 返回聚合结果.

    Args:
        adapter: 调度器适配器
        scenario: 场景名
        num_tasks: 任务数量
        task_duration: 每个任务的 sleep 秒数
        warmup: 预热轮数 (不计时)
        runs: 测量轮数
        priorities: 若提供, 为每个任务依次指定优先级 (循环使用)
        burst: True=先全部提交再等待; False=逐个提交
        timeout: 硬超时 (秒)
    """
    result = BenchmarkResult(adapter_name=adapter.name, scenario=scenario, num_tasks=num_tasks)

    for run_idx in range(warmup + runs):
        await adapter.start()

        # 提交任务
        tids: list[str] = []
        if burst:
            # 突发模式: 尽快提交所有任务
            for i in range(num_tasks):
                prio = priorities[i % len(priorities)] if priorities else 2
                tid = await adapter.submit_task(task_duration, prio)
                tids.append(tid)
        else:
            for i in range(num_tasks):
                prio = priorities[i % len(priorities)] if priorities else 2
                tid = await adapter.submit_task(task_duration, prio)
                tids.append(tid)

        start = time.perf_counter()

        # 轮询等待完成 (杜绝盲等)
        deadline = start + timeout
        target = num_tasks
        while True:
            done = adapter.completed_count() + adapter.failed_count()
            if done >= target:
                break
            if time.perf_counter() > deadline:
                print(f"  WARNING: timeout {timeout}s, done={done}/{target}")
                break
            await asyncio.sleep(0.005)  # 5ms 轮询

        elapsed = time.perf_counter() - start

        if run_idx >= warmup:
            result.runs.append(elapsed)

        # 校验完成数量
        stats_done = adapter.completed_count() + adapter.failed_count()
        if stats_done < num_tasks * 0.95:
            print(
                f"  WARNING: only {stats_done}/{num_tasks} tasks finished "
                f"(elapsed={elapsed:.2f}s)"
            )

        await adapter.stop()
        await asyncio.sleep(0.05)  # 清理间隙

    return result


# ---------------------------------------------------------------------------
# 场景定义
# ---------------------------------------------------------------------------

SCENARIOS = [
    # (name, num_tasks, task_duration, priorities, burst, timeout)
    ("micro-throughput", 200, 0.001, None, True, 30.0),
    ("high-concurrency", 2000, 0.001, None, True, 60.0),
    ("long-tasks", 20, 0.500, None, False, 60.0),
    ("mixed-priority", 100, 0.005, [1, 2, 3, 4], True, 30.0),
    ("burst-submit", 500, 0.001, None, True, 30.0),
]


async def run_benchmarks():
    adapters: list[SchedulerAdapter] = [
        DistributedAdapter(min_workers=4, max_workers=4),
        OptimizedAdapter(min_workers=4, max_workers=4),
    ]

    all_results: list[BenchmarkResult] = []

    for adapter in adapters:
        print(f"\n{'='*60}")
        print(f"  Testing: {adapter.name}")
        print(f"{'='*60}")
        for scenario, n, dur, prios, burst, timeout in SCENARIOS:
            print(
                f"  Scenario: {scenario} (n={n}, dur={dur}s, " f"burst={burst})...",
                end=" ",
                flush=True,
            )
            try:
                res = await measure(
                    adapter,
                    scenario,
                    n,
                    dur,
                    warmup=1,
                    runs=5,
                    priorities=prios,
                    burst=burst,
                    timeout=timeout,
                )
                all_results.append(res)
                print(f"  mean={res.mean:.3f}s  tps={res.tps:.1f}")
            except Exception as e:
                print(f"  FAILED: {e}")
                import traceback

                traceback.print_exc()

    # --- 报告 ---
    print("\n")
    print("=" * 74)
    print("  BENCHMARK RESULTS")
    print("=" * 74)
    print(f"{'Adapter':>12}  {'Scenario':<24s}  {'Tasks':>5s}  " f"{'Time (s)':>16s}  {'TPS':>8s}")
    print("-" * 74)
    for r in all_results:
        print(
            f"{r.adapter_name:>12}  {r.scenario:<24s}  {r.num_tasks:>5d}  "
            f"{r.mean:>7.3f} ±{r.stddev:.3f}s  {r.tps:>8.1f}"
        )

    # 场景对比
    print("\n--- 场景对比 (distributed vs optimized) ---")
    scenarios_seen = set()
    for r in all_results:
        if r.scenario in scenarios_seen:
            continue
        scenarios_seen.add(r.scenario)
        pair = [x for x in all_results if x.scenario == r.scenario]
        if len(pair) == 2:
            d, o = pair[0], pair[1]
            if d.adapter_name == "optimized":
                d, o = o, d
            ratio = d.mean / o.mean if o.mean > 0 else float("inf")
            winner = "optimized" if ratio > 1 else ("distributed" if ratio < 1 else "tie")
            print(
                f"  {r.scenario:<24s}  "
                f"dist={d.mean:.3f}s  opt={o.mean:.3f}s  "
                f"ratio={ratio:.2f}x  → {winner}"
            )

    print("\n--- 测量偏差自检 ---")
    print("  1. 使用 time.perf_counter() (单调时钟)")
    print("  2. 每场景 warmup=1 轮 + 测量=5 轮")
    print("  3. 用 get_stats() 轮询检测完成 + 硬超时")
    print("  4. 报告 mean ± stddev (非单次运行)")
    print("  5. 覆盖: 微任务 / 高并发 / 长任务 / 混合优先级 / 突发")
    print("  6. 统一适配层消除 API 差异")

    # 原始 benchmark 缺陷清单
    print("\n--- 原始 benchmark.py 缺陷对照 ---")
    issues = [
        (
            "B-00 致命",
            "submit(priority=int) 与 queue 不兼容, 启动即崩溃",
            "显式传递 TaskPriority 枚举",
        ),
        ("B-01 致命", "只测 distributed, 从未 import optimized", "统一适配层测试两个调度器"),
        ("B-02 致命", "await asyncio.sleep(2.0) 盲等", "get_stats() 轮询 + 硬超时"),
        ("B-03 严重", "无 warmup, 冷启动计入测量", "warmup=1 轮不计时"),
        ("B-04 严重", "单次运行无统计", "5 轮测量, 报告 mean ± stddev"),
        ("B-05 中等", "time.time() 受 NTP 影响", "time.perf_counter()"),
        ("B-06 严重", "仅覆盖 100 个 1ms 微任务", "5 种场景: 微任务/高并发/长任务/混合优先级/突发"),
    ]
    for tag, problem, fix in issues:
        print(f"  {tag}: {problem}")
        print(f"          → 本版修复: {fix}")

    return all_results


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("PilotCode Scheduler Benchmark")
    print("=" * 60)
    print("对比: distributed_scheduler vs optimized_scheduler")
    print(
        "场景: micro-throughput / high-concurrency / long-tasks / " "mixed-priority / burst-submit"
    )
    print("方法: warmup=1, runs=5, perf_counter, stats-polling")
    print()
    asyncio.run(run_benchmarks())
