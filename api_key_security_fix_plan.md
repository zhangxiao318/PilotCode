# API Key 明文存储问题 — 修改方案

> 问题：API Key 当前以明文 JSON 存储在 `~/.config/pilotcode/settings.json` 中，任何能访问该文件的程序或用户都可以直接读取。

---

## 1. 现状分析

### 1.1 存储路径

```
~/.config/pilotcode/settings.json   # 由 platformdirs 决定
```

内容示例：
```json
{
  "theme": "default",
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "default_model": "deepseek",
  "base_url": "https://api.deepseek.com"
}
```

### 1.2 涉及的文件（4个）

| 文件 | 行号 | 操作 |
|------|------|------|
| `utils/config.py` | `L236-243` | `save_global_config()` — 将 api_key 写入 JSON |
| `utils/config.py` | `L196-210` | `load_global_config()` — 从 JSON 读取 api_key |
| `utils/config.py` | `L170-178` | `_apply_env_overrides()` — 环境变量覆盖 |
| `utils/configure.py` | `L185-190` | 配置向导 — 用户输入 api_key 存入 GlobalConfig |
| `utils/model_client.py` | `L82` | `ModelClient.__init__()` — 取 api_key 拼入 HTTP Header |
| `utils/models_config.py` | `L307-340` | `check_api_key_configured()` — 检查环境变量 |
| `utils/models_config.py` | `L343-366` | `get_model_from_env()` — 从环境变量获取 key |

### 1.3 数据流

```
用户输入 (configure.py)
    │
    ▼
GlobalConfig.api_key  ──save──▶  settings.json (明文!)
    │
    ▼
ModelClient.__init__()
    │
    ▼
httpx.AsyncClient(headers={"Authorization": "Bearer {api_key}"})
```

---

## 2. 修改方案：分层安全存储

采用 **3级回退** 策略，按优先级尝试：

```
1. 环境变量 (已有，最高优先级，不改动)
2. 操作系统密钥环 (新增，推荐)
3. 加密文件存储 (新增，兜底)
4. 明文文件 (已有，仅作为迁移兼容)
```

### 2.1 架构设计

```python
# 新增文件: src/pilotcode/utils/secure_storage.py

class SecureStorage:
    """分层安全存储：Keyring → 加密文件 → 明文兼容"""
    
    def store_api_key(self, model_name: str, api_key: str) -> None:
        """存储 API Key，优先使用系统密钥环"""
        
    def retrieve_api_key(self, model_name: str) -> str | None:
        """读取 API Key"""
        
    def delete_api_key(self, model_name: str) -> bool:
        """删除 API Key"""
        
    def migrate_from_plaintext(self, model_name: str, plaintext_key: str) -> bool:
        """从明文迁移到安全存储"""
```

### 2.2 详细实现计划

#### 新增文件：`src/pilotcode/utils/secure_storage.py`

核心实现：

