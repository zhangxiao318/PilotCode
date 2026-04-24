"""Rework and reflection layer for P-EVR orchestration.

Handles:
- Rework context preservation
- Reflector periodic checks
- Redesign triggers
"""

from .rework_context import ReworkContext, ReworkAttempt, ReworkSeverity
from .reflector import Reflector, ReflectorResult

__all__ = [
    "ReworkContext",
    "ReworkAttempt",
    "Reflector",
    "ReflectorResult",
]
