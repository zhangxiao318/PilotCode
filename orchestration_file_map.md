# Orchestration File Map & Module Summary

## I. CORE ORCHESTRATION PACKAGE: `src/pilotcode/orchestration/`

### Entry Points & Public API
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 1 | `src/pilotcode/orchestration/__init__.py` | Public API surface; re-exports all key types (TaskSpec, Mission, Orchestrator, StateMachine, DagExecutor, verifiers, memory layers, reporters) | All sub-modules below |
| 2 | `src/pilotcode/orchestration/smart_coordinator.py` | Thin wrapper over MissionAdapter that auto-decides whether to use structured P-EVR planning or simple execution | `adapter.MissionAdapter`, `auto_config` |
| 3 | `src/pilotcode/orchestration/integration.py` | Integrates P-EVR orchestration with existing PilotCode systems; provides `OrchestrationAdapter` facade | `adapter.MissionAdapter` |

### Core Logic: Plan → DAG Build → Execute → Verify → Reflect
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 4 | `src/pilotcode/orchestration/orchestrator.py` | **Central orchestrator** drives the full P-EVR lifecycle: plan, DAG build, execute (worker dispatch), 3-level verify, smart retry, cascade failure handling. Registers workers/verifiers, manages concurrency semaphore. | `task_spec`, `state_machine`, `dag`, `tracker` |
| 5 | `src/pilotcode/orchestration/task_spec.py` | **Data models**: `TaskSpec`, `Phase`, `Mission`, `ComplexityLevel`, `Constraints`, `AcceptanceCriterion`. Serializable to/from dict for LLM plan generation. | None (pure dataclasses) |
| 6 | `src/pilotcode/orchestration/state_machine.py` | **Task state machine**: 11 states (PENDING→ASSIGNED→IN_PROGRESS→SUBMITTED→UNDER_REVIEW→VERIFIED→DONE / NEEDS_REWORK / REJECTED / BLOCKED / CANCELLED), 12 transitions with strict transition table. | None (pure enum/dataclass) |
| 7 | `src/pilotcode/orchestration/dag.py` | **DAG builder & executor**: Kahn's algorithm topological sort, dependency resolution, execution waves (parallel batches), critical path calculation, ready/blocked task queries. | `task_spec`, `state_machine` |
| 8 | `src/pilotcode/orchestration/tracker.py` | **Global mission tracker** (singleton): holds all missions, DAGs, state machines, agent progress. Persists to SQLite with WAL mode. Emits events. Provides `MissionSnapshot`. | `task_spec`, `state_machine`, `dag` |

### Communication Adapter (LLM Bridge)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 9 | `src/pilotcode/orchestration/adapter.py` | **MissionAdapter** — the primary entry point: converts natural language → LLM-planned Mission → orchestrator execution. Includes LLM-based worker, 3 verifiers (L1/L2/L3), explore-plan loop, project memory integration, continue-prompt builder, tool→memory bridge. | `orchestrator`, `task_spec`, `context_strategy`, `project_memory`, `query_engine`, `model_client`, `tools.registry`, `permissions` |

### Configuration & Strategy
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 10 | `src/pilotcode/orchestration/context_strategy.py` | **Context-aware strategy framework**: 3 strategies (FRAMEWORK_HEAVY for ≤12K tokens, BALANCED for 12K–48K, LLM_HEAVY for >48K). Each strategy has tuned configs for task granularity, verification layers, rework limits, and planner prompt suffix. `MissionPlanAdjuster` modifies missions per strategy. `StrategyMetrics` collects execution stats. | `task_spec` |
| 11 | `src/pilotcode/orchestration/auto_config.py` | **Auto-decomposition config**: thresholds for when to auto-decompose tasks (complexity score, task length). Global toggle. | None (standalone config) |

