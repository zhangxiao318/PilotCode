# PilotCode 任务编排系统功能重叠与合并方案

## 一、现状：4套独立的编排系统

PilotCode 目前存在 **4 套完全独立、互不调用** 的任务编排系统，每套都有自己的入口、分解器、执行器和状态管理。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           用户请求入口层                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ REPL直接模式 │  │WebSocket直接 │  │   WebSocket  │  │   Agent工作流    │ │
│  │ run_headless │  │ DIRECT分支   │  │  PLAN分支    │  │ AgentOrchestrator│ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
│         │                 │                  │                    │          │
│         ▼                 ▼                  ▼                    ▼          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ 系统1: QE直接│  │ 系统1: QE直接│  │ 系统2: P-EVR │  │ 系统4: 多Agent   │ │
│  │   模式       │  │   模式       │  │   框架       │  │   工作流         │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────┘ │
│                                                                              │
│  还有隐藏的 系统3: AgentCoordinator (orchestration/coordinator.py)           │
│  没有任何入口直接调用它，是一个"孤儿模块"                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、4套系统的详细对比

### 系统1：QueryEngine 直接模式（最常用）

**入口：**
- `components/repl.py:run_headless()` 行 1013-1058
- `components/repl.py:run_repl_session()` 行 96-101
- `web/server.py:process_query()` DIRECT 分支

**分解：** 无。用户输入直接作为 prompt 提交给 LLM。

**执行：**
```python
# repl.py:96-101
query_engine = QueryEngine(QueryEngineConfig(cwd=working_dir, tools=tools, ...))
# 直接 submit_message，没有任务分解
```

**状态：** `Store(AppState)` + `QueryEngine.messages`

**特点：**
- 最简洁，最常用
- 没有任务分解，没有验证，没有重试
- 适合简单问答和单文件编辑

---

### 系统2：P-EVR 框架（MissionAdapter）

**入口：**
- `orchestration/adapter.py:MissionAdapter.run()`
- `web/server.py:process_query()` PLAN 分支 行 686-699

**分解：**
```python
# adapter.py:123-234 _plan_mission()
# 1. 调用 LLM 生成 JSON plan
# 2. 解析为 Mission → Phase → TaskSpec
```

**执行：**
```python
# orchestrator.py:145-180
# 1. DagExecutor.build() 拓扑排序
# 2. 主循环调度 ready tasks
# 3. _llm_worker() → QueryEngine + ToolExecutor
```

**状态：** `MissionTracker` (SQLite + DAG + 状态机)

**特点：**
- 最完整的框架：Plan→Execute→Verify→Reflect
- 有 DAG 调度、三级验证、项目记忆
- 但只被 WebSocket PLAN 分支使用，REPL 不走这里

---

### 系统3：Coordinator 模式（孤儿模块）

**入口：** `orchestration/coordinator.py:AgentCoordinator.execute()`

**分解：**
```python
# coordinator.py:98-103
# 调用 TaskDecomposer.analyze() → 规则 + pattern
```

**执行：**
```python
# coordinator.py:118-139
# TaskExecutor.execute_sequential/parallel()
# 但 _execute_single() 是空的（stub）！
```

**状态：** 内部 `_workflows: dict[str, WorkflowResult]`

**特点：**
- **没有任何入口调用它**（全局搜索 `AgentCoordinator` 只有定义和测试引用）
- `TaskExecutor._execute_single()` 是空实现
- 完全的僵尸代码

---

### 系统4：多 Agent 工作流（AgentOrchestrator）

**入口：**
- `agent/agent_orchestrator.py:run_sequential()`
- `agent/agent_orchestrator.py:run_parallel()`
- `agent/agent_orchestrator.py:run_supervisor()`
- `agent/agent_orchestrator.py:run_debate()`

**分解：** 内置在每个工作流模式中
```python
# run_supervisor() 行 284-300
# 监督者 Agent 通过 prompt 分解任务
```

**执行：**
```python
# _run_agent_task() 行 533-620
# 自建工具调用循环（简化版 QueryEngine）
# ctx = ToolUseContext()  # 空的！没有 get_app_state
```

**状态：** `AgentManager` + `WorkflowResult`

**特点：**
- 与 P-EVR 完全隔离
- `_run_agent_task` 创建的是**空 ToolUseContext**，工具无法获取 cwd
- run_map_reduce / run_pipeline 定义了但未实现

---

## 三、功能重叠矩阵

