# 示例模块依赖与耦合度分析报告

> 生成日期: 2025-05-02  
> 分析范围: `examples/` 下所有编排(orchstration)和调度(scheduler)示例  
> 约束: 文件不超过 500 行, 仅分析不修改代码

---

## 一、总览

| 分类 | 示例数 | 关键问题 |
|------|--------|----------|
| orchestration 示例 | 4 个 Python 文件 | 2 个示例直接导入非公开内部模块 |
| complex_scheduler 示例 | 6 个 Python 文件 (含 distributed_scheduler + optimized_scheduler 子包) | 硬编码路径, 完全独立于核心调度 |
| mempo_context_demo | 1 个 Python 文件 | 直接导入 `pilotcode.services` 内部模块 |

---

## 二、⚠️ 直接导入非公开内部模块 (ACCEPTANCE CRITERIA)

### 2.1 `pilotcode.orchestration.smart_coordinator` — 不在 `__all__` 中

`src/pilotcode/orchestration/__init__.py` 的 `__all__` **未导出** `SmartCoordinator`。

| 文件 | 行号 | 导入语句 |
|------|------|----------|
| `examples/orchestration/auto_decomposition_demo.py` | L9 | `from pilotcode.orchestration.smart_coordinator import SmartCoordinator` |
| `examples/orchestration/real_world_usage.py` | L169 | `from pilotcode.orchestration.smart_coordinator import SmartCoordinator` |

### 2.2 `pilotcode.orchestration.auto_config` — 不在 `__all__` 中

`src/pilotcode/orchestration/__init__.py` 的 `__all__` **未导出** `configure_auto_decomposition` 等函数。

| 文件 | 行号 | 导入语句 |
|------|------|----------|
| `examples/orchestration/auto_decomposition_demo.py` | L10 | `from pilotcode.orchestration.auto_config import configure_auto_decomposition` |
| `examples/orchestration/real_world_usage.py` | L227-L232 | `from pilotcode.orchestration.auto_config import configure_auto_decomposition, get_auto_config, enable_auto_decomposition, disable_auto_decomposition` |

### 2.3 `pilotcode.services.*` — 非公开 services 模块

| 文件 | 行号 | 导入语句 |
|------|------|----------|
| `examples/mempo_context_demo.py` | L17-L19 | `from pilotcode.services.adaptive_context_manager import AdaptiveContextManager, AdaptiveContextConfig, ...` |
| `examples/mempo_context_demo.py` | L20 | `from pilotcode.services.memory_value import get_memory_value_estimator` |
| `examples/mempo_context_demo.py` | L21-L25 | `from pilotcode.services.task_aware_compression import TaskAwareCompressor, TaskContext, CompressionMode` |
| `examples/mempo_context_demo.py` | L26-L29 | `from pilotcode.services.compression_feedback import get_compression_feedback_loop, TaskOutcome` |
| `examples/mempo_context_demo.py` | L30 | `from pilotcode.services.hierarchical_memory import get_hierarchical_memory` |
| `examples/mempo_context_demo.py` | L63 | `from pilotcode.services.context_manager import ContextMessage` |

> 总计: **13 处**从示例代码直接导入非公开内部模块的情况。

### 2.4 硬编码本地路径

| 文件 | 行号 | 代码 |
|------|------|------|
| `examples/complex_scheduler/test_optimized_scheduler.py` | L11 | `sys.path.insert(0, "/home/zx/mycc/PilotCode/test_complex_system")` |
| `examples/mempo_context_demo.py` | L14 | `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))` |

---

## 三、耦合度分析

### 3.1 orchestration 示例与核心调度代码的耦合

```
examples/orchestration/  ──→  src/pilotcode/orchestration/
                                  ├── __init__.py          (✅ 公开 API)
                                  ├── smart_coordinator.py (❌ 非公开导入)
                                  └── auto_config.py       (❌ 非公开导入)
```

- **`basic_decomposition.py`**: 仅从 `pilotcode.orchestration` 公开 API 导入 → ✅ **低耦合**
- **`auto_decomposition_demo.py`**: 混用公开 API + 直接导入 `smart_coordinator` / `auto_config` → ❌ **中耦合**
- **`complex_task_demo.py`**: 仅从公开 API 导入 → ✅ **低耦合**
- **`real_world_usage.py`**: 混用公开 API + 直接导入 `smart_coordinator` / `auto_config` → ❌ **高耦合**

### 3.2 complex_scheduler 示例与核心调度代码的耦合

```
examples/complex_scheduler/  ──→  核心调度代码 (src/pilotcode/)
                                      └── ❌ 无任何依赖!
```

