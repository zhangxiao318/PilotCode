"""Performance benchmarks - ISSUES: No baseline, no regression detection."""

import asyncio
import time
from distributed_scheduler import TaskScheduler, TaskPriority


async def dummy_task(duration: float = 0.001):
    """Simulate work."""
    await asyncio.sleep(duration)
    return "done"


async def benchmark_throughput():
    """ISSUE: No warmup, single run only."""
    scheduler = TaskScheduler(min_workers=4, max_workers=4)
    await scheduler.start()

    try:
        num_tasks = 100
        start = time.time()

        # Submit tasks
        tasks = []
        for i in range(num_tasks):
            task = await scheduler.submit(dummy_task, 0.001)
            tasks.append(task)

        # Wait for completion - ISSUE: No actual waiting mechanism
        await asyncio.sleep(2.0)

        elapsed = time.time() - start
        throughput = num_tasks / elapsed

        print(f"Submitted {num_tasks} tasks in {elapsed:.2f}s")
        print(f"Throughput: {throughput:.2f} tasks/sec")

    finally:
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(benchmark_throughput())
