"""Tests for risk_assessment module."""

import pytest

from pilotcode.services.risk_assessment import (
    RiskLevel,
    RiskAssessment,
    CommandRiskAnalyzer,
    ToolRiskAnalyzer,
    get_risk_analyzer,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels(self):
        """Test all risk levels exist."""
        assert RiskLevel.NONE.value == "none"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestRiskAssessment:
    """Tests for RiskAssessment dataclass."""

    def test_creation(self):
        """Test creating RiskAssessment."""
        assessment = RiskAssessment(
            level=RiskLevel.MEDIUM,
            reason="Test reason",
            auto_allow=False,
            requires_confirmation=True,
            destructive=False,
            read_only=False,
        )

        assert assessment.level == RiskLevel.MEDIUM
        assert assessment.reason == "Test reason"
        assert assessment.auto_allow is False
        assert assessment.requires_confirmation is True
        assert assessment.destructive is False
        assert assessment.read_only is False


class TestCommandRiskAnalyzer:
    """Tests for CommandRiskAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create CommandRiskAnalyzer instance."""
        return CommandRiskAnalyzer()

    def test_assess_bash_command(self, analyzer):
        """Test assessing bash command."""
        result = analyzer.assess_bash_command("echo hello")

        assert isinstance(result, RiskAssessment)
        assert result.level is not None

    def test_dangerous_command_detected(self, analyzer):
        """Test dangerous command detection."""
        result = analyzer.assess_bash_command("rm -rf /")

        assert result.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert result.destructive is True

    def test_readonly_command_detected(self, analyzer):
        """Test read-only command detection."""
        result = analyzer.assess_bash_command("ls -la")

        assert result.read_only is True
        assert result.level == RiskLevel.NONE

    def test_is_write_operation(self, analyzer):
        """Test write operation detection."""
        assert analyzer._is_write_operation("> file.txt") is True
        assert analyzer._is_write_operation("echo test") is False


class TestToolRiskAnalyzer:
    """Tests for ToolRiskAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create ToolRiskAnalyzer instance."""
        return ToolRiskAnalyzer()

    def test_assess_file_read(self, analyzer):
        """Test FileRead tool assessment."""
        result = analyzer.assess_tool("FileRead", {"file_path": "/tmp/test.txt"})

        # FileRead is NONE risk in general, but specific paths may be higher
        assert result.level is not None
        assert result.read_only is True  # FileRead is always read-only

    def test_assess_file_write(self, analyzer):
        """Test FileWrite tool assessment."""
        result = analyzer.assess_tool("FileWrite", {"file_path": "/tmp/test.txt"})

        assert result.level == RiskLevel.MEDIUM
        assert result.read_only is False

    def test_assess_bash_safe(self, analyzer):
        """Test safe Bash command."""
        result = analyzer.assess_tool("Bash", {"command": "echo hello"})

        assert result.read_only is True
        assert result.auto_allow is True

    def test_assess_bash_dangerous(self, analyzer):
        """Test dangerous Bash command."""
        result = analyzer.assess_tool("Bash", {"command": "rm -rf /"})

        assert result.destructive is True
        assert result.auto_allow is False
        assert result.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

    def test_assess_glob(self, analyzer):
        """Test Glob tool assessment."""
        result = analyzer.assess_tool("Glob", {"pattern": "*.py"})

        assert result.level == RiskLevel.NONE
        assert result.read_only is True

    def test_assess_git_status(self, analyzer):
        """Test GitStatus tool assessment."""
        result = analyzer.assess_tool("GitStatus", {})

        # GitStatus is not in TOOL_RISKS, defaults to MEDIUM
        # but is effectively read-only
        assert result.level is not None

    def test_assess_unknown_tool(self, analyzer):
        """Test unknown tool defaults to MEDIUM."""
        result = analyzer.assess_tool("UnknownTool", {})

        assert result.level == RiskLevel.MEDIUM


class TestGlobalAnalyzer:
    """Tests for global risk analyzer."""

    def test_get_risk_analyzer_singleton(self):
        """Test that get_risk_analyzer returns singleton."""
        analyzer1 = get_risk_analyzer()
        analyzer2 = get_risk_analyzer()

        assert analyzer1 is analyzer2

    def test_global_analyzer_is_tool_risk_analyzer(self):
        """Test global analyzer is ToolRiskAnalyzer."""
        analyzer = get_risk_analyzer()

        assert isinstance(analyzer, ToolRiskAnalyzer)

    def test_tool_risk_mappings(self):
        """Test that TOOL_RISKS mappings exist."""
        analyzer = get_risk_analyzer()

        assert "Bash" in analyzer.TOOL_RISKS
        assert "FileRead" in analyzer.TOOL_RISKS
        assert "FileWrite" in analyzer.TOOL_RISKS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
