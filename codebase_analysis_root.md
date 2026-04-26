# Root-Level Orchestration Modules — Structured Analysis

> Generated from direct source inspection. Focus: task decomposition, dependency handling, parallelism, error tracing.

---

## 1. `scan_tools.py` — AI Tool & File Scanner

**Purpose:** Discover AI/ML-related files and configuration assets in the current directory tree.

**Key Components:**
- `scan_ai_tools()` — Walks directory (excluding `.git`), matches file names and content against ~40 AI keywords (`torch`, `tensorflow`, `llm`, `nlp`, `pipeline`, …), produces a list of `{path, type, description}` dicts.
- `main()` — Prints results grouped by type (`ai_related_file`, `configuration_file`, `script`), caps output at 100 entries.

**Orchestration Features:**
- **Task decomposition:** None — purely discovery, no task model.
- **Dependency handling:** Pattern-based file classification only; no inter-file dependency graph.
- **Parallelism:** None (single-threaded `os.walk`).
- **Error tracing:** Silent `except Exception: pass` on unreadable files — weak error handling.

---

## 2. `parallel_test.py` — Concurrency Safety Test Harness

**Purpose:** Demonstrate and test thread-safety issues with shared mutable state under `concurrent.futures.ThreadPoolExecutor`.

**Key Components:**
- Unsafe operations: `increment_counter()` / `append_to_list()` — read-modify-write races on globals.
- Safe operations: `safe_increment_counter()` / `safe_append_to_list()` — wrap critical sections with `threading.Lock()`.
- Four test functions: `test_unsafe_operations`, `test_safe_operations`, `test_list_operations`, `test_safe_list_operations` — each resets state, submits 10 tasks across 5 workers, logs final values.

**Orchestration Features:**
- **Task decomposition:** Manual test case grouping; no formal decomposition.
- **Dependency handling:** None — tasks are fire-and-forget with `concurrent.futures.wait()`.
- **Parallelism:** Core feature — `ThreadPoolExecutor(max_workers=5)`, demonstrates lock-based mutual exclusion for shared counters/lists.
- **Error tracing:** Standard `logging` with thread-name prefix; no structured error propagation.

---

## 3. `task_dependency_analysis.py` — Dependency Graph Analyzer

**Purpose:** Build a directed acyclic graph from task specs, detect dependency defects, and derive topological execution order.

**Key Components:**
- `TaskDependencyAnalyzer` class:
  - `__init__()` — Creates `nx.DiGraph()` (NetworkX) and `defaultdict(list)` for dependency storage.
  - `analyze_task_dependencies(task_list)` — Parses `{id, description, depends_on}` dicts, populates graph nodes/edges, runs cycle detection (`nx.simple_cycles`), topological sort (`nx.topological_sort`), and defect identification.
  - `_identify_defects()` — Three defect types: `undefined_dependency` (predecessor not in node set), `circular_dependency` (cycles), `isolated_task` (in-degree=0 and out-degree=0).
  - `_export_graph()` — Returns `{nodes, edges, adjacency}` dict.
- `generate_recommendations()` — Outputs 8 generic improvement suggestions (validation, visualization, dynamic adjustment).
- `main()` — Runs analyzer against a 5-task sample pipeline (data-collect → process → analyze → report + validate).

**Orchestration Features:**
- **Task decomposition:** Consumes pre-decomposed task lists; no auto-decomposition.
- **Dependency handling:** Full DAG construction with cycle detection, undefined-dependency checking, isolation detection. Topological sort provides execution order — foundational for real orchestrator.
- **Parallelism:** None — analysis is single-threaded; topological order could feed wave-based parallel execution but doesn't.
- **Error tracing:** Defect classification by severity type; YAML report generation.

---

## 4. `error_tracing_analysis.py` — Error Propagation & Root-Cause Analyzer

**Purpose:** Model error causality chains as a graph, identify tracing gaps, and compute impact scope.