### Verification Layer (`verifier/`)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 12 | `src/pilotcode/orchestration/verifier/__init__.py` | Verifier package exports: `VerificationResult`, `Verdict`, `BaseVerifier`, `StaticAnalysisVerifier`, `TestRunnerVerifier`, `CodeReviewVerifier` | All verifier modules |
| 13 | `src/pilotcode/orchestration/verifier/base.py` | **Base verifier**: abstract `BaseVerifier` class, `VerificationResult` dataclass, `Verdict` enum (APPROVE/NEEDS_REWORK/REJECT/PENDING) | None |
| 14 | `src/pilotcode/orchestration/verifier/level1_static.py` | **L1 Static Analysis**: checks file existence, line limits, forbidden/required patterns, must_use/must_not_use constraints. Scoring 0-100. | `base`, `task_spec`, `orchestrator` |
| 15 | `src/pilotcode/orchestration/verifier/level2_tests.py` | **L2 Test Execution**: discovers test files, runs pytest, parses failures, extracts coverage. Auto-passes if no tests. | `base`, `task_spec`, `orchestrator` |
| 16 | `src/pilotcode/orchestration/verifier/level3_review.py` | **L3 Code Review**: heuristic code review checking acceptance criteria, objective alignment (keyword matching), TODO/FIXME, error handling, function length, docstrings. | `base`, `task_spec`, `orchestrator` |

### Worker Layer (`workers/`)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 17 | `src/pilotcode/orchestration/workers/__init__.py` | Worker package exports | All worker modules |
| 18 | `src/pilotcode/orchestration/workers/base.py` | **BaseWorker**: abstract base with `execute()` method, `WorkerContext` dataclass, `_build_prompt()` with rework context support | `task_spec`, `orchestrator` |
| 19 | `src/pilotcode/orchestration/workers/simple_worker.py` | **SimpleWorker**: for single-file <50 line changes; focused prompt strategy | `base` |
| 20 | `src/pilotcode/orchestration/workers/standard_worker.py` | **StandardWorker**: for module-level work with related files context injection | `base` |
| 21 | `src/pilotcode/orchestration/workers/complex_worker.py` | **ComplexWorker**: for cross-module architecture tasks with full project context | `base` |
| 22 | `src/pilotcode/orchestration/workers/debug_worker.py` | **DebugWorker**: for surgical fixes, preserves working parts, minimal changes | `base` |

### Rework & Reflection Layer (`rework/`)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 23 | `src/pilotcode/orchestration/rework/__init__.py` | Rework package exports | `rework_context`, `reflector` |
| 24 | `src/pilotcode/orchestration/rework/rework_context.py` | **ReworkContext**: preserves what to keep (`preserve`), what to fix (`must_change`), why failed (`lessons_learned`). Tracks attempts with severity levels (MINOR/MAJOR/CRITICAL/BLOCKED). Determines retry strategy. | None |
| 25 | `src/pilotcode/orchestration/rework/reflector.py` | **Reflector**: periodic mission health checks — deadlock detection, rework rate monitoring, stalled task detection, critical path health, redesign triggers | `tracker`, `dag`, `state_machine` |

### Memory / Context Layer (`context/`)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 26 | `src/pilotcode/orchestration/context/__init__.py` | Context package exports: ProjectMemory, SessionMemory, WorkingMemory | All context modules |
| 27 | `src/pilotcode/orchestration/context/project_memory.py` | **L3 Project Memory** (cross-session, persistent): tech stack, architecture patterns, API conventions, learned patterns from rework. Saved to `.pilotcode/project_memory.json`. | None (file I/O) |
| 28 | `src/pilotcode/orchestration/context/session_memory.py` | **L2 Session Memory** (mission-level): DAG state, artifact versioning, state history. Archives completed sessions to disk with full execution trace. | `task_spec`, `state_machine` |
| 29 | `src/pilotcode/orchestration/context/working_memory.py` | **L1 Working Memory** (task-level): execution trace (last 50 steps), code context, focus tracking, context summary for prompt injection (Goal Anchoring). Compresses to `TaskSummary` for L2 storage. | None |

### Reporting
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 30 | `src/pilotcode/orchestration/report.py` | **Human-readable reports**: `format_plan()`, `format_progress()`, `format_completion()`, `format_failure()`, `format_task_event()` with emoji-rich output | `task_spec`, `tracker` |

### Top-Level Project Memory (re-exported from `__init__.py`)
| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 31 | `src/pilotcode/orchestration/project_memory.py` | **ProjectMemory** (worker-shared): file index snapshots, discovered conventions, module graph, failed attempt tracking, architecture notes, changed files. Generates `[PROJECT MEMORY]` prompt sections for worker context injection. | None (hashing, file I/O) |

---