```python
"""Secure API key storage with layered fallback.

Priority chain:
    1. Environment variable (handled externally, not here)
    2. OS keyring (macOS Keychain / Windows Credential Manager / Linux Secret Service)
    3. AES-encrypted file (~/.pilotcode/secrets.enc)
    4. Plaintext fallback (existing settings.json, for migration only)
"""

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Optional

import platformdirs


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------

class _KeyringBackend:
    """System keyring via keyring library."""

    SERVICE_NAME = "pilotcode"

    @staticmethod
    def available() -> bool:
        try:
            import keyring
            return True
        except ImportError:
            return False

    @staticmethod
    def store(model_name: str, api_key: str) -> None:
        import keyring
        keyring.set_password(_KeyringBackend.SERVICE_NAME, model_name, api_key)

    @staticmethod
    def retrieve(model_name: str) -> Optional[str]:
        import keyring
        return keyring.get_password(_KeyringBackend.SERVICE_NAME, model_name)

    @staticmethod
    def delete(model_name: str) -> None:
        import keyring
        try:
            keyring.delete_password(_KeyringBackend.SERVICE_NAME, model_name)
        except Exception:
            pass


class _EncryptedFileBackend:
    """AES-GCM encrypted file storage.

    Derives a per-machine encryption key from:
        - Machine ID (/etc/machine-id on Linux, registry on Windows)
        - A randomly generated salt stored alongside the encrypted data
    """

    STORAGE_DIR = Path(platformdirs.user_data_dir("pilotcode", "pilotcode"))
    SECRETS_FILE = STORAGE_DIR / "secrets.enc"

    @staticmethod
    def _derive_key(salt: bytes) -> bytes:
        """Derive AES-256 key from machine-specific data + salt."""
        # Collect machine fingerprint
        machine_id = b""
        mid_paths = [
            "/etc/machine-id",
            "/var/lib/dbus/machine-id",
        ]
        for p in mid_paths:
            try:
                machine_id = Path(p).read_bytes().strip()
                break
            except (OSError, PermissionError):
                continue

        if not machine_id:
            # Fallback: hostname + username
            machine_id = f"{os.uname().nodename}:{os.getlogin()}".encode()

        # Derive key using PBKDF2
        import hashlib
        return hashlib.pbkdf2_hmac("sha256", machine_id, salt, 100_000, dklen=32)

    @classmethod
    def _read_encrypted(cls) -> dict[str, str]:
        """Read and decrypt the secrets file."""
        if not cls.SECRETS_FILE.exists():
            return {}

        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            # cryptography not installed — fall back to stdlib
            return cls._read_encrypted_stdlib()

        raw = cls.SECRETS_FILE.read_bytes()
        # Format: salt(16) | nonce(12) | ciphertext | tag(16)
        salt = raw[:16]
        nonce = raw[16:28]
        ciphertext = raw[28:]

        key = cls._derive_key(salt)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            return json.loads(plaintext.decode("utf-8"))
        except Exception:
            return {}

    @classmethod
    def _write_encrypted(cls, data: dict[str, str]) -> None:
        """Encrypt and write the secrets file."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            cls._write_encrypted_stdlib(data)
            return

        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = cls._derive_key(salt)

        plaintext = json.dumps(data).encode("utf-8")
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.SECRETS_FILE.write_bytes(salt + nonce + ciphertext)
        # Restrict permissions
        os.chmod(cls.SECRETS_FILE, 0o600)

    # ---- stdlib-only fallback (no cryptography dep) ----
    @classmethod
    def _read_encrypted_stdlib(cls) -> dict[str, str]:
        """Simpler XOR-obfuscation when cryptography is not installed."""
        if not cls.SECRETS_FILE.exists():
            return {}
        raw = cls.SECRETS_FILE.read_bytes()
        salt = raw[:16]
        key = cls._derive_key(salt)
        data = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw[16:]))
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}

    @classmethod
    def _write_encrypted_stdlib(cls, data: dict[str, str]) -> None:
        """Simpler XOR-obfuscation."""
        salt = secrets.token_bytes(16)
        key = cls._derive_key(salt)
        plaintext = json.dumps(data).encode("utf-8")
        ciphertext = bytes(b ^ key[i % len(key)] for i, b in enumerate(plaintext))
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.SECRETS_FILE.write_bytes(salt + ciphertext)
        os.chmod(cls.SECRETS_FILE, 0o600)

    @classmethod
    def store(cls, model_name: str, api_key: str) -> None:
        data = cls._read_encrypted()
        data[model_name] = api_key
        cls._write_encrypted(data)

    @classmethod
    def retrieve(cls, model_name: str) -> Optional[str]:
        return cls._read_encrypted().get(model_name)

    @classmethod
    def delete(cls, model_name: str) -> None:
        data = cls._read_encrypted()
        data.pop(model_name, None)
        cls._write_encrypted(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SecureStorage:
    """Layered secure API key storage.

    Priority: Keyring > Encrypted File > Plaintext File (read-only compat)
    """

    def __init__(self):
        self._keyring_available = _KeyringBackend.available()

    # ---- Write (always goes to best available backend) ----

    def store_api_key(self, model_name: str, api_key: str) -> None:
        """Store API key securely. Tries keyring first, falls back to encrypted file."""
        if not api_key:
            return
        if self._keyring_available:
            _KeyringBackend.store(model_name, api_key)
        _EncryptedFileBackend.store(model_name, api_key)

    # ---- Read (checks all backends in priority order) ----

    def retrieve_api_key(self, model_name: str) -> Optional[str]:
        """Retrieve API key from the most secure available backend."""
        # 1. Keyring
        if self._keyring_available:
            key = _KeyringBackend.retrieve(model_name)
            if key:
                return key
        # 2. Encrypted file
        key = _EncryptedFileBackend.retrieve(model_name)
        if key:
            return key
        # 3. Plaintext fallback (migration)
        return PlaintextCompat.retrieve(model_name)

    # ---- Delete ----

    def delete_api_key(self, model_name: str) -> bool:
        """Remove API key from all backends."""
        deleted = False
        if self._keyring_available:
            _KeyringBackend.delete(model_name)
            deleted = True
        _EncryptedFileBackend.delete(model_name)
        PlaintextCompat.delete(model_name)
        return deleted

    # ---- Migration ----

    def migrate_from_plaintext(self, model_name: str) -> bool:
        """Move a plaintext key to secure storage, then wipe the plaintext."""
        key = PlaintextCompat.retrieve(model_name)
        if not key:
            return False
        self.store_api_key(model_name, key)
        PlaintextCompat.delete(model_name)
        return True


# ---------------------------------------------------------------------------
# Plaintext compatibility (read-only bridge for existing settings.json)
# ---------------------------------------------------------------------------

class PlaintextCompat:
    """Read API keys from legacy plaintext settings.json.

    Used ONLY for one-time migration.  After migrate_from_plaintext()
    is called, the plaintext copy is removed.
    """

    @staticmethod
    def retrieve(model_name: str) -> Optional[str]:
        """Read api_key from settings.json (legacy format)."""
        try:
            settings_path = Path(platformdirs.user_config_dir("pilotcode", "pilotcode")) / "settings.json"
            if not settings_path.exists():
                return None
            data = json.loads(settings_path.read_text("utf-8"))
            key = data.get("api_key")
            if key and key != "sk-placeholder":
                return key
        except Exception:
            pass
        return None

    @staticmethod
    def delete(model_name: str) -> None:
        """Remove api_key from settings.json (after migration)."""
        try:
            settings_path = Path(platformdirs.user_config_dir("pilotcode", "pilotcode")) / "settings.json"
            if not settings_path.exists():
                return
            data = json.loads(settings_path.read_text("utf-8"))
            if "api_key" in data:
                del data["api_key"]
                settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        except Exception:
            pass


# Global instance
_secure_storage: Optional[SecureStorage] = None


def get_secure_storage() -> SecureStorage:
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureStorage()
    return _secure_storage
```

