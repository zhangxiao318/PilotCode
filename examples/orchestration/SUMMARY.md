# Orchestration Demo Files — Summary

Generated from `examples/orchestration/` — 4 Python files demonstrating the `pilotcode.orchestration` system.

---

## 1. `auto_decomposition_demo.py` (186 lines)

**Purpose:** Demonstrates automatic task decomposition — how `SmartCoordinator` and `TaskDecomposer` heuristically decide whether to decompose a task, and configuration of the auto-decomposition feature.

**Key Classes:**
| Class | Description |
|---|---|
| `MockAgent` | Mock agent with `role` and `prompt` attributes |

**Key Functions:**
| Function | Signature | Description |
|---|---|---|
| `mock_agent_factory` | `(role, prompt) -> MockAgent` | Factory to create mock agents |
| `demo_heuristic_analysis` | `()` | Runs heuristic analysis on 8 test tasks, prints strategy/confidence/will-decompose |
| `demo_auto_patterns` | `()` | Demonstrates 4 decomposition patterns (Implementation, Refactoring, Bug Fix, Code Review) |
| `demo_smart_coordinator` | `()` | Shows `SmartCoordinator` analysis without execution for 4 tasks |
| `demo_configuration` | `()` | Prints current `auto_config` settings and shows configuration examples |
| `main` (async) | `()` | Runs all demos sequentially |

**Dependencies:**
- `pilotcode.orchestration.TaskDecomposer`, `DecompositionStrategy`
- `pilotcode.orchestration.smart_coordinator.SmartCoordinator`
- `pilotcode.orchestration.auto_config.configure_auto_decomposition`, `get_auto_config`

---

## 2. `basic_decomposition.py` (84 lines)

**Purpose:** Minimal intro to basic task decomposition — analyzes tasks, prints strategies, subtasks, and dependencies.

**Key Classes:** (none defined; uses library classes)

**Key Functions:**
| Function | Signature | Description |
|---|---|---|
| `main` (async) | `()` | Runs 4 examples: simple task (no decompose), implementation with tests, refactoring, bug fix |

**Notable API usage:**
- `TaskDecomposer().analyze(task)` → returns `DecompositionResult` with `.strategy`, `.confidence`, `.reasoning`
- `TaskDecomposer().auto_decompose(task)` → returns full decomposition with `.subtasks`, each having `role`, `description`, `dependencies`

**Dependencies:**
- `pilotcode.orchestration.TaskDecomposer`, `DecompositionStrategy`, `TaskExecutor`, `AgentCoordinator`

---

## 3. `complex_task_demo.py` (299 lines)

**Purpose:** In-depth demo of complex task decomposition with scheduling strategies, execution simulation, metrics, and comparison of with/without decomposition.

**Key Classes:** (none defined)

**Key Functions:**
| Function | Signature | Description |
|---|---|---|
| `print_section` | `(title)` | Prints a formatted section header |
| `demo_complex_task_decomposition` | `()` | Decomposes 4 large tasks (auth system, microservices migration, security audit, DB optimization), prints subtasks with roles and dependencies |
| `demo_scheduling_strategies` | `()` | Illustrates 3 strategies: SEQUENTIAL (dependencies), PARALLEL (independent), HIERARCHICAL (supervisor-worker) with execution flow diagrams |
| `demo_execution_simulation` | `()` | Simulates sequential execution of decomposed "Implement REST API" task with timeline and `time.sleep(0.1)` |
| `demo_comparison` | `()` | Compares with vs without decomposition for a user auth task |
| `demo_metrics` | `()` | Lists 8 tracked metrics (complexity score, confidence, duration, success rate, parallel efficiency, agent utilization, tool usage) and example report |
| `main` (async) | `()` | Runs all 5 demos sequentially |

**Dependencies:**
- `pilotcode.orchestration.TaskDecomposer`, `DecompositionStrategy`
- `datetime.datetime`
- `time`

---

## 4. `real_world_usage.py` (323 lines)

**Purpose:** Real-world usage examples of the orchestration system — feature implementation, bug fix, code review, large-scale refactoring, performance optimization, and auto-decomposition configuration.

**Key Classes:**
| Class | Description |
|---|---|
| `MockModelClient` | Mock LLM client with `chat_completion(messages, stream)` → `dict` |
| `MockAgent` | Mock agent with `role`, `prompt`, `tools_used`, `started_at`, `completed_at`; `execute()` → `str` |

**Key Functions:**
| Function | Signature | Description |
|---|---|---|
| `agent_factory` | `(role, prompt) -> MockAgent` | Factory for mock agents |
| `example_1_feature_implementation` (async) | `()` | `AgentCoordinator` executes a profile-management feature with progress tracking callback |
| `example_2_bug_fix_workflow` (async) | `()` | `TaskDecomposer` analyzes a password-reset bug, prints fix plan, simulates agent execution |
| `example_3_code_review_automation` (async) | `()` | `SmartCoordinator.run_with_preview()` on a PR, prints decomposition preview |
| `example_4_refactoring_project` (async) | `()` | Decomposes Python 2→3 migration into phases with estimated complexity and duration |
| `example_5_performance_optimization` (async) | `()` | `AgentCoordinator.execute()` with forced `strategy="parallel"` for DB optimization |
| `example_6_configuring_automation` (async) | `()` | Prints current config and shows 4 configuration modes (conservative, aggressive, disable, re-enable) |
| `main` (async) | `()` | Runs all 6 examples sequentially |

**Dependencies:**
- `pilotcode.orchestration.AgentCoordinator`, `TaskDecomposer`, `DecompositionStrategy`
- `pilotcode.orchestration.smart_coordinator.SmartCoordinator`
- `pilotcode.orchestration.auto_config.configure_auto_decomposition`, `get_auto_config`, `enable_auto_decomposition`, `disable_auto_decomposition`
- `datetime.datetime`
- `asyncio`

---

## Cross-Cutting Observations

| Aspect | Details |
|---|---|
| **Core library class** | `TaskDecomposer` — used in all 4 files; methods: `analyze(task)`, `auto_decompose(task)` |
| **Coordinators** | `AgentCoordinator` (basic), `SmartCoordinator` (auto-decides decomposition); both take an `agent_factory` callable |
| **Key types** | `DecompositionStrategy` enum (NONE, SEQUENTIAL, PARALLEL, HIERARCHICAL), `DecompositionResult` (with `.strategy`, `.confidence`, `.reasoning`, `.subtasks`) |
| **Subtask model** | Each has: `id`, `role`, `description`, `prompt`, `dependencies`, `estimated_complexity`, `estimated_duration_seconds` |
| **Config system** | `pilotcode.orchestration.auto_config` with `configure_auto_decomposition()`, `get_auto_config()`, `enable_auto_decomposition()`, `disable_auto_decomposition()` |
| **All examples are mock-based** | No real LLM/agent calls; use `MockAgent`, `MockModelClient` for safe self-contained demos |
