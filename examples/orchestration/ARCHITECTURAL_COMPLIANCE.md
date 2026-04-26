# Architectural Compliance Report

**Target:** `src/pilotcode/orchestration/` (12 modules, ~3500 lines)
**Standard:** SOLID principles, separation of concerns, plugin architecture
**Date:** 2025-01-21

---

## Summary

The orchestration system has a well-documented conceptual architecture (see
CORE_ABSTRACTIONS.md) with clearly named P-EVR phases, DAG execution, and
context-aware strategy selection. However, the _implementation_ deviates in
ways that will hamper maintainability. Six structural flaws follow.

---

## Flaw 1 — God Class: `MissionAdapter` (SRP Violation)

**Severity:** 🔴 Critical | **File:** `adapter.py` (919 lines)

`MissionAdapter` owns **eight distinct responsibilities** in one class:
LLM planning (`_plan_mission`, ~150 lines), codebase exploration
(`_explore_codebase`, ~60), worker prompt assembly (`_build_worker_prompt`,
~50), LLM worker loop (`_llm_worker`, ~130), L1/L2/L3 verifiers (three
static methods totalling ~130), project memory updates
(`_update_memory_from_tool`, ~40), plus permission setup. The verifiers are
**static methods** on the adapter — not independent pluggable classes. You
cannot add a verification level without modifying `MissionAdapter`, nor test
verifiers in isolation.

**Remediation:** Extract into `MissionPlanner`, `CodebaseExplorer`, `LlmWorker`,
`StaticVerifier`, `TestVerifier`, `CodeReviewVerifier` — each behind a
protocol, with `MissionAdapter` becoming a thin facade.

---

## Flaw 2 — Global Mutable Singletons (DIP Violation)

**Severity:** 🔴 Critical | **Files:** `tracker.py:297`, `smart_coordinator.py:53`,
`auto_config.py:37`

Three module-level globals serve as "poor man's DI":

```python
_tracker: MissionTracker | None = None       # tracker.py
_smart_coordinator: SmartCoordinator | None = None  # smart_coordinator.py
_auto_config = AutoDecompositionConfig()     # auto_config.py — module-level
```

`Orchestrator.__init__` calls `get_tracker()` internally rather than
accepting it via constructor injection. The `reset_tracker()` helper exists
_precisely because_ the authors know the singleton breaks tests — the test
helper is a workaround for a design flaw. Parallel tests share mutable state.

**Remediation:** Constructor injection throughout. Remove `get_tracker()`,
`get_smart_coordinator()`, and the module-level `_auto_config`. Let the
application entry point create and wire instances.

---

## Flaw 3 — Duplicate Worker-Type Selection Logic (DRY Violation)

**Severity:** 🟠 High | **Files:** `orchestrator.py:370`, `context_strategy.py:336`

The `ComplexityLevel` → worker type mapping is implemented twice:

```python
# orchestrator.py: if VERY_SIMPLE -> "simple", SIMPLE|MODERATE -> "standard", else -> "complex"
# context_strategy.py: identical mapping, PLUS auto_worker_selection config gating
```

The `MissionPlanAdjuster` version respects `auto_worker_selection`; the
`Orchestrator` version does not. A new worker type requires updating both —
inevitably one will be missed, producing divergent behavior.

**Remediation:** Extract a single `select_worker_type(complexity, *,
auto_select=True) -> str` used by both call sites.

---

## Flaw 4 — Concrete Dependencies in `MissionAdapter` (DIP Violation)

**Severity:** 🟠 High | **File:** `adapter.py:18-34`

`MissionAdapter` imports concrete infrastructure directly rather than
accepting it as constructor arguments:

```python
from pilotcode.utils.model_client import get_model_client
from pilotcode.query_engine import QueryEngine, QueryEngineConfig
from pilotcode.tools.registry import get_all_tools
from pilotcode.permissions.permission_manager import get_permission_manager
```

