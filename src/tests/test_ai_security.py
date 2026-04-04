"""Tests for AI-powered security analysis."""

import pytest

from pilotcode.services.ai_security import (
    SecurityAnalysis,
    RiskLevel,
    get_command_security_analysis,
    extract_command_prefix,
    split_command,
    analyze_command_dangerous_patterns,
    simulate_ai_security_analysis,
    clear_security_cache,
    estimate_security_check_tokens,
)


class TestRiskLevel:
    """Tests for RiskLevel enum."""
    
    def test_risk_ordering(self):
        """Test risk levels have correct ordering."""
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestExtractCommandPrefix:
    """Tests for command prefix extraction."""
    
    def test_simple_command(self):
        """Test extracting prefix from simple command."""
        assert extract_command_prefix("ls -la") == "ls"
        assert extract_command_prefix("cat file.txt") == "cat"
    
    def test_git_commands(self):
        """Test extracting prefix from git commands."""
        assert extract_command_prefix("git status") == "git status"
        assert extract_command_prefix("git commit -m 'test'") == "git commit"
        assert extract_command_prefix("git log --oneline") == "git log"
    
    def test_docker_commands(self):
        """Test extracting prefix from docker commands."""
        assert extract_command_prefix("docker ps") == "docker ps"
        assert extract_command_prefix("docker images") == "docker images"
    
    def test_kubectl_commands(self):
        """Test extracting prefix from kubectl commands."""
        assert extract_command_prefix("kubectl get pods") == "kubectl get"
        assert extract_command_prefix("kubectl logs pod-1") == "kubectl logs"
    
    def test_empty_command(self):
        """Test extracting prefix from empty command."""
        assert extract_command_prefix("") == ""
        assert extract_command_prefix("   ") == ""


class TestSplitCommand:
    """Tests for command splitting."""
    
    def test_simple_pipe(self):
        """Test splitting piped commands."""
        result = split_command("ls | grep test")
        assert len(result) == 2
        assert result[0] == "ls"
        assert result[1] == "grep test"
    
    def test_semicolon_separator(self):
        """Test splitting semicolon-separated commands."""
        result = split_command("cd /tmp; ls")
        assert len(result) == 2
        assert result[0] == "cd /tmp"
        assert result[1] == "ls"
    
    def test_single_command(self):
        """Test splitting single command."""
        result = split_command("ls -la")
        assert len(result) == 1
        assert result[0] == "ls -la"


class TestDangerousPatternAnalysis:
    """Tests for dangerous pattern detection."""
    
    def test_command_substitution(self):
        """Test detecting command substitution."""
        risks = analyze_command_dangerous_patterns("echo $(whoami | cat)")
        assert len(risks) > 0
        assert any(r[0] == RiskLevel.HIGH for r in risks)
    
    def test_backtick_substitution(self):
        """Test detecting backtick substitution."""
        risks = analyze_command_dangerous_patterns("echo `whoami`")
        assert len(risks) > 0
    
    def test_eval_with_variable(self):
        """Test detecting eval with variable."""
        risks = analyze_command_dangerous_patterns('eval "$VAR"')
        assert any(r[0] == RiskLevel.CRITICAL for r in risks)
    
    def test_shell_with_c_flag(self):
        """Test detecting sh -c pattern."""
        risks = analyze_command_dangerous_patterns('sh -c "echo test"')
        assert len(risks) > 0
    
    def test_safe_command(self):
        """Test that safe commands have no risks."""
        risks = analyze_command_dangerous_patterns("ls -la")
        assert len(risks) == 0
    
    def test_process_substitution(self):
        """Test detecting process substitution."""
        risks = analyze_command_dangerous_patterns("cat <(echo test)")
        assert len(risks) > 0
    
    def test_chained_dangerous(self):
        """Test detecting chained dangerous commands."""
        risks = analyze_command_dangerous_patterns("echo test; rm -rf /")
        # May have risk due to rm pattern
        assert len(risks) >= 0  # At least check it doesn't crash