**Key Components:**
- `ErrorTracingAnalyzer` class:
  - `__init__()` — Two `nx.DiGraph()` instances (error graph + dependency graph), `error_nodes` set, `error_context` defaultdict.
  - `analyze_error_tracing_mechanism(error_log)` — Builds error dependency graph from structured error dicts (`error_id`, `error_type`, `depends_on`, `call_stack`), runs defect detection and impact analysis.
  - `_build_error_dependency_graph()` — Adds error nodes, dependency edges, and call-stack edges (caller→callee chains).
  - `_identify_tracing_defects()` — Four defect types: `incomplete_error_info` (missing `error_type`), `circular_error_dependency`, `undefined_error_dependency`, `isolated_error_node` — each with `severity` levels.
  - `_analyze_impact_scope()` — Aggregates affected components, cascade effects (out-degree > 1), severity distribution, root causes.
  - `generate_recommendations()` — 10 suggestions including error classification, visualization, root-cause analysis, pattern recognition.
- `main()` — Demonstrates with 3 cascading errors: FileNotFoundError → ValueError → RuntimeError.

**Orchestration Features:**
- **Task decomposition:** Not task-oriented — error-event-oriented.
- **Dependency handling:** Graph-based error propagation chains; cascade effect detection tracks how one error spawns downstream failures.
- **Parallelism:** None.
- **Error tracing:** Core feature — full call-stack modeling, dependency-chain traversal, severity-level tracking, impact-scope analysis. Directly addresses error tracing gaps in orchestration.

---

## 5. `exception_analysis.py` — Exception Handling Audit

**Purpose:** Static analysis (print-based report) identifying anti-patterns in exception handling: over-broad `except Exception`, silent `pass`, missing `traceback` usage.

**Key Components:**
- `analyze_exception_handling()` — Prints 5 analysis sections: broad-catch detection, missing classification, silent failure, missing `finally` blocks, missing `traceback` module usage.
- `demonstrate_improvements()` — Shows before/after code patterns: broad `except Exception: pass` → specific `FileNotFoundError` / `PermissionError` with logging and `traceback.print_exc()`.
- `main()` — Orchestrates analysis + demonstration, prints summary of 5 problems and 5 improvement recommendations. Notably wraps itself in `except Exception` as a meta-demonstration.

**Orchestration Features:**
- **Task decomposition:** None.
- **Dependency handling:** None.
- **Parallelism:** None.
- **Error tracing:** The entire module is about error tracing gaps — identifies missing structured error recording, missing traceback, missing classification. Purely advisory; no automated fix.

---

## 6. `full_demo.py` — Feature Showcase & Architecture Walkthrough

**Purpose:** Interactive console demo of all PilotCode features — tools, commands, task management, architecture tree.

**Key Components:**
- `show_header()` — Rich `Panel` with version banner.
- `show_tools()` — Queries `get_all_tools()`, builds Rich `Table` with name/aliases/read-only/concurrency-safe/description columns.
- `show_commands()` — Queries `get_all_commands()`, displays slash-commands table.
- `demo_tasks()` (async) — Creates 3 background tasks via `TaskCreateTool`, lists them via `TaskListTool`, demonstrates task lifecycle.
- `show_architecture()` — Rich `Tree` of PilotCode architecture (Types → Tools → Commands → State → Services).
- `main()` (async) — Orchestrates full demo sequence, prints implementation summary.

**Orchestration Features:**
- **Task decomposition:** Demonstrates `TaskCreateTool` for ad-hoc task creation; no structural decomposition.
- **Dependency handling:** None — tasks are independent fire-and-forget.
- **Parallelism:** Tasks created as background processes run independently; demo shows concurrent task status via `TaskListTool`.
- **Error tracing:** None.

---

## 7. `run_single_instance.py` — SWE-bench Single-Instance Runner

**Purpose:** Run a single SWE-bench Lite instance through the PilotCode harness for isolated testing/evaluation.