These are called inside `_llm_worker`, `_plan_mission`, and
`_code_review_verifier`. Writing a unit test for `_plan_mission` requires
either a real LLM (slow, costly) or `unittest.mock.patch` across five
module paths (fragile, breaks on refactor).

**Remediation:** Accept `model_client`, `tool_registry`, and
`permission_manager` as constructor arguments. Depend on protocols/ABCs,
not concrete module singletons.

---

## Flaw 5 — `Orchestrator` Mixes Scheduling, Verification, and Retry (SRP)

**Severity:** 🟡 Medium | **File:** `orchestrator.py` (720 lines)

`Orchestrator` combines DAG scheduling (main loop + `asyncio.Semaphore`),
cascade failure detection (`_has_failed_dependency`, `_cancel_downstream_tasks`),
smart retry (`_smart_retry`, `_analyze_failure`, `_adjust_task_for_retry`),
verification pipeline (`_verify_task`, `_run_verifier`,
`_handle_verification_failure`), and worker dispatch. The failure analysis
method is a hand-written `if/elif` chain doing keyword matching (`"file not
found"`, `"permission"`, `"syntax"`) — a brittle classifier.

**Remediation:** Extract `VerificationPipeline`, `RetryPolicy`, and
`CascadeFailureHandler` as separate classes.

---

## Flaw 6 — Verifier Registry Uses Magic Integer Keys (OCP Violation)

**Severity:** 🟡 Medium | **Files:** `orchestrator.py:83`, `adapter.py:86`

Verifiers are registered with plain `int` keys and consumed via hardcoded
checks:

```python
self._verifier_registry: dict[int, Callable[...]] = {}
self._orchestrator.register_verifier(1, self._simple_verifier)
self._orchestrator.register_verifier(2, self._test_verifier)
self._orchestrator.register_verifier(3, self._code_review_verifier)
# consumed as:
if self.config.enable_l1_verification:
    l1 = await self._run_verifier(1, ...)
```

Adding a "security scan" level requires touching `OrchestratorConfig` (new
boolean), `StrategyConfig` (new boolean), `_verify_task` (new if-block),
AND `MissionAdapter` (new registration). The `auto_approve_simple` logic
also bypasses the registry entirely for VERY_SIMPLE tasks.

**Remediation:** `VerificationLevel` enum + `VerificationPipeline` iterating
registered verifiers in priority order, configurable per strategy.

---

## What's Done Well

- **State machine** (`state_machine.py`) — explicit dictionary-based transition
  table, clean and testable.
- **Strategy pattern** (`context_strategy.py`) — `ContextStrategySelector` +
  frozen `StrategyConfig` dataclasses; textbook strategy pattern.
- **DAG executor** (`dag.py`) — correct Kahn's algorithm with cycle detection
  and wave grouping; single responsibility.
- **Data models** (`task_spec.py`, `project_memory.py`) — clean dataclasses
  with `to_dict`/`from_dict` serialization.

---

## Risk Matrix

| Flaw | Impact | Fix Effort |
|---|---|---|
| F1: God Class `MissionAdapter` | Merge conflicts, slow onboarding | High (3–5 days) |
| F2: Global Singletons | Flaky parallel tests, hidden coupling | Medium (1–2 days) |
| F3: Duplicate worker selection | Subtle bugs from divergent logic | Low (2–4 hours) |
| F4: Concrete dependencies | Cannot unit test critical paths | Medium (1–2 days) |
| F5: Orchestrator SRP | Risky changes to scheduling/retry | Medium (1–2 days) |
| F6: Magic int verifier keys | Cannot extend verification cleanly | Low (2–4 hours) |

---

## Recommendation

Address F1 and F2 first — they are root causes behind F4, F5, and F6. Once
`MissionAdapter` is decomposed and singletons are replaced with dependency
injection, the remaining flaws become straightforward to fix.
