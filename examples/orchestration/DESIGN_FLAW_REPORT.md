# Design Flaw Report — `pilotcode.orchestration`

**Date:** 2025-01-21  
**Scope:** `src/pilotcode/orchestration/` (12 modules, ~3,500 lines) + `examples/orchestration/` (4 demo files)  
**Analysis Sources:** `code_smells.json` (12 smells), `ARCHITECTURAL_COMPLIANCE.md` (6 flaws), `CORE_ABSTRACTIONS.md` (architecture reference)

---

## 1. Analysis Process

The audit was conducted in four stages:

| Stage | Input | Output |
|---|---|---|
| **Code Smell Scan** | 4 example files (auto_decomposition_demo.py, basic_decomposition.py, complex_task_demo.py, real_world_usage.py) | `code_smells.json` — 12 smells across 6 categories |
| **Architecture Review** | 12 source modules against SOLID principles | `ARCHITECTURAL_COMPLIANCE.md` — 6 structural flaws |
| **Severity Triage** | All 18 findings ranked by severity × frequency × testability impact | `top_design_flaws.json` — top 3 with justification |
| **Report Synthesis** | Combined artifacts | This document |

Key metrics from the analysis:

- **Code smells found:** 12 (4 Hardcoded Values, 3 Improper Error Handling, 2 God Functions, 2 Tight Coupling, 1 Duplicate Code, 1 Lack of Abstraction)
- **Architectural flaws found:** 6 (2 Critical, 2 High, 2 Medium)
- **Selection criteria:** How badly the flaw breaks the system (severity), how many files it affects (frequency), and how severely it prevents isolated testing (testability)

---

## 2. Design Flaw #1 — God Class: `MissionAdapter` (SRP Violation)

**Severity:** 🔴 Critical | **File:** `src/pilotcode/orchestration/adapter.py` (922 lines)  
**Root cause of:** Flaws #4, #5, and #6

### Problem

`MissionAdapter` bundles **8 distinct responsibilities** in a single 922-line class:

```python
# adapter.py — 8 responsibilities crammed into one class
class MissionAdapter:
    # (1) LLM Planning (~150 lines)
    async def _plan_mission(self, user_request, exploration=None) -> Mission: ...

    # (2) Codebase Exploration (~60 lines)
    async def _explore_codebase(self, user_request) -> dict: ...

    # (3) Worker Prompt Assembly (~50 lines)
    def _build_worker_prompt(self, task, context) -> str: ...

    # (4) LLM Worker Loop (~130 lines)
    async def _llm_worker(self, task, context) -> ExecutionResult: ...

    # (5) L1 Static Verifier (static method)
    async def _simple_verifier(task, exec_result) -> VerificationResult: ...

    # (6) L2 Test Verifier (static method)
    async def _test_verifier(task, exec_result) -> VerificationResult: ...

    # (7) L3 Code Review Verifier (static method)
    async def _code_review_verifier(task, exec_result) -> VerificationResult: ...

    # (8) Project Memory Updates (~40 lines)
    def _update_memory_from_tool(self, ...) -> None: ...
```

The three verifiers are `@staticmethod` — meaning **no verification level can be tested in isolation** without instantiating the entire adapter. Adding a new verification level (e.g., security scan) requires modifying `MissionAdapter` itself, violating the **Open-Closed Principle**.

### Impact

- **Testability blocked:** Cannot unit-test verifiers, planner, or worker loop independently. Requires a real LLM and full adapter instantiation for any test.
- **Merge conflict risk:** Any change to planning, verification, or worker logic risks collisions in the same file.
- **Onboarding friction:** New team members must understand all 8 concerns before modifying any one.

### Suggested Fix

Extract into focused classes behind protocols, with `MissionAdapter` becoming a thin facade:

```
MissionAdapter (facade, ~50 lines)
  ├── MissionPlanner        — LLM planning
  ├── CodebaseExplorer      — codebase scanning
  ├── LlmWorker            — LLM worker loop
  ├── StaticVerifier       — L1 verification
  ├── TestVerifier         — L2 verification
  └── CodeReviewVerifier   — L3 verification
```

