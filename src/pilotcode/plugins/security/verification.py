"""Plugin verification system.

Combines signature verification with trust store for comprehensive
plugin security verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .signature import SignatureManager, PluginSignature
from .trust import TrustStore, TrustLevel


class VerificationStatus(Enum):
    """Verification status."""

    VERIFIED = "verified"  # Signature valid, trusted publisher
    UNVERIFIED = "unverified"  # No signature found
    UNTRUSTED = "untrusted"  # Valid signature but untrusted publisher
    INVALID = "invalid"  # Invalid signature
    BLOCKED = "blocked"  # Publisher blocked
    EXPIRED = "expired"  # Signature expired
    TAMPERED = "tampered"  # Content doesn't match signature


@dataclass
class VerificationResult:
    """Result of plugin verification."""

    status: VerificationStatus
    plugin_name: str
    plugin_version: str
    publisher: Optional[str] = None
    trust_level: Optional[TrustLevel] = None
    signature_valid: bool = False
    message: str = ""
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    @property
    def can_install(self) -> bool:
        """Check if plugin can be installed based on verification."""
        return self.status not in (
            VerificationStatus.BLOCKED,
            VerificationStatus.INVALID,
            VerificationStatus.TAMPERED,
        )

    @property
    def should_warn(self) -> bool:
        """Check if user should be warned."""
        return self.status in (
            VerificationStatus.UNVERIFIED,
            VerificationStatus.UNTRUSTED,
            VerificationStatus.EXPIRED,
        )


class PluginVerifier:
    """Verifies plugins before installation.

    Performs comprehensive verification including:
    - Signature validation
    - Publisher trust check
    - Content integrity verification
    - Expiration check
    """

    def __init__(
        self,
        signature_manager: Optional[SignatureManager] = None,
        trust_store: Optional[TrustStore] = None,
    ):
        self.signature_manager = signature_manager or SignatureManager()
        self.trust_store = trust_store or TrustStore()

        # Verification policy
        self.require_signature = False  # If True, reject unsigned plugins
        self.require_trusted = False  # If True, reject untrusted publishers
        self.auto_trust_official = True  # Auto-trust official marketplace

    def verify(
        self,
        plugin_path: Path,
        expected_publisher: Optional[str] = None,
    ) -> VerificationResult:
        """Verify a plugin.

        Args:
            plugin_path: Path to plugin directory
            expected_publisher: Expected publisher (if known)

        Returns:
            VerificationResult
        """
        # Load plugin manifest
        manifest = self._load_manifest(plugin_path)
        if not manifest:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                plugin_name=plugin_path.name,
                plugin_version="unknown",
                message="Plugin manifest not found",
            )

        plugin_name = manifest.get("name", plugin_path.name)
        plugin_version = manifest.get("version", "unknown")

        # Check for signature file
        sig_path = plugin_path / ".signature.json"
        if not sig_path.exists():
            sig_path = plugin_path / ".claude-plugin" / ".signature.json"

        if not sig_path.exists():
            # No signature - unverified
            if self.require_signature:
                return VerificationResult(
                    status=VerificationStatus.INVALID,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    message="Plugin signature required but not found",
                )

            return VerificationResult(
                status=VerificationStatus.UNVERIFIED,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                message="Plugin is not signed. Proceed with caution.",
            )

        # Load signature
        signature = self.signature_manager.load_signature(sig_path)
        if not signature:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                message="Failed to load plugin signature",
            )

        # Check signature expiration
        if signature.is_expired():
            return VerificationResult(
                status=VerificationStatus.EXPIRED,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                publisher=signature.signer,
                message=f"Signature expired on {signature.expires}",
            )

        # Determine publisher
        publisher = signature.signer

        # Check if publisher is blocked
        if self.trust_store.is_blocked(publisher):
            return VerificationResult(
                status=VerificationStatus.BLOCKED,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                publisher=publisher,
                trust_level=TrustLevel.BLOCKED,
                message=f"Publisher '{publisher}' is blocked",
            )

        # Get publisher's public key
        public_key = self.trust_store.get_public_key(publisher)
        if not public_key:
            # Unknown publisher with valid signature
            trust_level = self.trust_store.get_trust_level(publisher)

            if self.require_trusted:
                return VerificationResult(
                    status=VerificationStatus.UNTRUSTED,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    publisher=publisher,
                    trust_level=trust_level,
                    message=f"Publisher '{publisher}' is not trusted",
                )

            # Continue with verification but warn
            result = self._verify_signature(plugin_path, signature, None)
            result.trust_level = trust_level
            return result

        # Verify signature
        try:
            valid = self.signature_manager.verify_signature(plugin_path, signature, public_key)

            if not valid:
                return VerificationResult(
                    status=VerificationStatus.TAMPERED,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    publisher=publisher,
                    signature_valid=False,
                    message="Plugin content does not match signature. Possible tampering.",
                )

            # Signature valid
            trust_level = self.trust_store.get_trust_level(publisher)

            if trust_level == TrustLevel.UNTRUSTED and self.require_trusted:
                return VerificationResult(
                    status=VerificationStatus.UNTRUSTED,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    publisher=publisher,
                    trust_level=trust_level,
                    signature_valid=True,
                    message=f"Publisher '{publisher}' is not in trust store",
                )

            return VerificationResult(
                status=VerificationStatus.VERIFIED,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                publisher=publisher,
                trust_level=trust_level,
                signature_valid=True,
                message=f"Plugin verified. Signed by {publisher} ({trust_level.value})",
            )

        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                message=f"Signature verification failed: {e}",
            )

    def _verify_signature(
        self,
        plugin_path: Path,
        signature: PluginSignature,
        public_key: Optional[str],
    ) -> VerificationResult:
        """Verify signature without trust check."""
        plugin_name = signature.plugin_name
        plugin_version = signature.plugin_version

        if not public_key:
            # Can't verify without public key
            return VerificationResult(
                status=VerificationStatus.UNVERIFIED,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                publisher=signature.signer,
                signature_valid=False,
                message=f"Cannot verify: no public key for {signature.signer}",
            )

        try:
            valid = self.signature_manager.verify_signature(plugin_path, signature, public_key)

            if valid:
                return VerificationResult(
                    status=VerificationStatus.VERIFIED,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    publisher=signature.signer,
                    signature_valid=True,
                    message="Signature valid but publisher not in trust store",
                    warnings=["Publisher not verified"],
                )
            else:
                return VerificationResult(
                    status=VerificationStatus.TAMPERED,
                    plugin_name=plugin_name,
                    plugin_version=plugin_version,
                    publisher=signature.signer,
                    signature_valid=False,
                    message="Signature verification failed",
                )
        except Exception as e:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                plugin_name=plugin_name,
                plugin_version=plugin_version,
                message=f"Verification error: {e}",
            )

    def _load_manifest(self, plugin_path: Path) -> Optional[dict]:
        """Load plugin manifest."""
        import json

        manifest_paths = [
            plugin_path / "plugin.json",
            plugin_path / ".claude-plugin" / "plugin.json",
        ]

        for path in manifest_paths:
            if path.exists():
                try:
                    with open(path, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

        return None

    def quick_check(
        self,
        plugin_path: Path,
    ) -> tuple[bool, str]:
        """Quick verification check.

        Returns:
            Tuple of (can_install, message)
        """
        result = self.verify(plugin_path)
        return result.can_install, result.message

    def set_policy(
        self,
        require_signature: Optional[bool] = None,
        require_trusted: Optional[bool] = None,
    ) -> None:
        """Set verification policy."""
        if require_signature is not None:
            self.require_signature = require_signature
        if require_trusted is not None:
            self.require_trusted = require_trusted


class VerificationError(Exception):
    """Verification error."""

    pass
