# Core Orchestration Abstractions

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SmartCoordinator                                  │
│  "Should I decompose this request?"  ──►  auto_config                    │
│        │                                                                 │
│        ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │                    MissionAdapter                               │     │
│  │  Explore → Plan (LLM) → Execute (Orchestrator)                  │     │
│  │  Adapts via ContextStrategy (FRAMEWORK_HEAVY|BALANCED|LLM_HEAVY)│    │
│  │       │                                                         │     │
│  │       ▼                                                         │     │
│  │  ┌────────────────────── P-EVR CYCLE ──────────────────────┐    │     │
│  │  │                                                          │    │     │
│  │  │  PLAN               EXECUTE           VERIFY             │    │     │
│  │  │  ┌──────────┐     ┌──────────┐     ┌──────────────┐     │    │     │
│  │  │  │ Mission  │     │ Worker   │     │ L1: Static   │     │    │     │
│  │  │  │  ├Phase  │ ──► │ (Simple/ │ ──► │ L2: Tests    │     │    │     │
│  │  │  │  ├Phase  │     │ Standard/│     │ L3: Review   │     │    │     │
│  │  │  │  └Phase  │     │ Complex/ │     └──────┬───────┘     │    │     │
│  │  │  └────┬─────┘     │ Debug)   │            │             │    │     │
│  │  │       │           └──────────┘       ┌────┴────┐        │    │     │
│  │  │       ▼                              ▼         ▼        │    │     │
│  │  │  ┌──────────┐                  VERIFIED   NEEDS_REWORK  │    │     │
│  │  │  │ DagExec  │                     │          │          │    │     │
│  │  │  │ (Kahn)   │                     ▼          ▼          │    │     │
│  │  │  └──────────┘                  DONE      REFLECT ──►retry   │     │
│  │  │                                                          │    │     │
│  │  └──────────────────────────────────────────────────────────┘    │     │
│  └────────────────────────────┬─────────────────────────────────────┘     │
│                               │                                           │
│  ┌────────────────────────────┴─────────────────────────────────────┐     │
│  │                     Shared State Layer                            │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │     │
│  │  │MissionTracker│  │ProjectMemory │  │StateMachine (per task)   │ │     │
│  │  │ (global sing-│  │(file index,  │  │PENDING→ASSIGNED→IN_PROG  │ │     │
│  │  │ leton, SQLite│  │ conventions, │  │→SUBMITTED→UNDER_REVIEW   │ │     │
│  │  │ persistence) │  │ failures,    │  │→VERIFIED→DONE            │ │     │
│  │  │              │  │ architecture)│  │   ↓          ↓           │ │     │
│  │  └──────────────┘  └──────────────┘  │NEEDS_REWORK REJECTED     │ │     │
│  │                                       └──────────────────────────┘ │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Problem Domain Model

### Mission → Phase → TaskSpec (3-Layer Decomposition)

| Layer | Class | Responsibility |
|-------|-------|---------------|
| **L1** | `Mission` | Top-level unit of work. Holds the original user requirement, a list of phases, context budget, and strategy name. Serializable to/from dict. |
| **L2** | `Phase` | Strategic grouping of tasks (e.g., "Setup", "API Implementation", "Testing"). Has phase-level dependencies. |
| **L3** | `TaskSpec` | Single atomic executable task. Carries: `objective`, `inputs`/`outputs`, `dependencies`, `estimated_complexity` (1-5), `acceptance_criteria`, `constraints`, `context_budget`, `worker_type`. |

**Relationship:** `Mission` contains 1..N `Phase`s, each contains 1..N `TaskSpec`s. Dependencies declared at `TaskSpec` level form the DAG.

---

## 2. State Management

### TaskState & StateMachine

**Lifecycle (happy path):**

```
PENDING ──ASSIGN──► ASSIGNED ──START──► IN_PROGRESS ──SUBMIT──► SUBMITTED
                                                                      │
                                                              BEGIN_REVIEW
                                                                      ▼
  DONE ◄──COMPLETE── VERIFIED ◄──APPROVE── UNDER_REVIEW
```

**Lifecycle (with failure):**

