"""Secure API key storage with layered fallback strategy.

Priority chain:
  1. Environment variable  (highest — never persisted)
  2. OS keyring            (macOS Keychain / Linux Secret Service / Windows Credential Manager)
  3. Encrypted local file  (AES-256-GCM, key derived from machine fingerprint + random salt)
  4. Plaintext config file (legacy fallback — triggers one-shot migration to encrypted)

Encrypted file location:  <CONFIG_DIR>/credentials.enc
Salt file location:       <CONFIG_DIR>/credentials.salt
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVICE_NAME = "pilotcode"
_ACCOUNT_NAME = "api_key"

_CONFIG_DIR = Path(user_config_dir("pilotcode", "pilotcode"))
_ENCRYPTED_FILE = _CONFIG_DIR / "credentials.enc"
_SALT_FILE = _CONFIG_DIR / "credentials.salt"

_KEYRING_AVAILABLE = False
try:
    import keyring

    _KEYRING_AVAILABLE = True
except ImportError:
    pass

_CRYPTO_AVAILABLE = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Machine fingerprinting (for key derivation, NOT for telemetry)
# ---------------------------------------------------------------------------


def _machine_fingerprint() -> bytes:
    """Derive a stable machine fingerprint for key derivation.

    Combines multiple system identifiers that are stable across reboots
    but unique per machine.  This is NOT a telemetry mechanism — the
    fingerprint never leaves the local machine.
    """
    parts: list[str] = []

    # Hardware / system identifiers
    try:
        parts.append(str(uuid.getnode()))  # MAC address
    except Exception:
        pass

    try:
        parts.append(os.environ.get("HOME", ""))
    except Exception:
        pass

    try:
        parts.append(os.environ.get("USER", os.environ.get("USERNAME", "")))
    except Exception:
        pass

    try:
        import platform

        parts.append(platform.node())  # hostname
        parts.append(platform.machine())  # x86_64, arm64, etc.
    except Exception:
        pass

    combined = "|".join(parts)
    return hashlib.sha256(combined.encode()).digest()


def _derive_key(salt: bytes) -> bytes:
    """Derive a 256-bit AES key from the machine fingerprint + salt.

    Uses PBKDF2 with 600 000 iterations (OWASP 2023 recommendation).
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography library is required for encrypted storage")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return kdf.derive(_machine_fingerprint())


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------


@dataclass
class StorageResult:
    """Result of a storage operation."""

    value: str | None
    source: str  # "env", "keyring", "encrypted", "plaintext"


# Common placeholder tokens that should never be treated as real API keys.
_PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "local",
    "test",
    "fake",
    "dummy",
    "placeholder",
    "your",
    "example",
    "sample",
    "demo",
    "invalid",
    "wrong",
    "mock",
    "changeme",
    "password",
    "secret",
    "key",
    "token",
    "xxx",
    "aaaa",
    "bbbb",
    "cccc",
    "dddd",
    "eeee",
    "ffff",
)


def _is_placeholder_key(val: str) -> bool:
    """Heuristically detect placeholder or fake API keys.

    Rules (conservative — avoids false positives on real keys):
    1. Too short (< 8 chars)
    2. Contains common placeholder words
    3. All characters are identical or only letters + hyphens and very short
    4. Looks like a demo key (e.g. "sk-local-api-key")
    """
    if len(val) < 8:
        return True

    lowered = val.lower()

    # Contains obvious placeholder words
    for pat in _PLACEHOLDER_PATTERNS:
        if pat in lowered:
            return True

    # All same character (e.g. "xxxxxxxx")
    if len(set(val)) == 1:
        return True

    # Very short and only lowercase letters + hyphens (e.g. "local-api-key")
    if len(val) < 24 and val.replace("-", "").replace("_", "").isalpha() and val.islower():
        return True

    return False