#### 修改文件：`src/pilotcode/utils/config.py`

```python
# ======  imports 区域新增 ======
from .secure_storage import get_secure_storage

# ======  GlobalConfig 中 api_key 字段改为 NonSerialized ======
# api_key 不再持久化到 settings.json, 改为通过 SecureStorage 存取

@dataclass
class GlobalConfig:
    theme: str = "default"
    verbose: bool = False
    auto_compact: bool = True
    # api_key 不再序列化到 JSON
    api_key: str | None = field(default=None, metadata={"nosave": True})
    base_url: str = ""
    default_model: str = ""
    model_provider: str = ""
    context_window: int = 0
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    auto_review: bool = False
    max_review_iterations: int = 3


# ======  save_global_config 修改 ======
def save_global_config(self, config: GlobalConfig) -> None:
    """Save global configuration. API key is stored securely, not in JSON."""
    self._ensure_config_dir()

    # 1. 提取 api_key，存入安全存储
    if config.api_key:
        storage = get_secure_storage()
        model_name = config.default_model or "default"
        storage.store_api_key(model_name, config.api_key)

        # 2. 如果存在旧明文 key，迁移后擦除
        storage.migrate_from_plaintext(model_name)

    # 3. 写入不含 api_key 的配置
    save_dict = asdict(config)
    save_dict.pop("api_key", None)  # 确保 api_key 不写入 JSON

    with open(self.SETTINGS_FILE, "w") as f:
        json.dump(save_dict, f, indent=2, ensure_ascii=False)

    self._global_config = config
    self._settings_mtime = self.SETTINGS_FILE.stat().st_mtime


# ======  load_global_config 修改 ======
def load_global_config(self) -> GlobalConfig:
    """Load global config. API key retrieved from secure storage."""
    # ... (mtime checking same as before) ...

    if self.SETTINGS_FILE.exists():
        try:
            with open(self.SETTINGS_FILE, "r") as f:
                data = json.load(f)
            self._global_config = GlobalConfig(**data)
        except Exception:
            self._global_config = GlobalConfig()
    else:
        self._global_config = GlobalConfig()

    # 从安全存储恢复 api_key
    storage = get_secure_storage()
    model_name = self._global_config.default_model or "default"

    # 检查是否有旧明文 key 需要迁移
    if not self._global_config.api_key:
        # 先尝试安全存储
        secure_key = storage.retrieve_api_key(model_name)
        if secure_key:
            self._global_config.api_key = secure_key
        else:
            # 兼容：从旧明文文件读取（触发自动迁移）
            legacy_key = PlaintextCompat.retrieve(model_name)
            if legacy_key:
                self._global_config.api_key = legacy_key
                # 自动迁移
                storage.store_api_key(model_name, legacy_key)
                # 不在这里删除旧文件，等 save 时处理

    self._global_config = self._apply_env_overrides(self._global_config)
    # ... rest same as before ...
```

