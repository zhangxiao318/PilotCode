"""Plugin security features.

Provides:
- Plugin signing and verification
- Trust store management
- Security policy enforcement
"""

from .signature import SignatureManager, PluginSignature
from .trust import TrustStore, TrustLevel
from .verification import PluginVerifier, VerificationResult, VerificationStatus

__all__ = [
    "SignatureManager",
    "PluginSignature",
    "TrustStore",
    "TrustLevel",
    "PluginVerifier",
    "VerificationResult",
    "VerificationStatus",
]