**Key Components:**
- `load_instance_cached(instance_id)` — Loads instance from `/home/zx/.cache/swe-bench-lite.json` cache or falls back to `swebench.harness.utils.load_swebench_dataset("princeton-nlp/SWE-bench_Lite", "test")`.
- `main()` — CLI: `python run_single_instance.py <instance_id> [--output predictions_single.jsonl]`. Calls `solve_instance()` from the harness, appends prediction JSON line to output file.

**Orchestration Features:**
- **Task decomposition:** Delegates entirely to `solve_instance()` in the harness — opaque.
- **Dependency handling:** None at this level; harness handles internally.
- **Parallelism:** Single-instance only — designed for debugging, not batch execution.
- **Error tracing:** Minimal — exits with code 1 if instance not found.

---

## 8. `run_meta_analysis.py` — WebSocket Meta-Analysis Client

**Purpose:** Connect to PilotCode's WebSocket server (`ws://127.0.0.1:28081`) and send a comprehensive orchestration-system refactoring prompt, streaming results back and saving to `meta_analysis_result.md`.

**Key Components:**
- `ANALYSIS_PROMPT` (module-level constant) — A detailed prompt targeting 9 orchestration files (`adapter.py`, `orchestrator.py`, `dag.py`, `tracker.py`, `state_machine.py`, `project_memory.py`, `context_strategy.py`, `verifier/level2_tests.py`, `agent_orchestrator.py`) asking for design-flaw identification, concurrency/race analysis, error-handling gaps, performance bottlenecks, testing gaps, and P-EVR architecture alignment.
- `run_analysis()` (async) — Connects via `websockets.connect`, creates session, sends query in `PLAN` mode, auto-approves all permissions, handles streaming events (`streaming_chunk`, `streaming_end`, `streaming_error`, `interrupted`, `planning_progress`, `system`), collects output, saves to `meta_analysis_result.md`.

**Orchestration Features:**
- **Task decomposition:** The prompt itself requests analysis of decomposition in `orchestrator.py` and `adapter.py` Plan phase.
- **Dependency handling:** Prompt targets `dag.py` (DAG construction, topological sort, execution waves) and dependency-related flaws.
- **Parallelism:** Prompt targets concurrency/race conditions in the orchestrator and agent orchestrator.
- **Error tracing:** Prompt targets error handling gaps across all orchestration modules, verifier pipeline, and state machine transitions.

---

## Cross-Cutting Summary

| File | Task Decomp | Dependency | Parallelism | Error Tracing |
|------|:-----------:|:----------:|:-----------:|:-------------:|
| `scan_tools.py` | — | pattern-based | — | weak (silent pass) |
| `parallel_test.py` | — | — | **lock/race demo** | logging only |
| `task_dependency_analysis.py` | consumes tasks | **DAG+cycles+topo** | — | defect types |
| `error_tracing_analysis.py` | — | **cascade graph** | — | **root-cause+impact** |
| `exception_analysis.py` | — | — | — | audit report |
| `full_demo.py` | via TaskCreateTool | — | bg tasks | — |
| `run_single_instance.py` | opaque (harness) | — | single only | exit code |
| `run_meta_analysis.py` | prompts for it | prompts for it | prompts for it | prompts for it |

### Key Findings

1. **Analysis modules are standalone** — `task_dependency_analysis.py` and `error_tracing_analysis.py` implement graph-based analysis with NetworkX but are not integrated into the actual orchestrator (`src/pilotcode/orchestration/`). They serve as design/audit tools.

2. **The real orchestration lives in `src/pilotcode/orchestration/`** — The 8 root-level files are analysis, demo, and test utilities, not the engine itself. See `orchestration_file_map.md` for the full 31-file core orchestration package.

3. **`run_meta_analysis.py` bridges the gap** — It sends a prompt that asks PilotCode to analyze and refactor its own orchestration system, effectively using the LLM to audit the codebase.

4. **`parallel_test.py` informs thread-safety** — Directly relevant to the `ToolOrchestrator` and `DagExecutor` parallelism in the core orchestrator.
