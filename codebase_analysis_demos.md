# Orchestration Demos Analysis

Analysis of the four demo files under `examples/orchestration/`.

---

## 1. basic_decomposition.py (84 lines)

**Purpose:** Introduce core decomposition APIs — the "getting started" demo.

**Orchestration Approach:**
- Uses `TaskDecomposer` directly; no agent execution, only analysis.
- Runs four examples that exercise two entry points:
  - `decomposer.analyze(task)` — heuristic-only, returns a `result` with `strategy`, `confidence`, `reasoning`, and `subtasks`.
  - `decomposer.auto_decompose(task)` — full decomposition on complex tasks; returns populated `subtasks`.

**APIs Demonstrated:**
| API | Role |
|-----|------|
| `TaskDecomposer` | Central decomposer class |
| `DecompositionStrategy` | Enum of strategies (NONE, SEQUENTIAL, PARALLEL, HIERARCHICAL) |
| `.analyze(task)` | Lightweight heuristic analysis |
| `.auto_decompose(task)` | Full decomposition into subtasks |

**Decomposition Strategies Observed:**
- Simple file-read → `NONE` (no decomposition).
- Implement auth system → sub-tasks with `role`, `description`, `dependencies` fields.
- Refactoring and bug-fix → similar structured breakdowns.

**Unique Feature:** Acts as a smoke test. If this runs, the core `TaskDecomposer` contract works.

---

## 2. real_world_usage.py (323 lines)

**Purpose:** "Day-in-the-life" walkthrough — six end-to-end scenarios for actual development workflows.

**Orchestration Approach:**
- Fully async; mixes decomposition + execution + progress tracking.
- Introduces mock agent factories (`agent_factory`) and a `MockModelClient` to simulate real execution without needing a live LLM.

**Six Examples:**

| # | Example | Key Classes Used | Notable Pattern |
|---|---------|-----------------|-----------------|
| 1 | Feature Implementation | `AgentCoordinator` | `auto_decompose=True`, progress callback via `coordinator.on_progress()`, metadata-driven result summary |
| 2 | Bug Fix Workflow | `TaskDecomposer` | Manual step-by-step execution loop over subtasks (no coordinator) |
| 3 | Code Review Automation | `SmartCoordinator` | `run_with_preview(task)` — preview before execution, shows estimated duration |
| 4 | Large-Scale Refactoring | `TaskDecomposer` | Rich subtask metadata: `estimated_complexity` (star rating), `estimated_duration_seconds`, dependency chains |
| 5 | Performance Optimization | `AgentCoordinator` | Forced `strategy="parallel"` override, parallel efficiency calculation |
| 6 | Configuring Automation | `auto_config` module | `configure_auto_decomposition()`, `enable_auto_decomposition()`, `disable_auto_decomposition()`, `get_auto_config()` |

**APIs Demonstrated:**
| API | Role |
|-----|------|
| `AgentCoordinator(agent_factory)` | High-level executor; takes a task string, optionally auto-decomposes, runs agents |
| `SmartCoordinator(agent_factory)` | Smarter variant; decides *if* decomposition is worthwhile |
| `coordinator.on_progress(callback)` | Event hook: `task_starting`, `task_completed` |
| `coordinator.execute(task, strategy, auto_decompose)` | Main entry; returns result with `status`, `duration_seconds`, `metadata`, `summary` |
| `coordinator.run_with_preview(task)` | Returns `(result, preview)` — preview includes `will_decompose`, `strategy`, `subtasks`, `estimated_duration` |
| `auto_config.configure_auto_decomposition(...)` | Global config: `enabled`, `min_confidence`, `require_confirmation` |
| `auto_config.get_auto_config()` | Returns current `AutoConfig` |
| `auto_config.enable_auto_decomposition()` / `disable_auto_decomposition()` | Convenience toggles |
| `TaskDecomposer` | Used standalone for analysis without execution |
| `DecompositionStrategy` | Enum (implicitly used) |

**Decomposition Strategies Observed:**
- Sequential (default) for refactoring, bug fixes, feature work.
- Parallel (explicit override) for independent review/optimization tasks.

**Unique Features:**
- **Progress Events:** `on_progress` callback with `task_starting`/`task_completed` events.
- **Run-with-Preview:** `SmartCoordinator.run_with_preview()` for dry-run analysis before committing.
- **Forced Strategy Override:** `strategy="parallel"` bypasses heuristic choice.
- **Auto-Configuration:** Global toggles for decomposition behavior.

---

## 3. auto_decomposition_demo.py (186 lines)

**Purpose:** Deep-dive into *when and why* tasks are automatically decomposed.

**Orchestration Approach:**
- Heuristic-driven; focuses on the decision layer, not execution.
- Uses `TaskDecomposer.analyze()` (not `auto_decompose`) for lightweight checks.
- Introduces `SmartCoordinator` as the decision-making coordinator.

**Four Demos:**

| # | Demo | Focus |
|---|------|-------|
| 1 | Heuristic Analysis | 8 test cases (simple vs. complex); validates that the decomposer correctly classifies which tasks need breakdown |
| 2 | Auto Patterns | Four canonical patterns (Implementation, Refactoring, Bug Fix, Code Review) with full subtask output |
| 3 | Smart Coordinator | Shows that `SmartCoordinator` delegates to its internal `decomposer.analyze()` to decide |
| 4 | Configuration | Displays `AutoConfig` fields: `enabled`, `min_confidence`, `simple_task_threshold`, `require_confirmation` |