| 能力维度 | 系统1 QE直接 | 系统2 P-EVR | 系统3 Coordinator | 系统4 AgentOrchestrator |
|---------|:----------:|:---------:|:---------------:|:---------------------:|
| **任务分解** | ❌ 无 | ✅ LLM JSON | ✅ 规则+Pattern | ✅ 内置prompt |
| **DAG 拓扑调度** | ❌ 无 | ✅ Kahn算法 | ❌ 无 | ❌ 无 |
| **工具执行循环** | ✅ QueryEngine | ✅ QueryEngine | ❌ **空实现** | ✅ 自建循环 |
| **并发控制** | ❌ 无 | ✅ Semaphore | ✅ Semaphore | ✅ Semaphore |
| **结果验证** | ❌ 无 | ✅ L1/L2/L3 | ❌ 无 | ❌ 无 |
| **失败重试** | ❌ 无 | ✅ SmartRetry | ❌ 无 | ❌ 无 |
| **级联失败处理** | ❌ 无 | ✅ 下游取消 | ❌ 无 | ❌ 无 |
| **项目级记忆** | ❌ 无 | ✅ ProjectMemory | ❌ 无 | ❌ 无 |
| **状态持久化** | ⚠️ session文件 | ✅ SQLite | ❌ 内存 | ❌ 内存 |
| **上下文策略** | ❌ 无 | ✅ 3种策略 | ❌ 无 | ❌ 无 |

---

## 四、具体重叠点（带代码位置）

### 重叠1：三套任务分解器

```
分解器A: MissionAdapter._plan_mission()
    位置: adapter.py:123-234
    机制: LLM 生成 JSON → Mission.from_dict()
    用户: 仅 WebSocket PLAN 模式

分解器B: TaskDecomposer.analyze()  
    位置: decomposer.py:82-117
    机制: 规则启发式 → pattern匹配 → LLM（空实现）
    用户: 仅 AgentCoordinator（孤儿模块）

分解器C: AgentOrchestrator.run_supervisor() 内置
    位置: agent_orchestrator.py:284-300
    机制: 监督者 Agent 通过 prompt 分解
    用户: 仅 AgentOrchestrator

分解器D: classify_task_complexity()
    位置: components/repl.py:790-807
    机制: 基于 prompt 关键词判断 DIRECT vs PLAN
    用户: REPL + WebSocket
```

**重叠度：极高。** 4个分解器做同一件事（判断任务复杂度+分解任务），互不调用。

**合并方案：**
- 保留 `classify_task_complexity` 作为入口判断
- 保留 `_plan_mission` 作为复杂任务的 LLM 分解器
- **删除** `TaskDecomposer`（Coordinator 是孤儿，其分解器也无用）
- **删除** AgentOrchestrator 内置的分解逻辑，改用统一的 MissionAdapter

---

### 重叠2：三套工具执行循环

```
执行循环A: REPL/WebSocket 直接模式
    位置: repl.py 工具循环 / web/server.py:876-943
    机制: QueryEngine.submit_message() → 检测 ToolUseMessage → ToolExecutor

执行循环B: P-EVR _llm_worker()
    位置: adapter.py:484-650
    机制: QueryEngine.submit_message() → 检测 ToolUseMessage → ToolExecutor
    特点: 增加了 ProjectMemory 更新和 continue prompt

执行循环C: AgentOrchestrator._run_agent_task()
    位置: agent_orchestrator.py:533-620
    机制: 自建循环调用 model_client.chat_completion() + 手动工具执行
    特点: 创建空 ToolUseContext()，没有 cwd 注入
```

**重叠度：极高。** A 和 B 几乎完全相同（都是 QueryEngine + ToolExecutor），C 是劣化版的自建循环。

**合并方案：**
- 统一使用 **执行循环B**（`_llm_worker`），因为它功能最完整（有 ProjectMemory、continue prompt、工具过滤）
- **删除** AgentOrchestrator 的自建循环，改用统一的 worker
- REPL/WebSocket DIRECT 模式在复杂任务时也应走统一 worker

---

### 重叠3：两套状态追踪

```
状态A: Store(AppState) + QueryEngine.messages
    位置: state/store.py, query_engine.py
    范围: 单个会话/QueryEngine
    持久化: session 文件（save_session/load_session）

状态B: MissionTracker (SQLite + DAG + 状态机)
    位置: orchestration/tracker.py
    范围: 单个 Mission
    持久化: SQLite 数据库

状态C: ToolUseContext.read_file_state
    位置: tools/base.py
    范围: 单次工具调用批次
    持久化: 无（内存）
```

**重叠度：中高。** A 和 B 都追踪"任务执行状态"，但 A 是对话级别，B 是 mission 级别。

**合并方案：**
- `MissionTracker` 应成为**唯一的状态中心**
- `Store(AppState)` 降级为会话级配置容器（cwd、settings）
- `read_file_state` 迁移到 `ProjectMemory`