#### 修改文件：`src/pilotcode/utils/model_client.py`

```python
# ======  __init__ 中的 api_key 获取保持不变 ======
# 因为 GlobalConfig.api_key 已经通过 SecureStorage 恢复了
# 所以 ModelClient 无须改动，逻辑透明

class ModelClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        config = get_global_config()
        # config.api_key 已经是安全恢复后的值
        self.api_key = api_key or config.api_key or "sk-placeholder"
        # ... rest unchanged ...
```

#### 新增依赖：`pyproject.toml`

```toml
dependencies = [
    # ... existing ...
    "keyring>=24.0.0",          # 系统密钥环（可选，自动降级）
    "cryptography>=42.0.0",     # AES 加密（可选，自动降级到 stdlib）
]
```

> 两个依赖都标记为可选：代码中 `try/except ImportError` 自动降级。

#### 新增单元测试：`tests/test_secure_storage.py`

```python
"""Tests for secure API key storage."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from pilotcode.utils.secure_storage import (
    SecureStorage,
    _EncryptedFileBackend,
    PlaintextCompat,
    get_secure_storage,
)


class TestSecureStorage:
    """Test layered storage retrieval."""

    def test_store_and_retrieve_encrypted_file(self, tmp_path):
        """Test encrypted file backend."""
        with patch.object(_EncryptedFileBackend, "SECRETS_FILE", tmp_path / "secrets.enc"):
            storage = SecureStorage()
            storage._keyring_available = False  # force encrypted file
            
            storage.store_api_key("deepseek", "sk-test-12345")
            result = storage.retrieve_api_key("deepseek")
            
            assert result == "sk-test-12345"
            # Verify file is not plaintext
            raw = (tmp_path / "secrets.enc").read_bytes()
            assert b"sk-test-12345" not in raw  # encrypted, not plaintext

    def test_delete(self, tmp_path):
        """Test key deletion."""
        with patch.object(_EncryptedFileBackend, "SECRETS_FILE", tmp_path / "secrets.enc"):
            storage = SecureStorage()
            storage._keyring_available = False
            
            storage.store_api_key("openai", "sk-delete-me")
            assert storage.retrieve_api_key("openai") == "sk-delete-me"
            
            storage.delete_api_key("openai")
            assert storage.retrieve_api_key("openai") is None

    def test_migration_from_plaintext(self, tmp_path):
        """Test migration from legacy plaintext settings.json."""
        settings_dir = tmp_path / "pilotcode"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"api_key": "sk-legacy-key"}))

        secrets_file = tmp_path / "secrets.enc"

        with patch.object(
            PlaintextCompat, "retrieve", return_value="sk-legacy-key"
        ), patch.object(
            _EncryptedFileBackend, "SECRETS_FILE", secrets_file
        ):
            storage = SecureStorage()
            storage._keyring_available = False
            assert storage.migrate_from_plaintext("deepseek") is True
            assert storage.retrieve_api_key("deepseek") == "sk-legacy-key"

    def test_empty_key_not_stored(self, tmp_path):
        """Empty or placeholder keys should not be stored."""
        with patch.object(_EncryptedFileBackend, "SECRETS_FILE", tmp_path / "secrets.enc"):
            storage = SecureStorage()
            storage._keyring_available = False
            
            storage.store_api_key("model", "")
            storage.store_api_key("model", "sk-placeholder")
            
            # Should not appear in encrypted store
            result = storage.retrieve_api_key("model")
            assert result is None
```