**Effort:** High (3–5 days). Each extraction is straightforward; testing the new boundaries is the bulk of the work.

---

## 3. Design Flaw #2 — Global Mutable Singletons (DIP Violation)

**Severity:** 🔴 Critical | **Files:** `tracker.py`, `smart_coordinator.py`, `auto_config.py`, `orchestrator.py`

### Problem

Three module-level global variables act as "poor man's dependency injection" across four core files:

```python
# tracker.py:322
_tracker: MissionTracker | None = None

def get_tracker(db_path=None) -> MissionTracker:
    global _tracker
    if _tracker is None:
        _tracker = MissionTracker(db_path=db_path)
    return _tracker

def reset_tracker() -> None:
    """Reset global tracker (mainly for testing)."""
    global _tracker
    _tracker = None
```

```python
# smart_coordinator.py:53
_smart_coordinator: SmartCoordinator | None = None

def get_smart_coordinator(config=None) -> SmartCoordinator:
    global _smart_coordinator
    if _smart_coordinator is None:
        _smart_coordinator = SmartCoordinator(config=config)
    return _smart_coordinator
```

```python
# auto_config.py:35
_auto_config = AutoDecompositionConfig()  # module-level instantiation

def get_auto_config() -> AutoDecompositionConfig:
    return _auto_config

def enable_auto_decomposition():
    global _auto_config
    _auto_config.enabled = True
```

The anti-pattern infects `Orchestrator` via internal singleton fetch:

```python
# orchestrator.py:74
def __init__(self, config=None):
    self.config = config or OrchestratorConfig()
    self.tracker = get_tracker(db_path=self.config.db_path)  # not constructor injection!
```

### Impact

- **Parallel tests break:** `reset_tracker()` exists _precisely because_ the authors know the singleton breaks tests — it is a workaround for a design flaw. CI pipelines with `pytest-xdist` will experience flaky, non-reproducible failures.
- **Hidden coupling:** Any module can call `get_tracker()` without the dependency appearing in the constructor signature. Refactoring tracker internals requires auditing all call sites.
- **Pattern contagion:** New developers see `reset_tracker()` as a legitimate pattern rather than a code smell.

### Suggested Fix

Constructor injection throughout:

```python
# Before
class Orchestrator:
    def __init__(self, config=None):
        self.tracker = get_tracker(db_path=self.config.db_path)

# After
class Orchestrator:
    def __init__(self, config=None, tracker: MissionTracker):
        self.tracker = tracker
```

Remove `get_tracker()`, `get_smart_coordinator()`, `reset_tracker()`, and the module-level `_auto_config`. Let the application entry point create and wire instances.

**Effort:** Medium (1–2 days). Mechanical refactor — find all call sites, replace with injected parameters.

---

## 4. Design Flaw #3 — Concrete Infrastructure Dependencies (DIP Violation)

**Severity:** 🟠 High | **File:** `src/pilotcode/orchestration/adapter.py`

### Problem

`MissionAdapter` imports concrete infrastructure directly at the module level rather than accepting dependencies via constructor injection:

```python
# adapter.py:15-22 — concrete imports at module level
from pilotcode.utils.model_client import get_model_client, Message
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_all_tools
from pilotcode.permissions.permission_manager import (
    get_permission_manager,
    PermissionLevel,
    PermissionRequest,
)
```

These are consumed inside the three most critical methods:

| Method | Concrete dependencies used |
|---|---|
| `_llm_worker` | `get_model_client`, `QueryEngine`, `get_all_tools` |
| `_plan_mission` | `get_model_client` |
| `_code_review_verifier` | `get_model_client`, `get_permission_manager` |

Writing a unit test for `_plan_mission` requires either:
- A **real LLM** (slow, costly, non-deterministic), or
- `unittest.mock.patch` across **5+ module paths** (fragile, breaks on any import refactor)