---

### 重叠4：两套并发控制

```
并发A: Orchestrator._semaphore
    位置: orchestrator.py:82
    控制: P-EVR 任务级并发

并发B: AgentOrchestrator.run_parallel semaphore
    位置: agent_orchestrator.py:195
    控制: Agent 工作流级并发

并发C: TaskExecutor.semaphore
    位置: executor.py:167
    控制: Coordinator 子任务并发
```

**重叠度：高。** 3个 asyncio.Semaphore 做同一件事。

**合并方案：**
- 统一在 `OrchestratorConfig.max_concurrent_workers`
- **删除** AgentOrchestrator 和 TaskExecutor 的独立 semaphore

---

## 五、推荐合并架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     统一入口层 (Unified Entry)                    │
│  REPL / WebSocket / API / TUI                                   │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              classify_task_complexity()                  │   │
│  │  ├─ 简单任务 → DIRECT 路径（QueryEngine 直接执行）       │   │
│  │  └─ 复杂任务 → PLAN 路径（UnifiedOrchestrator）          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (PLAN 路径)
┌─────────────────────────────────────────────────────────────────┐
│                 UnifiedOrchestrator (合并后)                     │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │ UnifiedDecomposer│ │   DagExecutor   │ │ UnifiedWorker  │     │
│  │ (原_plan_mission) │ │  (原Kahn算法)   │ │ (原_llm_worker)│     │
│  │ + 探索阶段       │ │               │ │ + ProjectMem  │     │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘     │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Verification Layer (L1/L2/L3)               │   │
│  │              + SmartRetry + CascadeCancel                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  状态中心: MissionTracker (SQLite + DAG + StateMachine)         │
│  项目记忆: ProjectMemory (跨任务共享)                           │
└─────────────────────────────────────────────────────────────────┘

                    ═══════ 删除/合并的模块 ═══════

❌ 删除 AgentCoordinator + TaskDecomposer + TaskExecutor
   └─ 功能完全被 UnifiedOrchestrator 覆盖，且当前是孤儿代码

❌ 删除 AgentOrchestrator 的 run_sequential / run_parallel
   └─ 功能被 DagExecutor 覆盖

🔧 重构 AgentOrchestrator 的 run_supervisor / run_debate
   └─ 降级为 UnifiedOrchestrator 的插件/特殊 worker 类型

🔧 重构 REPL/WebSocket DIRECT 模式
   └─ 简单任务仍走 DIRECT，但复杂任务应自动升级到 PLAN 路径
```

---

## 六、删除清单

| 文件/类 | 删除原因 | 替代方案 |
|--------|---------|---------|
| `orchestration/coordinator.py` | 孤儿模块，无入口调用 | 使用 `MissionAdapter` |
| `orchestration/decomposer.py` | Coordinator 的配套，LLM 分解是空实现 | 使用 `_plan_mission` |
| `orchestration/executor.py` | Coordinator 的配套，`_execute_single` 是空实现 | 使用 `_llm_worker` |
| `agent_orchestrator.run_sequential` | 与 DagExecutor 功能重叠 | 使用 `Orchestrator.run()` |
| `agent_orchestrator.run_parallel` | 与 DagExecutor 功能重叠 | 使用 `Orchestrator.run()` |
| `agent_orchestrator._run_agent_task` | 自建劣化循环，ToolUseContext 为空 | 使用 `_llm_worker` |
| `WorkflowType.MAP_REDUCE` | 无实现 | 删除枚举值或实现 |
| `WorkflowType.PIPELINE` | 无实现 | 删除枚举值或实现 |

---

## 七、保留但重构的模块

| 模块 | 重构内容 |
|------|---------|
| `AgentOrchestrator.run_supervisor` | 改为调用 `UnifiedOrchestrator`，自身只保留"监督者-工作者"prompt 逻辑 |
| `AgentOrchestrator.run_debate` | 同上，保留辩论流程逻辑，执行走统一 worker |
| `QueryEngine` | 保留作为底层执行引擎，但 DIRECT 模式也应能访问 ProjectMemory |
| `Store(AppState)` | 降级为配置容器，MissionTracker 接管执行状态 |

---

## 八、合并后的收益

1. **代码量减少 ~40%**：删除 coordinator、decomposer、executor 三个孤儿模块 + AgentOrchestrator 的重复实现
2. **维护成本降低**：只需维护一套编排逻辑
3. **功能一致性**：所有入口享受相同的验证、重试、记忆能力
4. **状态统一**：MissionTracker 成为唯一真相源
5. **测试覆盖提升**：集中测试一套系统，而非分散测试四套