**关键发现**: `distributed_scheduler/` 和 `optimized_scheduler/` 是**完全独立实现**的调度系统，与 `src/pilotcode/` 下任何模块**零依赖**。它们不是"调用"核心调度，而是**自己就是一套调度系统**。

这意味着：
- 它们不是"示例"（demo/usage example），而是**独立的参考实现**（reference implementation）
- 对核心调度代码的耦合度为 **0**
- 但与核心调度的**接口契约**也无任何关联

### 3.3 mempo_context_demo 与核心代码的耦合

```
examples/mempo_context_demo.py  ──→  src/pilotcode/services/
                                       ├── adaptive_context_manager.py
                                       ├── memory_value.py
                                       ├── task_aware_compression.py
                                       ├── compression_feedback.py
                                       ├── hierarchical_memory.py
                                       └── context_manager.py
```

**6 个 services 模块的直接依赖** — 这是最高的耦合度。该示例深度依赖 `pilotcode.services` 内部实现细节。

---

## 四、重复代码分析

### 4.1 orchestration 示例间的重复

| 重复模式 | 出现文件 | 重复度 |
|----------|----------|--------|
| `TaskDecomposer()` 实例化 + `.analyze()` / `.auto_decompose()` 调用 | `basic_decomposition.py`, `auto_decomposition_demo.py`, `complex_task_demo.py`, `real_world_usage.py` | 🔴 高 |
| `print("=" * 60)` 分隔线打印模式 | 全部 4 个 orchestration 文件 | 🔴 高 |
| 遍历 `result.subtasks` 打印 `subtask.role`, `subtask.description`, `subtask.dependencies` | `basic_decomposition.py` (L46-L49), `complex_task_demo.py` (L94-L97), `auto_decomposition_demo.py` (L93-L95) | 🔴 高 |
| `DecompositionStrategy` 枚举比较逻辑 | `basic_decomposition.py`, `auto_decomposition_demo.py`, `complex_task_demo.py` | 🟡 中 |
| `MockAgent` 类定义 | `auto_decomposition_demo.py` (L13-L17), `real_world_usage.py` (L24-L28) | 🔴 重复定义 |

### 4.2 distributed_scheduler vs optimized_scheduler 代码重复

| 模块 | distributed_scheduler | optimized_scheduler | 关系 |
|------|----------------------|---------------------|------|
| `TaskPriority` | `task.py` (Enum) | `models.py` (int, Enum) | 重复实现 |
| `TaskStatus` | `task.py` (Enum) | `models.py` (str, Enum) | 重复实现 |
| `TaskQueue` / `OptimizedTaskQueue` | `queue.py` (133行) | `queue.py` (277行) | 重写版本 |
| `StateManager` | `state.py` (102行) | `state.py` (172行) | 重写版本 |
| `WorkerPool` | `worker.py` (162行) | `worker.py` (295行) | 重写版本 |
| `TaskScheduler` / `OptimizedScheduler` | `scheduler.py` (173行) | `scheduler.py` (284行) | 重写版本 |

`optimized_scheduler` 本质上是 `distributed_scheduler` 的**完整重写**，增加了 Pydantic 模型、自动扩缩容、指标采集等功能，但核心架构完全相同。

---

## 五、风险评估汇总

| 风险等级 | 问题 | 影响 |
|----------|------|------|
| 🔴 严重 | `smart_coordinator` / `auto_config` 非公开导入 | 内部重构将破坏示例代码 |
| 🔴 严重 | `mempo_context_demo.py` 依赖 6 个 services 内部模块 | 任何 service 签名变更将破坏示例 |
| 🔴 严重 | `test_optimized_scheduler.py` 硬编码绝对路径 | 仅创建者本机可运行 |
| 🟡 中等 | 4 个 orchestration 示例存在大量重复打印/分析逻辑 | 维护成本高, 修改需同步多处 |
| 🟡 中等 | `distributed_scheduler` 和 `optimized_scheduler` 完全独立 | 与核心无接口契约, 不能作为集成参考 |
| 🟢 低 | `basic_decomposition.py` 和 `complex_task_demo.py` 仅用公开 API | 耦合可控 |

---

## 六、建议

1. **将 `SmartCoordinator` 和 `auto_config` 加入 `__all__`** — 或创建稳定的公开适配层
2. **为 `mempo_context_demo.py` 创建 `pilotcode.services` 公开子集** — 或将其移至 `src/pilotcode/` 内部作为集成测试
3. **移除硬编码路径** — `test_optimized_scheduler.py` L11 的绝对路径是严重缺陷
4. **提取公共打印工具函数** — 消除 4 个 orchestration 示例中的重复格式化逻辑
5. **明确 `complex_scheduler` 定位** — 要么作为独立参考实现移至 `docs/examples/`, 要么与核心调度建立接口契约