def _env_get() -> str | None:
    """Try to read API key from environment variables.

    Placeholder / demo keys are filtered out so that secure storage
    (keyring or encrypted file) can take precedence.
    """
    for env_var in (
        "PILOTCODE_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DASHSCOPE_API_KEY",
        "ZHIPU_API_KEY",
        "MOONSHOT_API_KEY",
        "BAICHUAN_API_KEY",
        "ARK_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        val = os.environ.get(env_var)
        if not val:
            continue
        if _is_placeholder_key(val):
            import logging

            logging.getLogger(__name__).debug(
                "Ignoring placeholder API key from %s (starts with: %s...)",
                env_var,
                val[:8],
            )
            continue
        return val
    return None


def _keyring_get() -> str | None:
    """Try to read API key from OS keyring."""
    if not _KEYRING_AVAILABLE:
        return None
    try:
        return keyring.get_password(_SERVICE_NAME, _ACCOUNT_NAME)
    except Exception:
        return None


def _keyring_set(value: str) -> bool:
    """Store API key in OS keyring."""
    if not _KEYRING_AVAILABLE:
        return False
    try:
        keyring.set_password(_SERVICE_NAME, _ACCOUNT_NAME, value)
        return True
    except Exception:
        return False


def _keyring_delete() -> bool:
    """Remove API key from OS keyring."""
    if not _KEYRING_AVAILABLE:
        return False
    try:
        keyring.delete_password(_SERVICE_NAME, _ACCOUNT_NAME)
        return True
    except Exception:
        return False


def _encrypted_get() -> str | None:
    """Try to read API key from AES-256-GCM encrypted file."""
    if not _CRYPTO_AVAILABLE:
        return None
    if not _ENCRYPTED_FILE.exists() or not _SALT_FILE.exists():
        return None
    try:
        salt = _SALT_FILE.read_bytes()
        key = _derive_key(salt)
        data = _ENCRYPTED_FILE.read_bytes()
        # Format: 12-byte nonce || ciphertext+tag
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception:
        return None


def _encrypted_set(value: str) -> bool:
    """Store API key in AES-256-GCM encrypted file."""
    if not _CRYPTO_AVAILABLE:
        return False
    try:
        salt = secrets.token_bytes(32)
        key = _derive_key(salt)
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _SALT_FILE.write_bytes(salt)
        # Set restrictive permissions: only owner can read
        os.chmod(_SALT_FILE, 0o600)
        _ENCRYPTED_FILE.write_bytes(nonce + ciphertext)
        os.chmod(_ENCRYPTED_FILE, 0o600)
        return True
    except Exception:
        return False


def _encrypted_delete() -> bool:
    """Remove encrypted credentials files."""
    removed = False
    for path in (_ENCRYPTED_FILE, _SALT_FILE):
        try:
            path.unlink(missing_ok=True)
            removed = True
        except Exception:
            pass
    return removed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_api_key() -> StorageResult:
    """Retrieve the API key using the layered fallback strategy.

    Priority: env > keyring > encrypted

    Returns:
        StorageResult with the key value and source.
    """
    # 1. Environment variable (highest priority)
    val = _env_get()
    if val:
        return StorageResult(value=val, source="env")

    # 2. OS keyring
    val = _keyring_get()
    if val:
        return StorageResult(value=val, source="keyring")

    # 3. Encrypted local file
    val = _encrypted_get()
    if val:
        return StorageResult(value=val, source="encrypted")

    return StorageResult(value=None, source="")


def store_api_key(value: str) -> str:
    """Persist an API key using the best available secure storage.

    Tries keyring first, falls back to encrypted file.

    Args:
        value: The API key string to store.

    Returns:
        The storage backend used: "keyring" or "encrypted".

    Raises:
        RuntimeError: If neither keyring nor encrypted storage is available.
    """
    # Try OS keyring first (best UX + security)
    if _keyring_set(value):
        return "keyring"

    # Fall back to encrypted file
    if _encrypted_set(value):
        return "encrypted"

    raise RuntimeError(
        "No secure storage backend available. "
        "Install 'keyring' (recommended) or 'cryptography' to enable secure API key storage. "
        "As a temporary measure, set the PILOTCODE_API_KEY environment variable instead."
    )


def delete_api_key() -> bool:
    """Remove the stored API key from all backends.

    Returns:
        True if the key was deleted from at least one backend.
    """
    deleted = False
    if _keyring_delete():
        deleted = True
    if _encrypted_delete():
        deleted = True
    return deleted


def migrate_from_plaintext(plaintext_key: str) -> str | None:
    """One-shot migration: move a plaintext key into secure storage.

    Args:
        plaintext_key: The plaintext API key currently in settings.json.

    Returns:
        The storage backend used ("keyring" or "encrypted"), or None if
        the key is empty/None.
    """
    if not plaintext_key:
        return None
    return store_api_key(plaintext_key)


def is_secure_storage_available() -> bool:
    """Check if at least one secure storage backend is available."""
    return _KEYRING_AVAILABLE or _CRYPTO_AVAILABLE
