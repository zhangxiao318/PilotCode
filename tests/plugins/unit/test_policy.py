"""Unit tests for plugin policy."""

import json
import pytest

try:
    from pilotcode.plugins.policy import (
        PolicyManager,
        PluginPolicy,
        PolicyRule,
        PolicyAction,
        PolicyScope,
        AuditLogger,
        AuditAction,
        AuditOutcome,
    )

    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False

pytestmark = [
    pytest.mark.plugin,
    pytest.mark.plugin_unit,
    pytest.mark.unit,
    pytest.mark.skipif(not PLUGINS_AVAILABLE, reason="Plugin system not available"),
]


class TestPolicyRule:
    """Test PolicyRule."""

    def test_create_rule(self):
        """Test creating policy rule."""
        rule = PolicyRule(
            name="block-external",
            description="Block external marketplaces",
            scope=PolicyScope.MARKETPLACE,
            pattern="*external*",
            action=PolicyAction.DENY,
        )

        assert rule.name == "block-external"
        assert rule.action == PolicyAction.DENY

    def test_matches_pattern(self):
        """Test pattern matching."""
        rule = PolicyRule(
            name="test",
            description="Test",
            scope=PolicyScope.MARKETPLACE,
            pattern="claude-*",
            action=PolicyAction.ALLOW,
        )

        assert rule.matches("claude-plugins-official") is True
        assert rule.matches("other-marketplace") is False

    def test_matches_wildcard(self):
        """Test wildcard pattern matching."""
        rule = PolicyRule(
            name="block-all",
            description="Block all",
            scope=PolicyScope.MARKETPLACE,
            pattern="*",
            action=PolicyAction.DENY,
        )

        assert rule.matches("anything") is True
        assert rule.matches("") is True


class TestPluginPolicy:
    """Test PluginPolicy."""

    def test_create_policy(self):
        """Test creating policy."""
        policy = PluginPolicy(
            name="company-policy",
            version="1.0",
            description="Company plugin policy",
        )

        assert policy.name == "company-policy"
        assert policy.require_signatures is False

    def test_to_dict(self):
        """Test conversion to dict."""
        policy = PluginPolicy(
            name="test",
            allowed_marketplaces=["official"],
            blocked_publishers=["bad-actor"],
        )

        data = policy.to_dict()

        assert data["name"] == "test"
        assert data["allowed_marketplaces"] == ["official"]
        assert data["blocked_publishers"] == ["bad-actor"]

    def test_from_dict(self):
        """Test creation from dict."""
        data = {
            "name": "test-policy",
            "version": "2.0",
            "allowed_marketplaces": ["m1", "m2"],
            "rules": [
                {
                    "name": "rule1",
                    "description": "Test rule",
                    "scope": "marketplace",
                    "pattern": "*",
                    "action": "allow",
                }
            ],
        }

        policy = PluginPolicy.from_dict(data)

        assert policy.name == "test-policy"
        assert policy.version == "2.0"
        assert len(policy.allowed_marketplaces) == 2
        assert len(policy.rules) == 1


