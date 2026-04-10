"""Policy enforcement for plugin operations.

Integrates policy checks with plugin operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .policy import PolicyManager, PolicyAction
from .audit import AuditLogger, AuditAction, AuditOutcome
from ..security.verification import PluginVerifier, VerificationResult


class PolicyEnforcer:
    """Enforces policies on plugin operations.

    Combines policy checks with security verification and audit logging.
    """

    def __init__(
        self,
        policy_manager: Optional[PolicyManager] = None,
        verifier: Optional[PluginVerifier] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.policy = policy_manager or PolicyManager()
        self.verifier = verifier or PluginVerifier()
        self.audit = audit_logger or AuditLogger()

    async def check_install(
        self,
        plugin_id: str,
        publisher: str,
        marketplace: str,
        plugin_path: Optional[Path] = None,
    ) -> tuple[bool, str]:
        """Check if plugin can be installed.

        Performs:
        1. Policy checks
        2. Security verification (if path provided)
        3. Audit logging

        Returns:
            Tuple of (allowed, message)
        """
        # Policy check
        allowed, message = self.policy.can_install(plugin_id, publisher, marketplace)
        if not allowed:
            self._log_denied(AuditAction.INSTALL, plugin_id, message)
            return False, message

        # Check if approval required
        if self.policy.requires_approval():
            self._log_event(
                AuditAction.INSTALL,
                AuditOutcome.WARNING,
                plugin_id,
                "Installation requires approval",
            )
            return True, "Installation requires admin approval"

        # Security verification
        if plugin_path:
            if self.policy.requires_signature():
                self.verifier.set_policy(require_signature=True)

            result = self.verifier.verify(plugin_path)

            if not result.can_install:
                self._log_denied(AuditAction.INSTALL, plugin_id, result.message)
                return False, result.message

            if result.should_warn:
                self._log_event(
                    AuditAction.VERIFY,
                    AuditOutcome.WARNING,
                    plugin_id,
                    result.message,
                )

        # Log success
        if self.policy.should_audit_installs():
            self._log_event(
                AuditAction.INSTALL,
                AuditOutcome.SUCCESS,
                plugin_id,
                "Installation approved",
            )

        return True, "Allowed"

    def check_update(self, plugin_id: str, marketplace: str) -> tuple[bool, str]:
        """Check if auto-update is allowed."""
        if not self.policy.can_auto_update(plugin_id, marketplace):
            return False, "Auto-update not allowed by policy"
        return True, "Allowed"

    def check_marketplace(self, marketplace: str) -> tuple[bool, str]:
        """Check if marketplace is allowed."""
        return self.policy.check_marketplace(marketplace)

    def _log_event(
        self,
        action: AuditAction,
        outcome: AuditOutcome,
        plugin_id: Optional[str],
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        """Log audit event."""
        self.audit.log(
            action=action,
            outcome=outcome,
            plugin_id=plugin_id,
            message=message,
            details=details,
        )

    def _log_denied(
        self,
        action: AuditAction,
        plugin_id: str,
        reason: str,
    ) -> None:
        """Log policy denial."""
        self._log_event(
            action=AuditAction.POLICY_VIOLATION,
            outcome=AuditOutcome.DENIED,
            plugin_id=plugin_id,
            message=reason,
        )

    def get_policy_summary(self) -> str:
        """Get policy summary."""
        return self.policy.get_policy_summary()
