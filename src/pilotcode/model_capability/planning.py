"""Planning dimension benchmarks (medium-hard)."""

from __future__ import annotations

from typing import Any

from pilotcode.utils.model_client import Message

from .base import BenchmarkResult, _call_llm, _extract_json, _score_bool


def _validate_plan_dag(data: dict) -> tuple[bool, dict]:
    """Validate a JSON plan: unique IDs, valid deps, no cycles, topo sortable."""
    meta: dict[str, Any] = {"errors": []}
    if not isinstance(data, dict) or "phases" not in data:
        meta["errors"].append("missing 'phases' key")
        return False, meta

    all_tasks: dict[str, dict] = {}
    for phase in data.get("phases", []):
        for task in phase.get("tasks", []):
            tid = task.get("task_id", "")
            if not tid:
                continue
            if tid in all_tasks:
                meta["errors"].append(f"duplicate task_id: {tid}")
            all_tasks[tid] = task

    meta["task_count"] = len(all_tasks)
    if len(all_tasks) < 5:
        meta["errors"].append("insufficient tasks (<5)")

    dep_map: dict[str, set[str]] = {tid: set() for tid in all_tasks}
    for tid, task in all_tasks.items():
        for dep in task.get("dependencies", []):
            if dep not in all_tasks:
                meta["errors"].append(f"missing dependency: {dep}")
            else:
                dep_map[tid].add(dep)

    in_degree = {tid: 0 for tid in all_tasks}
    for tid, deps in dep_map.items():
        for dep in deps:
            in_degree[tid] = in_degree.get(tid, 0) + 1

    queue = [tid for tid, d in in_degree.items() if d == 0]
    topo: list[str] = []
    while queue:
        node = queue.pop(0)
        topo.append(node)
        for tid, deps in dep_map.items():
            if node in deps:
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    queue.append(tid)

    has_cycle = len(topo) != len(all_tasks)
    if has_cycle:
        meta["errors"].append("cycle detected in dependency graph")

    return len(meta["errors"]) == 0 and not has_cycle, meta


PLANNING_TEST_PROMPT = """You are a senior architect. Design an implementation plan for the following system.

System: "Build an e-commerce platform with these microservices:
- User Service (auth, profiles, addresses)
- Product Catalog Service (search, categories, inventory tracking)
- Order Service (cart, checkout, order history)
- Payment Service ( Stripe integration, refunds, invoicing)
- Notification Service (email, SMS, push)

Critical constraints:
1. Order Service depends on User Service and Product Catalog Service.
2. Payment Service depends on Order Service.
3. Notification Service depends on Order Service and Payment Service.
4. Product Catalog Service depends on User Service (for personalized inventory).
5. No service may be deployed before all of its dependencies are deployed.

Output a single valid JSON object (no markdown, no explanations outside JSON) with this exact structure:
{
  "phases": [
    {
      "phase_id": "phase_1",
      "title": "Phase title",
      "tasks": [
        {
          "task_id": "task_1",
          "title": "Task title",
          "objective": "What to do",
          "dependencies": []
        }
      ]
    }
  ]
}

Rules:
- Use snake_case for all IDs.
- Every service must have at least one deployment task.
- Dependencies must reference existing task_ids only.
- The dependency graph must be acyclic (DAG).
- Include at least 8 tasks total across all phases.
"""


async def test_planning_json_validity() -> BenchmarkResult:
    """Test complex DAG planning with full validation."""
    raw = await _call_llm(
        [Message(role="user", content=PLANNING_TEST_PROMPT)],
        temperature=0.3,
    )
    data = _extract_json(raw)
    is_valid, meta = _validate_plan_dag(data)
    return BenchmarkResult(
        test_name="planning_json_validity",
        dimension="planning",
        sub_dimension="dag_correctness",
        score=_score_bool(is_valid),
        raw_output=raw[:600],
        metadata=meta,
    )