**APIs Demonstrated:**
| API | Role |
|-----|------|
| `TaskDecomposer.analyze(task)` | Returns `result.strategy` and `result.confidence` without full decomposition |
| `DecompositionStrategy.NONE` | Sentinel for "no decomposition needed" |
| `SmartCoordinator(agent_factory)` | Has a `.decomposer` attribute for analysis |
| `configure_auto_decomposition(...)` | Global tuning |
| `get_auto_config()` | Inspect current settings |

**Decomposition Strategies Observed:**
- `NONE` for simple read/list/find tasks.
- `SEQUENTIAL` or `PARALLEL` for implementation, refactoring, bug fix, review.

**Unique Features:**
- **Heuristic Test Harness:** Provides a ready-made validation suite with expected outcomes.
- **"Will Decompose" Boolean:** Clear yes/no decision per task, useful for debugging the heuristic.
- **Pattern Catalog:** Names the four canonical patterns the system recognizes (Implementation, Refactoring, Bug Fix, Code Review).

---

## 4. complex_task_demo.py (299 lines)

**Purpose:** Stress-test the system with large, real-world-scale tasks and demonstrate all scheduling strategies.

**Orchestration Approach:**
- Primarily uses `TaskDecomposer` (no external coordinator execution).
- Deep dives into the *structure* and *strategy* of decomposition.
- Demonstrates timeline simulation and comparative analysis.

**Five Demos:**

| # | Demo | Focus |
|---|------|-------|
| 1 | Complex Task Decomposition | Four large tasks (auth system, microservices migration, security audit, DB optimization) with full subtask breakdown |
| 2 | Scheduling Strategies | Visual walkthrough of SEQUENTIAL, PARALLEL, and HIERARCHICAL strategies with flow diagrams |
| 3 | Execution Simulation | Simulated timeline with `time.sleep()` showing task ordering and dependency propagation |
| 4 | With vs. Without Comparison | Side-by-side benefits of decomposition (specialization, tracking, parallelization) |
| 5 | Execution Metrics | Catalog of tracked metrics and a sample execution report |

**APIs Demonstrated:**
| API | Role |
|-----|------|
| `TaskDecomposer.auto_decompose(task)` | Full decomposition for complex tasks |
| `DecompositionStrategy` | NONE, SEQUENTIAL, PARALLEL, HIERARCHICAL |
| `result.subtasks[i].dependencies` | Dependency graph between subtasks |
| `result.subtasks[i].role` | Agent role assignment (`coder`, `debugger`, `tester`, `planner`) |
| `result.subtasks[i].estimated_complexity` | Star-rating for complexity |
| `result.subtasks[i].estimated_duration_seconds` | Time estimate |

**Decomposition Strategies Deep Dive:**
- **SEQUENTIAL:** Tasks depend on each other; results pass forward. Used when output of Step N feeds Step N+1.
- **PARALLEL:** Independent tasks run simultaneously; results collected at end. Used for reviews, audits.
- **HIERARCHICAL:** Supervisor-worker model. Supervisor creates breakdown, workers execute in parallel, supervisor synthesizes results.

**Metrics Catalog (Demo 5):**
- Task Complexity Score
- Decomposition Confidence (0.0–1.0)
- Estimated vs. Actual Duration
- Success Rate (completed / total)
- Parallel Efficiency
- Agent Utilization
- Tool Usage Count

**Unique Features:**
- **Strategy Visualization:** ASCII-art flow diagrams for each strategy.
- **Execution Timeline Simulation:** Timestamped step-by-step with dependency arrows.
- **A/B Comparison:** "With vs. Without Decomposition" table.
- **Sample Report:** Pre-formatted execution report template showing real-world output shape.

---

## Cross-Cutting Summary

### Orchestration Patterns

| Pattern | Where Used | Description |
|---------|-----------|-------------|
| **Analyze-then-Decide** | All four | `TaskDecomposer.analyze()` returns confidence + strategy; caller decides whether to decompose |
| **Auto-Decompose** | basic, complex, real_world | `auto_decompose(task)` does full breakdown in one call |
| **Execute-by-Coordinator** | real_world | `AgentCoordinator.execute(task, auto_decompose=True)` handles both decompose and run |
| **Preview-before-Execute** | real_world | `SmartCoordinator.run_with_preview()` shows plan before committing |
| **Manual Step Loop** | real_world (bug fix) | Loop over `result.subtasks`, create agents, `await agent.execute()` |
| **Forced Strategy** | real_world | Pass `strategy="parallel"` to override heuristics |
| **Progress Callbacks** | real_world | `coordinator.on_progress(handler)` for streaming updates |
| **Global Configuration** | auto_decomposition, real_world | `configure_auto_decomposition()`, `enable/disable` toggles |

### Agent Roles
Observed across all demos: `planner`, `coder`, `debugger`, `tester`, `reviewer`. Each subtask gets a role-matched agent.

### Key Data Structures
- `result.strategy` — `DecompositionStrategy` enum
- `result.confidence` — float 0.0–1.0
- `result.subtasks[]` — each has `id`, `role`, `description`, `prompt`, `dependencies`, `estimated_complexity`, `estimated_duration_seconds`
- `result.metadata` — dict with `decomposed`, `subtask_count`, `success_count`, `strategy`
- `AutoConfig` — `enabled`, `min_confidence`, `simple_task_threshold`, `require_confirmation`

### File Size Check
- This document: well under 300 lines. ✓