This is a direct **Dependency Inversion Principle** violation: high-level policy (mission planning) depends on low-level infrastructure (concrete LLM client, concrete tool registry), not on abstractions.

### Impact

- **Testability blocked:** Cannot write fast, deterministic unit tests for the planner or worker.
- **Vendor lock-in:** Swapping the LLM provider, tool registry, or permission system requires editing `MissionAdapter` internals rather than passing a different implementation at construction time.
- **Downstream of Flaw #1:** Because `MissionAdapter` is already a god class, the concrete imports are buried inside methods. Fixing #1 naturally fixes #4.

### Suggested Fix

Accept dependencies as constructor arguments typed to protocols/ABCs:

```python
# Before
class MissionAdapter:
    def __init__(self, ...):  # no infrastructure params
        ...

# After
class MissionAdapter:
    def __init__(
        self,
        model_client: ModelClientProtocol,       # injected
        tool_registry: ToolRegistryProtocol,      # injected
        permission_manager: PermissionProtocol,   # injected
        ...
    ):
        self._model_client = model_client
        self._tool_registry = tool_registry
        self._permission_manager = permission_manager
```

Define lightweight protocols:

```python
class ModelClientProtocol(Protocol):
    async def chat_completion(self, messages, temperature, stream) -> AsyncIterator[dict]: ...

class ToolRegistryProtocol(Protocol):
    def get_all_tools(self) -> list[ToolSpec]: ...
```

**Effort:** Medium (1–2 days). This is naturally addressed when decomposing `MissionAdapter` (Flaw #1).

---

## 5. Recommended Fix Order

Fixes are sequenced so each step unblocks the next:

```
Step 1 ──► Extract MissionAdapter into focused classes  (Fixes #1)
  │         Introduce constructor-injected dependencies  (Fixes #4)
  │
  ▼
Step 2 ──► Replace global singletons with constructor
  │         injection throughout the system              (Fixes #2)
  │
  ▼
Step 3 ──► Cleanup tasks (low effort, now unblocked):
             • Extract shared worker-type selector       (ARCH-F3, 2-4 hrs)
             • Decompose Orchestrator SRP                (ARCH-F5, 1-2 days)
             • Replace magic int verifier keys with enum (ARCH-F6, 2-4 hrs)
             • Create shared example mock module         (SMELL-003, 1 hr)
```

**Total estimated effort:** 6–10 days across all steps.

---

## 6. What's Done Well

The codebase has strong foundations that should be preserved:

| Module | Strength |
|---|---|
| `state_machine.py` | Explicit dictionary-based transition table, clean and testable |
| `context_strategy.py` | `ContextStrategySelector` + frozen `StrategyConfig` dataclasses — textbook strategy pattern |
| `dag.py` | Correct Kahn's algorithm with cycle detection and wave grouping; single responsibility |
| `task_spec.py`, `project_memory.py` | Clean dataclasses with `to_dict`/`from_dict` serialization |

These modules already demonstrate the target architecture — small, focused, protocol-driven, independently testable. The flawed modules should be refactored toward this same standard.

---

## 7. Other Notable Issues (Not Top 3)

| ID | Issue | Severity | Why Not Top 3 |
|---|---|---|---|
| ARCH-F3 | Duplicate worker-type selection (`orchestrator.py:323` vs `context_strategy.py:347`) | 🟠 High | Independently testable; fix is low-effort (2-4 hrs) once #1 resolves |
| ARCH-F5 | `Orchestrator` mixes scheduling, verification, retry in 720 lines | 🟡 Medium | Becomes straightforward to fix once #1 and #2 are addressed |
| ARCH-F6 | Magic integer verifier keys (1, 2, 3) violate OCP | 🟡 Medium | Adding a security scan requires touching 4 files; low-effort fix |
| SMELL-003 | Duplicate `MockAgent` in two example files | 🟠 High | Confined to demo files, not core orchestration logic |

---

*Report generated from analysis artifacts: `code_smells.json`, `ARCHITECTURAL_COMPLIANCE.md`, `top_design_flaws.json`*