```
UNDER_REVIEW ──REQUEST_REWORK──► NEEDS_REWORK ──RESUME──► IN_PROGRESS (retry)
UNDER_REVIEW ──REJECT─────────► REJECTED ──► (terminal)
PENDING ──BLOCK──► BLOCKED ──UNBLOCK──► PENDING
PENDING ──CANCEL──► CANCELLED (terminal)
```

Each `StateMachine` tracks one task: current state, full `StateChangeEvent` history, and callback-based listeners.

### MissionTracker (Global Singleton)

Central registry for all active missions. Manages:
- Mission → DAG mapping
- Per-task `StateMachine` instances
- Agent progress tracking
- Event emission (`mission:started`, `task:state_changed`, etc.)
- Optional SQLite persistence with WAL mode

---

## 3. Execution Engine

### DAG Executor

| Component | Role |
|-----------|------|
| `DagNode` | Wraps a `TaskSpec` with runtime `state`, `depth`, `result`, `artifacts` |
| `DagEdge` | Dependency edge; `from_task` must reach `VERIFIED` before `to_task` can run |
| `DagExecutor` | Builds DAG via Kahn's algorithm (topological sort), detects cycles, computes depth, identifies ready/blocked tasks, finds critical path, groups tasks into execution waves |

### Orchestrator

The main event loop driving P-EVR:

1. **Plan:** Takes a `Mission`, registers it with the `MissionTracker`, builds the DAG
2. **Execute Loop:** While `!all_done`:
   - Query ready tasks (dependencies satisfied)
   - Filter out tasks with failed dependencies (cascade cancel)
   - Execute up to `max_concurrent_workers` via `asyncio.Semaphore`
   - Transition: ASSIGN → START → EXECUTE (worker) → SUBMIT
3. **Verify:** L1 (static) → L2 (tests) → L3 (code review). Auto-approve VERY_SIMPLE after L1.
4. **Rework:** On `NEEDS_REWORK`, analyze failure, adjust task (reduce max_lines, add hints), retry up to `max_rework_attempts`. On max exceeded, reject and cascade-cancel downstream.

### Workers (Stateless)

| Worker | Complexity | Behavior |
|--------|-----------|----------|
| `SimpleWorker` | VERY_SIMPLE | Minimal turns, single-file edits |
| `StandardWorker` | SIMPLE/MODERATE | Moderate turns, multi-file |
| `ComplexWorker` | COMPLEX/VERY_COMPLEX | Extended turns, full QueryEngine |
| `DebugWorker` | (rework) | Used during retry cycles |

All registered as `Callable[[TaskSpec, dict], Awaitable[ExecutionResult]]` handlers. The `MissionAdapter` registers an LLM-based worker (`_llm_worker`) that uses `QueryEngine` with tool access.

---

## 4. Planning & Adaptation

### MissionAdapter

Bridges natural language → structured `Mission`:

1. **Explore Phase (P0):** Scans `**/*.py`, reads `pyproject.toml`/`README.md`, detects frameworks
2. **Plan Phase (P1):** Calls LLM with JSON schema to produce a `Mission` (phases, tasks, dependencies)
3. **Execute Phase (P2):** Delegates to `Orchestrator.run(mission)`

Also registers L1/L2/L3 verifiers and handles permission auto-allow for autonomous execution.

### ContextStrategy

Adapts the entire pipeline based on available context window tokens:

| Strategy | Context Budget | Key Behaviors |
|----------|---------------|---------------|
| `FRAMEWORK_HEAVY` | ≤ 12K | Max 2 files/task, 150-line max, L3 off, 2 retry max, aggressive decomposition |
| `BALANCED` | 12K–48K | Max 4 files/task, 300-line max, L3 on for complexity ≥ 3, 3 retries |
| `LLM_HEAVY` | > 48K | Max 8 files/task, 500-line max, all verifications, 5 retries, trusts LLM |

The `MissionPlanAdjuster` post-processes LLM-generated plans to enforce strategy constraints (caps complexity, adjusts constraints, selects worker type).

### SmartCoordinator

Thin wrapper: auto-decides whether to decompose by calling `should_auto_decompose(task, complexity_score)` from `auto_config`.

---

## 5. Shared Memory

### ProjectMemory (Working Memory — `orchestration/project_memory.py`)

Cross-task shared state injected into every worker prompt via `[PROJECT MEMORY]`:

| Field | Purpose |
|-------|---------|
| `file_index` | `FileSnapshot`s of every file read (path, hash, line count, summary) |
| `conventions` | Detected patterns: `{framework: FastAPI, testing_framework: pytest}` |
| `failed_attempts` | List of `FailedAttempt` records with root cause analysis |
| `architecture_notes` | Key decisions discovered |
| `changed_files` | Cumulative list of modified files across all tasks |

### Context Package (3-Layer Memory Architecture)

| Layer | Class | Scope | Persistence |
|-------|-------|-------|-------------|
| **L3** | `context.ProjectMemory` | Cross-session | `.pilotcode/project_memory.json` |
| **L2** | `context.SessionMemory` | Mission-level | Archive to `~/.pilotcode/sessions/` |
| **L1** | `context.WorkingMemory` | Single task | In-memory (trace queue, focus history) |

---

## 6. Verification

### Three-Level Verification Pipeline

| Level | Verifier | Method | Trigger |
|-------|----------|--------|---------|
| **L1** | `StaticAnalysisVerifier` / `_simple_verifier` | Execution success + output checks | Always |
| **L2** | `TestRunnerVerifier` / `_test_verifier` | `pytest` run | When test files exist or AC demands it |
| **L3** | `CodeReviewVerifier` / `_code_review_verifier` | LLM review of changed files | Complexity ≥ threshold (strategy-dependent) |

Each returns a `VerificationResult` with `verdict`: `APPROVE`, `NEEDS_REWORK`, or `REJECT`.

---

## 7. Reflection & Rework

### Reflector

Periodic health checks on missions:
- **Deadlock detection:** Tasks pending but none ready or in-progress
- **Rework rate:** Triggers redesign if > 50%
- **Stalled tasks:** In-progress too long
- **Critical path blocked:** Alerts on blocked critical-path tasks

### ReworkContext

Preserved across retry attempts:
- `preserve`: What to keep from previous attempts
- `must_change`: What must be fixed
- `lessons_learned`: Why previous attempts failed
- `ReworkSeverity`: MINOR → MAJOR → CRITICAL escalates worker type and may trigger redesign

---

## 8. Reporting

| Function | Purpose |
|----------|---------|
| `format_plan(mission)` | Tree-view of phases and tasks before execution |
| `format_progress(snapshot)` | Live progress with emoji state indicators |
| `format_completion(result)` | Final summary with task outputs |
| `format_failure(result)` | Failure explanation with problematic tasks |
| `format_task_event(event, data)` | Real-time event formatting (20+ event types) |

---

## 9. Configuration

### AutoDecompositionConfig

Global toggle controlling automatic decomposition heuristics:
- `enabled` — master switch
- `simple_task_threshold` — max complexity to skip decomposition (default: 2)
- `max_simple_task_length` — tasks shorter than this character count are auto-simple
- `require_confirmation` — if True, prompts user before decomposing

### OrchestratorConfig

Tuning parameters: `max_concurrent_workers`, `auto_approve_simple`, enable/disable L1/L2/L3, `max_rework_attempts`, `db_path`.

---

## 10. Key Relationships Summary

```
SmartCoordinator
    │
    ├── auto_config (AutoDecompositionConfig)
    └── MissionAdapter
            │
            ├── ContextStrategySelector ──► ContextStrategy (FRAMEWORK_HEAVY|BALANCED|LLM_HEAVY)
            │       └── MissionPlanAdjuster ──► adjusts Mission before execution
            │
            ├── ProjectMemory (shared across tasks)
            │
            ├── _explore_codebase() ──► populates ProjectMemory
            │
            ├── _plan_mission() ──► Mission ──► Phases ──► TaskSpecs
            │
            └── Orchestrator
                    │
                    ├── MissionTracker (global singleton)
                    │       ├── DagExecutor (per mission)
                    │       │       ├── DagNode[] (per task)
                    │       │       └── DagEdge[] (dependencies)
                    │       └── StateMachine[] (per task)
                    │
                    ├── Worker Registry (LLM-powered via QueryEngine)
                    │
                    ├── Verifier Registry (L1/L2/L3)
                    │
                    ├── ReworkContext + Reflector
                    │
                    └── Report (format_plan/format_progress/format_completion)
```
