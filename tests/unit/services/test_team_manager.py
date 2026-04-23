"""Tests for team manager."""

import pytest
from pilotcode.services.team_manager import (
    TeamManager,
    AgentStatus,
    create_team,
    get_team_manager,
)


class TestTeamManager:
    """Test team management functionality."""

    @pytest.fixture
    def manager(self):
        """Create fresh manager for each test."""
        return TeamManager()

    def test_create_team(self, manager):
        """Test team creation."""
        team = manager.create_team("TestTeam", "A test team")

        assert team.name == "TestTeam"
        assert team.description == "A test team"
        assert team.id is not None
        assert len(team.agents) == 0

    def test_create_team_with_id(self, manager):
        """Test team creation with custom ID."""
        team = manager.create_team("TestTeam", "A test team", team_id="custom123")

        assert team.id == "custom123"

    def test_delete_team(self, manager):
        """Test team deletion."""
        team = manager.create_team("TestTeam", "A test team")
        team_id = team.id

        assert manager.delete_team(team_id) is True
        assert manager.get_team(team_id) is None

    def test_delete_nonexistent_team(self, manager):
        """Test deleting a team that doesn't exist."""
        assert manager.delete_team("nonexistent") is False

    def test_spawn_agent(self, manager):
        """Test spawning an agent."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        assert agent is not None
        assert agent.name == "TestBot"
        assert agent.role == "tester"
        assert agent.task == "Run tests"
        assert agent.status == AgentStatus.IDLE
        assert agent.id is not None

    def test_spawn_agent_invalid_team(self, manager):
        """Test spawning an agent in nonexistent team."""
        agent = manager.spawn_agent(
            "invalid_team", "TestBot", "tester", "A test agent", "Run tests"
        )

        assert agent is None

    def test_get_agent(self, manager):
        """Test getting an agent by ID."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        retrieved = manager.get_agent(agent.id)
        assert retrieved is not None
        assert retrieved.id == agent.id

    def test_list_teams(self, manager):
        """Test listing all teams."""
        manager.create_team("Team1", "First team")
        manager.create_team("Team2", "Second team")

        teams = manager.list_teams()
        assert len(teams) == 2

    def test_list_agents(self, manager):
        """Test listing agents."""
        team = manager.create_team("TestTeam", "A test team")
        manager.spawn_agent(team.id, "Bot1", "role1", "desc1", "task1")
        manager.spawn_agent(team.id, "Bot2", "role2", "desc2", "task2")

        agents = manager.list_agents(team.id)
        assert len(agents) == 2

    def test_cancel_agent(self, manager):
        """Test canceling an agent."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")
        agent.status = AgentStatus.RUNNING

        assert manager.cancel_agent(agent.id) is True
        assert agent.status == AgentStatus.CANCELLED

    def test_cancel_non_running_agent(self, manager):
        """Test canceling an agent that's not running."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        assert manager.cancel_agent(agent.id) is False

    def test_share_context(self, manager):
        """Test sharing context in a team."""
        team = manager.create_team("TestTeam", "A test team")

        assert manager.share_context(team.id, "key1", "value1") is True
        assert team.shared_context["key1"] == "value1"

    def test_share_context_invalid_team(self, manager):
        """Test sharing context in nonexistent team."""
        assert manager.share_context("invalid", "key", "value") is False

    def test_get_team_summary(self, manager):
        """Test getting team summary."""
        team = manager.create_team("TestTeam", "A test team")
        manager.spawn_agent(team.id, "Bot1", "role1", "desc1", "task1")

        summary = manager.get_team_summary(team.id)

        assert summary is not None
        assert summary["team"]["name"] == "TestTeam"
        assert summary["progress"]["total"] == 1

    def test_send_message_to_agent(self, manager):
        """Test sending message to agent."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        assert manager.send_message_to_agent(agent.id, "Hello!") is True
        assert len(agent.messages) == 1
        assert agent.messages[0]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_run_agent(self, manager):
        """Test running an agent."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        async def dummy_task(agent):
            return "Task completed"

        result = await manager.run_agent(agent.id, dummy_task)

        assert result is True
        assert agent.status == AgentStatus.COMPLETED
        assert agent.result == "Task completed"

    @pytest.mark.asyncio
    async def test_run_agent_error(self, manager):
        """Test running an agent that errors."""
        team = manager.create_team("TestTeam", "A test team")
        agent = manager.spawn_agent(team.id, "TestBot", "tester", "A test agent", "Run tests")

        async def failing_task(agent):
            raise ValueError("Something went wrong")

        result = await manager.run_agent(agent.id, failing_task)

        assert result is False
        assert agent.status == AgentStatus.ERROR
        assert "Something went wrong" in agent.error


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_team_convenience(self):
        """Test create_team convenience function."""
        team = create_team("ConvenienceTeam", "Created via convenience function")

        assert team.name == "ConvenienceTeam"

        # Clean up
        get_team_manager().delete_team(team.id)