async def test_planning_dependency_accuracy() -> BenchmarkResult:
    """Test CI/CD pipeline with parallel stages and cross-stage deps."""
    prompt = """Design a CI/CD pipeline plan for a microservice project with these stages:

Stages and constraints:
1. lint — code style check (no deps)
2. security_scan — vulnerability scanning (no deps)
3. unit_test — run unit tests (depends on lint AND security_scan)
4. build_container — build Docker image (depends on unit_test)
5. integration_test — run integration tests (depends on build_container)
6. deploy_staging — deploy to staging (depends on integration_test)
7. deploy_prod — deploy to production (depends on deploy_staging)

Additional rule: lint and security_scan can run in parallel, but both must finish before unit_test.

Output a single valid JSON object (no markdown, no extra text) with this structure:
{
  "phases": [
    {
      "phase_id": "phase_1",
      "title": "...",
      "tasks": [
        {"task_id": "task_1", "title": "...", "objective": "...", "dependencies": []}
      ]
    }
  ]
}

Critical requirements:
- The dependency graph must be acyclic.
- All dependencies must reference existing task_ids.
- lint and security_scan must have NO dependencies on each other (parallel).
- deploy_prod must transitively depend on lint and security_scan.
- Include exactly 7 tasks (one per stage).
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.3,
    )
    data = _extract_json(raw)
    is_valid, meta = _validate_plan_dag(data)

    if is_valid and isinstance(data, dict):
        all_tasks: dict[str, dict] = {}
        for phase in data.get("phases", []):
            for task in phase.get("tasks", []):
                tid = task.get("task_id", "")
                if tid:
                    all_tasks[tid] = task

        lint_task = None
        sec_task = None
        deploy_prod_task = None
        for tid, task in all_tasks.items():
            title = task.get("title", "").lower()
            if "lint" in title:
                lint_task = task
            if "security" in title or "scan" in title:
                sec_task = task
            if "deploy" in title and "prod" in title:
                deploy_prod_task = task

        parallel_ok = True
        if lint_task and sec_task:
            lint_deps = set(lint_task.get("dependencies", []))
            sec_deps = set(sec_task.get("dependencies", []))
            lint_id = next((k for k, v in all_tasks.items() if v is lint_task), "")
            sec_id = next((k for k, v in all_tasks.items() if v is sec_task), "")
            if lint_id in sec_deps or sec_id in lint_deps:
                parallel_ok = False
                meta["errors"].append("lint and security_scan depend on each other")

        transitive_ok = True
        if deploy_prod_task:
            visited = set()
            queue = list(deploy_prod_task.get("dependencies", []))
            while queue:
                dep = queue.pop(0)
                if dep in visited:
                    continue
                visited.add(dep)
                if dep in all_tasks:
                    queue.extend(all_tasks[dep].get("dependencies", []))

            lint_id = next((k for k, v in all_tasks.items() if v is lint_task), "")
            sec_id = next((k for k, v in all_tasks.items() if v is sec_task), "")
            if lint_id and lint_id not in visited:
                transitive_ok = False
                meta["errors"].append("deploy_prod does not transitively depend on lint")
            if sec_id and sec_id not in visited:
                transitive_ok = False
                meta["errors"].append("deploy_prod does not transitively depend on security_scan")

        is_valid = is_valid and parallel_ok and transitive_ok

    score = 1.0 if is_valid else 0.5 if len(meta.get("errors", [])) <= 1 else 0.0
    return BenchmarkResult(
        test_name="planning_dependency_accuracy",
        dimension="planning",
        sub_dimension="dependency_accuracy",
        score=score,
        raw_output=raw[:600],
        metadata=meta,
    )


async def test_planning_granularity() -> BenchmarkResult:
    """Test granularity with stricter bounds."""
    prompt = """You are a principal engineer. Plan the migration of a monolithic Python Django app to a Kubernetes-based microservices architecture.

The app has these components:
- User authentication (OAuth2, JWT sessions)
- Product catalog (PostgreSQL, Elasticsearch for search)
- Shopping cart (Redis for session storage)
- Order processing (Celery task queue, RabbitMQ)
- Payment gateway (Stripe webhooks, idempotency keys)
- Admin dashboard (React frontend, GraphQL API)

Output a single valid JSON object with this structure:
{"phases": [{"phase_id": "...", "title": "...", "tasks": [{"task_id": "...", "title": "...", "objective": "...", "dependencies": []}]}]}

Guidelines:
- Each task should be a SINGLE deployable unit or migration step.
- Tasks should not be too vague ("implement everything") nor too detailed ("write line 42 of file X").
- Aim for 8-15 tasks total.
- Include dependency relationships where one task must finish before another starts.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.3,
    )
    data = _extract_json(raw)
    if not data:
        return BenchmarkResult(
            test_name="planning_granularity",
            dimension="planning",
            sub_dimension="task_granularity_appropriateness",
            score=0.0,
            raw_output=raw[:500],
            error="No valid JSON",
        )

    task_count = sum(len(p.get("tasks", [])) for p in data.get("phases", []))
    if 8 <= task_count <= 15:
        score = 1.0
    elif 5 <= task_count <= 20:
        score = 0.7
    elif 3 <= task_count <= 30:
        score = 0.4
    else:
        score = 0.0

    return BenchmarkResult(
        test_name="planning_granularity",
        dimension="planning",
        sub_dimension="task_granularity_appropriateness",
        score=score,
        raw_output=raw[:500],
        metadata={"task_count": task_count},
    )
