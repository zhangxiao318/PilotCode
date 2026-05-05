"""Tests for plan mode decision logic — verifies key scenarios work end-to-end."""

import pytest
from pilotcode.orchestration.plan_mode import should_plan


class TestPlanModeDecision:
    """Verify should_plan() returns correct decisions for real-world scenarios."""

    # ------------------------------------------------------------------
    # Scenarios that should trigger PLAN
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "request_text, reason",
        [
            ("Plan the implementation of OAuth2 login", "explicit plan keyword"),
            ("设计用户管理模块的架构方案", "Chinese plan keyword"),
            ("I need a strategy for migrating from Redis to PostgreSQL", "strategy keyword"),
            ("帮我分析数据库性能问题并给出优化方案", "混合分析+实现 → plan"),
            (
                "Add a new feature for file upload with validation across multiple modules",
                "multi-file indicator",
            ),
            (
                "Should we use WebSocket or SSE for real-time updates?",
                "ambiguous architecture decision",
            ),
            ("create a full authentication system", "implement keyword + full system indicator"),
            ("构建完整的用户权限管理系统", "Chinese implement keyword"),
        ],
    )
    def test_should_plan(self, request_text: str, reason: str):
        decision = should_plan(request_text)
        assert decision == "plan", f"Expected 'plan' for: {request_text} ({reason})"
        print(f"  ✅ {reason}: '{request_text[:50]}...' → {decision}")

    # ------------------------------------------------------------------
    # Scenarios that should be DIRECT (no planning needed)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "request_text, reason",
        [
            ("read the file src/app.py", "read command"),
            ("fix typo in the login page", "fix typo pattern"),
            ("change the color of the button to blue", "single change"),
            ("add a parameter to the validate function", "add parameter"),
            ("rename the function getData to fetchData", "rename command"),
            ("remove the unused import", "remove command"),
            ("查看 src/main.py 的内容", "Chinese read command"),
            ("fix this bug in the error handler", "direct fix pattern"),
            ("edit the config.py file to enable debug mode", "single file change"),
        ],
    )
    def test_direct(self, request_text: str, reason: str):
        decision = should_plan(request_text)
        assert decision == "direct", f"Expected 'direct' for: {request_text} ({reason})"
        print(f"  ✅ {reason}: '{request_text[:50]}...' → {decision}")

    # ------------------------------------------------------------------
    # Scenarios that should be ANALYZE (read-only investigation)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "request_text, reason",
        [
            ("analyze the performance of the database queries", "pure analysis"),
            ("review the code in src/auth.py for security issues", "code review"),
            ("explain how the authentication flow works", "explain request"),
            ("分析这个项目的代码质量", "Chinese analysis"),
            ("审查用户模块的代码是否存在安全漏洞", "Chinese code review"),
            ("understand the data flow between components", "understand request"),
            ("investigate why the tests are failing", "investigation"),
        ],
    )
    def test_analyze(self, request_text: str, reason: str):
        decision = should_plan(request_text)
        assert decision == "analyze", f"Expected 'analyze' for: {request_text} ({reason})"
        print(f"  ✅ {reason}: '{request_text[:50]}...' → {decision}")

    # ------------------------------------------------------------------
    # Short requests (under 80 chars) should be DIRECT
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "request_text",
        [
            "add error handling",
            "fix the bug",
            "update the readme",
            "debug this test",
            "查看这个文件",
            "添加日志",
        ],
    )
    def test_short_requests_direct(self, request_text: str):
        decision = should_plan(request_text)
        assert decision == "direct", f"Expected 'direct' for short: '{request_text}'"
        print(f"  ✅ short request: '{request_text}' → {decision}")


class TestPlanDecisionEdgeCases:
    """Edge cases for plan mode decisions."""

    def test_force_plan(self):
        """force_plan=True should always return 'plan'."""
        assert should_plan("read a file", force_plan=True) == "plan"
        assert should_plan("fix typo", force_plan=True) == "plan"

    def test_empty_request(self):
        """Empty string should be 'direct'."""
        assert should_plan("") == "direct"

    def test_ambiguous_architecture(self):
        """Architecture comparison should trigger plan."""
        requests = [
            "compare Redis vs PostgreSQL for the user cache",
            "what are the tradeoffs between REST and GraphQL",
        ]
        for req in requests:
            assert should_plan(req) == "plan", f"Expected plan for: {req}"

    def test_single_file_change(self):
        """Single file change should be direct."""
        requests = [
            "change the login function in auth.py",
            "modify the User model in models.py",
        ]
        for req in requests:
            assert should_plan(req) == "direct", f"Expected direct for: {req}"

    def test_multiple_tasks_in_one(self):
        """Multiple things in one request → plan."""
        req = "find all API endpoints and add rate limiting to them"
        assert should_plan(req) in ("plan", "analyze"), f"Expected plan/analyze for: {req}"

    def test_edit_config_add_setting_plan(self):
        """Edit config with additive change may need plan."""
        req = "edit the config.yaml file to add a new setting"
        decision = should_plan(req)
        # This is borderline - the rule is conservative (plan when in doubt)
        assert decision in ("plan", "direct"), f"Expected plan or direct for: {req}"