## II. ADJACENT ORCHESTRATION SERVICES

| # | File | Purpose | Key Dependencies |
|---|------|---------|-----------------|
| 32 | `src/pilotcode/agent/agent_orchestrator.py` | **AgentOrchestrator**: multi-agent workflow orchestration (SEQUENTIAL, PARALLEL, MAP_REDUCE, SUPERVISOR, DEBATE, PIPELINE). Delegates to `MissionAdapter` for execution. | `agent_manager`, `model_client`, `tools.base`, `orchestration.adapter` |
| 33 | `src/pilotcode/services/tool_orchestrator.py` | **ToolOrchestrator**: concurrent tool execution with batch analysis, read-only parallelism, semaphore-limited concurrency, caching integration. Groups tools into parallel/sequential batches. | `tools.base`, `tools.registry`, `services.tool_cache` |

---

## III. TEST FILES

| # | File | Purpose |
|---|------|---------|
| 34 | `tests/test_orchestration.py` | Comprehensive tests for P-EVR: state machine transitions, DAG construction, parallel/diamond/multi-phase missions, rework cycles, verification pipelines, memory layers, cascade failures (1058 lines) |
| 35 | `tests/orchestration/test_context_strategy.py` | Unit tests for context strategy: threshold boundaries, plan adjustment (complexity caps, line limits, budget), metadata tagging, immutability, prompt suffix variation (357 lines) |
| 36 | `tests/orchestration/experiment_context_strategy.py` | Experiment script: simulates mission execution under different strategies to validate framework-heavy vs LLM-heavy effectiveness (505 lines) |
| 37 | `tests/orchestration/experiment_results.json` | Cached experiment results for context strategy comparison |

---

## IV. DOCUMENTATION & EXAMPLES

| # | File | Purpose |
|---|------|---------|
| 38 | `docs/features/p-evr-task-orchestration.md` | Full P-EVR design document: architecture diagrams, state machine spec, three-layer memory, rework cycle, verification pipeline, context strategy framework (497 lines) |
| 39 | `docs/archive/orchestration/README.md` | Archived orchestration documentation |
| 40 | `examples/orchestration/basic_decomposition.py` | Example: basic task decomposition and execution demo |
| 41 | `examples/orchestration/complex_task_demo.py` | Example: complex multi-task orchestration demo |
| 42 | `examples/orchestration/auto_decomposition_demo.py` | Example: automatic decomposition threshold demo |
| 43 | `examples/orchestration/real_world_usage.py` | Example: real-world orchestration usage patterns |
| 44 | `examples/orchestration/code_smells.json` | Example data: code smell definitions for verification |
| 45 | `examples/orchestration/SUMMARY.md` | Summary of orchestration examples |

---

## ARCHITECTURE OVERVIEW

```
                    ┌─────────────────────────────────────┐
                    │     MissionAdapter (adapter.py)      │  ← User-facing entry point
                    │   NL → LLM Plan → Mission → Run      │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │     Orchestrator (orchestrator.py)   │  ← Core P-EVR engine
                    │  Plan → DAG → Execute → Verify → Refl │
                    └──┬────────┬────────┬────────┬───────┘
                       │        │        │        │
              ┌────────▼──┐ ┌──▼───┐ ┌──▼───┐ ┌──▼──────┐
              │ task_spec │ │ dag  │ │state │ │ tracker  │
              │ (models)  │ │(topo)│ │mach. │ │(global)  │
              └───────────┘ └──────┘ └──────┘ └─────────┘
                       │                         │
          ┌────────────┼────────────┐            │
          ▼            ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ verifier/│ │ workers/ │ │ rework/  │ │ context/ │
    │ L1 L2 L3 │ │sim/std/  │ │ctx+refl. │ │L1/L2/L3  │
    └──────────┘ │cmpx/debug│ └──────────┘ └──────────┘
                 └──────────┘

Adjacent services:
  • AgentOrchestrator (agent/) → multi-agent workflows via MissionAdapter
  • ToolOrchestrator  (services/) → concurrent tool execution + caching
  • context_strategy  → adaptive framework based on context window size
  • auto_config       → auto-decomposition thresholds
  • project_memory    → cross-worker shared state (file index, failures, conventions)
  • report            → human-readable formatting (emoji progress, plan tree)
```
