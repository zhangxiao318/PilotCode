"""Tests for quest command."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from pilotcode.commands.quest_cmd import (
    quest_command,
    _resolve_qid,
    _generate_summary,
    _fallback_missions,
    _format_quest_status,
    QuestState,
    QuestPhase,
    _quests,
    _next_quest_id,
)
from pilotcode.commands.base import CommandContext


@pytest.fixture(autouse=True)
def clean_quests():
    """Clear global quest store before each test."""
    global _quests, _next_quest_id
    _quests.clear()
    _next_quest_id = 1
    yield
    _quests.clear()
    _next_quest_id = 1


@pytest.fixture
def context(tmp_path):
    """Create a command context."""
    return CommandContext(cwd=str(tmp_path))


# =============================================================================
# Command routing tests
# =============================================================================


class TestQuestCommandRouting:
    """Tests for /quest command routing."""

    @pytest.mark.asyncio
    async def test_no_args_shows_help(self, context):
        """Test /quest with no args shows help when no quests exist."""
        result = await quest_command([], context)
        assert "No active quests" in result
        assert "/quest" in result

    @pytest.mark.asyncio
    async def test_no_args_lists_quests(self, context):
        """Test /quest with no args lists active quests."""
        q = QuestState(id=1, description="Test quest", status="running")
        _quests[1] = q
        result = await quest_command([], context)
        assert "Test quest" in result
        assert "running" in result

    @pytest.mark.asyncio
    async def test_start_new_quest(self, context):
        """Test /quest "<description>" starts a new quest."""
        with patch("pilotcode.commands.quest_cmd._run_quest") as mock_run:
            result = await quest_command(["implement", "auth"], context)
            assert "Quest #1 started" in result
            assert "implement auth" in result
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_shows_details(self, context):
        """Test /quest status shows quest details."""
        q = QuestState(id=1, description="Test", status="running")
        q.phases = [QuestPhase(name="P1", status="done", result="ok")]
        _quests[1] = q
        result = await quest_command(["status"], context)
        assert "Quest #1" in result
        assert "P1" in result
        assert "ok" in result

    @pytest.mark.asyncio
    async def test_status_unknown_quest(self, context):
        """Test /quest status with non-existent ID."""
        result = await quest_command(["status", "99"], context)
        assert "No quest found" in result

    @pytest.mark.asyncio
    async def test_pause_running_quest(self, context):
        """Test /quest pause pauses a running quest."""
        q = QuestState(id=1, description="Test", status="running")
        _quests[1] = q
        result = await quest_command(["pause"], context)
        assert "paused" in result
        assert q.status == "paused"

    @pytest.mark.asyncio
    async def test_pause_not_running(self, context):
        """Test /quest pause on non-running quest."""
        q = QuestState(id=1, description="Test", status="completed")
        _quests[1] = q
        result = await quest_command(["pause"], context)
        assert "not running" in result

    @pytest.mark.asyncio
    async def test_resume_paused_quest(self, context):
        """Test /quest resume resumes a paused quest."""
        q = QuestState(id=1, description="Test", status="paused")
        _quests[1] = q
        with patch("pilotcode.commands.quest_cmd._run_quest") as mock_run:
            result = await quest_command(["resume"], context)
            assert "resuming" in result
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_not_paused(self, context):
        """Test /quest resume on non-paused quest."""
        q = QuestState(id=1, description="Test", status="running")
        _quests[1] = q
        result = await quest_command(["resume"], context)
        assert "not paused" in result

    @pytest.mark.asyncio
    async def test_cancel_quest(self, context):
        """Test /quest cancel removes quest."""
        q = QuestState(id=1, description="Test", status="running")
        _quests[1] = q
        result = await quest_command(["cancel"], context)
        assert "cancelled" in result
        assert 1 not in _quests


# =============================================================================
# Resolve ID tests
# =============================================================================


class TestResolveQid:
    """Tests for _resolve_qid."""

    def test_explicit_id(self):
        """Test explicit ID from args."""
        assert _resolve_qid(["status", "#3"]) == 3
        assert _resolve_qid(["status", "5"]) == 5

    def test_explicit_id_invalid(self):
        """Test invalid explicit ID."""
        assert _resolve_qid(["status", "abc"]) is None

    def test_fallback_to_running(self):
        """Test fallback to most recent running/paused quest."""
        _quests[1] = QuestState(id=1, description="Old", status="completed")
        _quests[2] = QuestState(id=2, description="Running", status="running")
        assert _resolve_qid(["status"]) == 2

    def test_fallback_to_recent(self):
        """Test fallback to most recent quest when none running."""
        _quests[1] = QuestState(id=1, description="Old", status="completed")
        _quests[3] = QuestState(id=3, description="New", status="completed")
        assert _resolve_qid(["status"]) == 3

    def test_no_quests(self):
        """Test no quests returns None."""
        assert _resolve_qid(["status"]) is None


# =============================================================================
# Summary generation tests
# =============================================================================


class TestGenerateSummary:
    """Tests for _generate_summary."""

    def test_all_success(self):
        """Test summary when all missions succeed."""
        missions = [
            {"title": "M1", "description": "d1"},
            {"title": "M2", "description": "d2"},
        ]
        results = [{"success": True}, {"success": True}]
        summary = _generate_summary("Test quest", missions, results)
        assert "2/2 missions succeeded" in summary
        assert "M1" in summary
        assert "M2" in summary
        assert "All missions completed successfully" in summary

    def test_partial_failure(self):
        """Test summary with partial failures."""
        missions = [
            {"title": "M1", "description": "d1"},
            {"title": "M2", "description": "d2"},
        ]
        results = [{"success": True}, {"success": False, "error": "bug"}]
        summary = _generate_summary("Test quest", missions, results)
        assert "1/2 missions succeeded" in summary
        assert "1 mission(s) failed" in summary
        assert "bug" in summary

    def test_all_failure(self):
        """Test summary when all missions fail."""
        missions = [{"title": "M1"}]
        results = [{"success": False, "error": "crash"}]
        summary = _generate_summary("Test quest", missions, results)
        assert "0/1 missions succeeded" in summary
        assert "All missions failed" in summary

    def test_empty(self):
        """Test summary with no missions."""
        summary = _generate_summary("Test quest", [], [])
        assert "0/0 missions succeeded" in summary


# =============================================================================
# Fallback missions tests
# =============================================================================


class TestFallbackMissions:
    """Tests for _fallback_missions."""

    def test_returns_single_mission(self):
        """Test fallback creates a single mission."""
        missions = _fallback_missions("do something")
        assert len(missions) == 1
        assert missions[0]["title"] == "do something"
        assert missions[0]["type"] == "code"

    def test_truncates_long_description(self):
        """Test fallback truncates long title."""
        long_desc = "a" * 100
        missions = _fallback_missions(long_desc)
        assert missions[0]["title"] == long_desc[:30]


# =============================================================================
# Integration: _run_quest resumability
# =============================================================================


class TestRunQuestResumability:
    """Tests that _run_quest can resume from any phase."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_phases(self, context):
        """Test that resuming skips already-done phases."""
        from pilotcode.commands.quest_cmd import _run_quest

        q = QuestState(id=1, description="Test", status="paused")
        # Phase 1 already done
        q.phases = [
            QuestPhase(name="需求解析", status="done", missions=[{"title": "M1"}]),
            QuestPhase(name="Mission 执行", status="pending"),
        ]
        _quests[1] = q

        with patch(
            "pilotcode.commands.quest_cmd._execute_mission", new_callable=AsyncMock
        ) as mock_exec:
            mock_exec.return_value = {"success": True}
            await _run_quest(q, context)

        assert q.status == "completed"
        # Phase 1 should not be re-executed
        assert q.phases[0].status == "done"
        # Phase 2 should have executed
        assert q.phases[1].status == "done"
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_during_mission_execution(self, context):
        """Test pausing during mission execution stops cleanly."""
        from pilotcode.commands.quest_cmd import _run_quest

        q = QuestState(id=1, description="Test", status="running")
        q.phases = [
            QuestPhase(name="需求解析", status="done", missions=[{"title": "M1"}, {"title": "M2"}]),
            QuestPhase(name="Mission 执行", status="running"),
        ]
        _quests[1] = q

        call_count = 0

        async def mock_exec(mission, ctx, quest_state):
            nonlocal call_count
            call_count += 1
            # Simulate pause after first mission
            if call_count == 1:
                quest_state.status = "paused"
            return {"success": True}

        with patch("pilotcode.commands.quest_cmd._execute_mission", side_effect=mock_exec):
            await _run_quest(q, context)

        assert q.status == "paused"
        assert call_count == 1  # Only first mission ran
        assert len(q.phases[1].missions) == 1


# =============================================================================
# Quest state formatting tests
# =============================================================================


class TestQuestStatusFormat:
    """Tests for _format_quest_status."""

    def test_basic_format(self):
        """Test basic status formatting."""
        q = QuestState(id=1, description="Test quest", status="running")
        q.phases = [QuestPhase(name="Phase 1", status="done", result="ok")]
        text = _format_quest_status(q)
        assert "Quest #1" in text
        assert "Test quest" in text
        assert "Phase 1" in text
        assert "ok" in text

    def test_with_missions(self):
        """Test status with mission list."""
        q = QuestState(id=1, description="Test", status="running")
        q.phases = [
            QuestPhase(name="P1", status="done", missions=[{"title": "M1", "success": True}]),
        ]
        text = _format_quest_status(q)
        assert "M1" in text
        assert "✓" in text

    def test_truncates_many_missions(self):
        """Test status truncates when > 5 missions."""
        q = QuestState(id=1, description="Test", status="running")
        missions = [{"title": f"M{i}", "success": True} for i in range(10)]
        q.phases = [QuestPhase(name="P1", status="done", missions=missions)]
        text = _format_quest_status(q)
        assert "... and 5 more" in text