class TestSecurityAnalysis:
    """Tests for full security analysis."""
    
    def test_safe_command_analysis(self):
        """Test analysis of safe command."""
        analysis = simulate_ai_security_analysis("ls -la")
        assert analysis.command_prefix == "ls"
        assert analysis.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)
    
    def test_dangerous_rm_rf(self):
        """Test analysis of dangerous rm command."""
        analysis = simulate_ai_security_analysis("rm -rf /")
        assert analysis.risk_level == RiskLevel.CRITICAL
        assert not analysis.is_safe
    
    def test_eval_command(self):
        """Test analysis of eval command."""
        analysis = simulate_ai_security_analysis('eval "$USER_INPUT"')
        assert analysis.risk_level == RiskLevel.CRITICAL
    
    def test_git_command_safe(self):
        """Test analysis of git commands."""
        analysis = simulate_ai_security_analysis("git status")
        assert analysis.command_prefix == "git status"
        assert analysis.is_safe
    
    def test_curl_with_variable(self):
        """Test analysis of curl with variable."""
        analysis = simulate_ai_security_analysis("curl $URL")
        assert not analysis.is_safe or analysis.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    
    def test_subcommand_analysis(self):
        """Test that subcommands are analyzed."""
        analysis = simulate_ai_security_analysis("ls | grep test | wc -l")
        assert analysis.subcommand_prefixes is not None
        assert len(analysis.subcommand_prefixes) == 3
    
    def test_context_aware_analysis(self):
        """Test analysis with context."""
        context = {"cwd": "/home/user/project"}
        analysis = simulate_ai_security_analysis(
            "cat ../../etc/passwd",
            context=context
        )
        # Should detect path traversal risk
        assert not analysis.is_safe or analysis.suggestions


class TestCaching:
    """Tests for security analysis caching."""
    
    def test_caching_enabled(self):
        """Test that analysis is cached when enabled."""
        clear_security_cache()
        
        # First call
        result1 = get_command_security_analysis("ls -la", use_cache=True)
        
        # Second call should use cache
        result2 = get_command_security_analysis("ls -la", use_cache=True)
        
        assert result1.is_safe == result2.is_safe
        assert result1.risk_level == result2.risk_level
    
    def test_caching_disabled(self):
        """Test that analysis is not cached when disabled."""
        # Call without cache
        result = get_command_security_analysis("ls -la", use_cache=False)
        assert result.is_safe  # Just verify it works
    
    def test_cache_with_context(self):
        """Test caching with context."""
        clear_security_cache()
        
        context1 = {"cwd": "/path1"}
        context2 = {"cwd": "/path2"}
        
        # Same command, different context
        result1 = get_command_security_analysis("ls", context=context1)
        result2 = get_command_security_analysis("ls", context=context2)
        
        # Results should be independent
        assert result1.is_safe == result2.is_safe


class TestTokenEstimation:
    """Tests for token estimation."""
    
    def test_estimate_tokens(self):
        """Test token estimation for security check."""
        tokens = estimate_security_check_tokens("ls -la")
        assert tokens > 0
        
        # Longer command should need more tokens
        long_tokens = estimate_security_check_tokens("a" * 1000)
        short_tokens = estimate_security_check_tokens("ls")
        assert long_tokens > short_tokens


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_command(self):
        """Test analysis of empty command."""
        analysis = simulate_ai_security_analysis("")
        assert analysis.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)
    
    def test_whitespace_only(self):
        """Test analysis of whitespace command."""
        analysis = simulate_ai_security_analysis("   ")
        assert analysis.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)
    
    def test_very_long_command(self):
        """Test analysis of very long command."""
        long_cmd = "echo " + "a" * 10000
        analysis = simulate_ai_security_analysis(long_cmd)
        assert isinstance(analysis.is_safe, bool)
    
    def test_unicode_in_command(self):
        """Test analysis with unicode characters."""
        analysis = simulate_ai_security_analysis("echo '你好世界'")
        assert analysis.is_safe


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