class TestPolicyManager:
    """Test PolicyManager."""

    def test_load_default_policy(self, temp_config_dir):
        """Test loading default policy when no file exists."""
        # Change to temp dir so no policy files exist
        import os

        original_cwd = os.getcwd()
        os.chdir(temp_config_dir)

        try:
            manager = PolicyManager()

            # Should have default permissive policy
            assert manager.policy is not None
            assert manager.policy.name == "default"
        finally:
            os.chdir(original_cwd)

    def test_check_marketplace_allowed(self, temp_config_dir):
        """Test checking allowed marketplace."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.allowed_marketplaces = ["official", "internal"]

        allowed, msg = manager.check_marketplace("official")

        assert allowed is True
        assert msg is None

    def test_check_marketplace_blocked(self, temp_config_dir):
        """Test checking blocked marketplace."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.blocked_marketplaces = ["untrusted"]

        allowed, msg = manager.check_marketplace("untrusted")

        assert allowed is False
        assert "blocked" in msg.lower()

    def test_check_marketplace_not_in_allowlist(self, temp_config_dir):
        """Test marketplace not in allowlist."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.allowed_marketplaces = ["official"]

        allowed, msg = manager.check_marketplace("unknown")

        assert allowed is False

    def test_check_plugin_allowed(self, temp_config_dir):
        """Test checking allowed plugin."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")

        allowed, msg = manager.check_plugin("docker@official")

        assert allowed is True

    def test_check_plugin_blocked(self, temp_config_dir):
        """Test checking blocked plugin."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.blocked_plugins = ["dangerous"]

        allowed, msg = manager.check_plugin("dangerous@official")

        assert allowed is False

    def test_check_rules(self, temp_config_dir):
        """Test checking policy rules."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.rules.append(
            PolicyRule(
                name="block-test",
                description="Block test plugins",
                scope=PolicyScope.PLUGIN,
                pattern="test-*",
                action=PolicyAction.DENY,
            )
        )

        action, msg = manager.check_rules("official", "publisher", "test-plugin")

        assert action == PolicyAction.DENY

    def test_can_install(self, temp_config_dir):
        """Test comprehensive install check."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")

        allowed, msg = manager.can_install(
            plugin_id="docker@official",
            publisher="anthropics",
            marketplace="official",
        )

        assert allowed is True

    def test_can_auto_update(self, temp_config_dir):
        """Test auto-update check."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.auto_update_allowed = True

        assert manager.can_auto_update("docker@official", "official") is True

        manager.policy.auto_update_allowed = False
        assert manager.can_auto_update("docker@official", "official") is False

    def test_requires_signature(self, temp_config_dir):
        """Test signature requirement check."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")

        assert manager.requires_signature() is False

        manager.policy.require_signatures = True
        assert manager.requires_signature() is True

    def test_get_policy_summary(self, temp_config_dir):
        """Test getting policy summary."""
        manager = PolicyManager(policy_path=temp_config_dir / "policy.json")
        manager.policy.name = "Test Policy"
        manager.policy.allowed_marketplaces = ["official"]

        summary = manager.get_policy_summary()

        assert "Test Policy" in summary
        assert "official" in summary


class TestAuditLogger:
    """Test AuditLogger."""

    def test_log_event(self, temp_config_dir):
        """Test logging an event."""
        log_path = temp_config_dir / "audit.log"
        logger = AuditLogger(log_path=log_path)

        logger.log(
            action=AuditAction.INSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
            message="Plugin installed successfully",
        )

        assert log_path.exists()

    def test_get_events(self, temp_config_dir):
        """Test retrieving events."""
        log_path = temp_config_dir / "audit.log"
        logger = AuditLogger(log_path=log_path)

        logger.log(
            action=AuditAction.INSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )
        logger.log(
            action=AuditAction.INSTALL,
            outcome=AuditOutcome.FAILURE,
            plugin_id="other@official",
        )

        events = logger.get_events(limit=10)

        assert len(events) == 2

    def test_get_events_filtered(self, temp_config_dir):
        """Test retrieving filtered events."""
        log_path = temp_config_dir / "audit.log"
        logger = AuditLogger(log_path=log_path)

        logger.log(
            action=AuditAction.INSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )
        logger.log(
            action=AuditAction.UNINSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )

        events = logger.get_events(action=AuditAction.INSTALL, limit=10)

        assert len(events) == 1
        assert events[0].action == AuditAction.INSTALL.value

    def test_get_install_history(self, temp_config_dir):
        """Test getting install history."""
        log_path = temp_config_dir / "audit.log"
        logger = AuditLogger(log_path=log_path)

        logger.log(
            action=AuditAction.INSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )
        logger.log(
            action=AuditAction.UNINSTALL,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )
        logger.log(
            action=AuditAction.ENABLE,
            outcome=AuditOutcome.SUCCESS,
            plugin_id="docker@official",
        )

        history = logger.get_install_history("docker@official")

        assert len(history) == 2
        actions = [e.action for e in history]
        assert AuditAction.INSTALL.value in actions
        assert AuditAction.UNINSTALL.value in actions