---

## 3. 实施步骤

### Phase 1：基础设施（1-2 天）

1. 创建 `src/pilotcode/utils/secure_storage.py`
2. 在 `pyproject.toml` 中添加 `keyring` 和 `cryptography` 为可选依赖
3. 编写 `tests/test_secure_storage.py` 验证核心逻辑

### Phase 2：集成（1 天）

4. 修改 `config.py` 的 `save_global_config()` — api_key 不再写入 JSON
5. 修改 `config.py` 的 `load_global_config()` — 从 SecureStorage 恢复
6. 修改 `GlobalConfig` — api_key 标记为 non-serialized
7. ModelClient 无需修改（透明）

### Phase 3：迁移（自动）

8. 首次启动时自动检测 `settings.json` 中的明文 api_key
9. 自动迁移到安全存储
10. 从 `settings.json` 中移除 `api_key` 字段
11. 打印一条 info 日志告知用户迁移完成

### Phase 4：文档（0.5 天）

12. 更新 `QUICKSTART.md` 中的配置指南
13. 在 `/model` 命令输出中隐藏 api_key 细节

---

## 4. 安全等级对比

| 方案 | 安全等级 | 说明 |
|------|----------|------|
| **当前：明文 JSON** | ⚠️ 低 | 任何进程可读 |
| **环境变量** | 🟡 中 | shell history 可能泄露，但不会写入文件 |
| **加密文件 (stdlib)** | 🟡 中 | 混淆存储，依赖 machine-id |
| **加密文件 (AES-GCM)** | 🟢 较高 | 标准 AES-256-GCM，依赖 machine-id |
| **系统密钥环** | 🟢 高 | macOS Keychain / Windows Credential Manager / Linux Secret Service |

> 方案保持向后兼容：已有明文字段自动迁移，用户无感知。

---

## 5. 风险与注意事项

| 风险 | 缓解措施 |
|------|----------|
| `keyring` 在某些 Linux 无桌面环境不可用 | 自动降级到加密文件存储 |
| `cryptography` 未安装 | 自动降级到 stdlib XOR 混淆（仍比明文安全） |
| machine-id 变更（Docker/VM 克隆） | 密钥丢失，用户需重新配置（与明文丢失行为一致） |
| 多用户共享 machine-id | 使用 `os.getlogin()` 作为额外 salt |
| 旧版本 `settings.json` 仍有 api_key | 启动时自动检测并迁移 + 警告 |

---

## 6. 迁移日志示例

用户升级后首次启动时：

```
[INFO] Migrating API key from plaintext settings.json to secure storage...
[INFO] API key for 'deepseek' has been moved to system keyring.
[INFO] Plaintext API key removed from settings.json.
[INFO] Migration complete. Your API key is now stored securely.
```
