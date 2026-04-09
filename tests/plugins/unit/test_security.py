"""Unit tests for plugin security."""

import json
import tempfile
from pathlib import Path

import pytest


try:
    from pilotcode.plugins.security import (
        SignatureManager,
        PluginSignature,
        TrustStore,
        TrustLevel,
        PluginVerifier,
        VerificationStatus,
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


class TestPluginSignature:
    """Test PluginSignature."""
    
    def test_create_signature(self):
        """Test creating signature."""
        sig = PluginSignature(
            plugin_name="test-plugin",
            plugin_version="1.0.0",
            hash_algorithm="sha256",
            content_hash="abc123",
            signer="test-signer",
            timestamp="2024-01-01T00:00:00",
        )
        
        assert sig.plugin_name == "test-plugin"
        assert sig.hash_algorithm == "sha256"
    
    def test_to_dict(self):
        """Test conversion to dict."""
        sig = PluginSignature(
            plugin_name="test",
            plugin_version="1.0.0",
            hash_algorithm="sha256",
            content_hash="abc",
            signer="test",
            timestamp="2024-01-01",
        )
        
        data = sig.to_dict()
        
        assert data["plugin_name"] == "test"
        assert data["hash_algorithm"] == "sha256"
    
    def test_from_dict(self):
        """Test creation from dict."""
        data = {
            "plugin_name": "test",
            "plugin_version": "1.0.0",
            "hash_algorithm": "sha256",
            "content_hash": "abc",
            "signer": "test",
            "timestamp": "2024-01-01",
        }
        
        sig = PluginSignature.from_dict(data)
        
        assert sig.plugin_name == "test"
        assert sig.content_hash == "abc"
    
    def test_is_expired(self):
        """Test expiration check."""
        from datetime import datetime, timedelta
        
        # Not expired
        future = (datetime.now() + timedelta(days=1)).isoformat()
        sig = PluginSignature(
            plugin_name="test",
            plugin_version="1.0.0",
            hash_algorithm="sha256",
            content_hash="abc",
            signer="test",
            timestamp="2024-01-01",
            expires=future,
        )
        
        assert sig.is_expired() is False
        
        # Expired
        past = (datetime.now() - timedelta(days=1)).isoformat()
        sig.expires = past
        
        assert sig.is_expired() is True
    
    def test_get_signing_data(self):
        """Test getting data to sign."""
        sig = PluginSignature(
            plugin_name="test",
            plugin_version="1.0.0",
            hash_algorithm="sha256",
            content_hash="abc",
            signer="test",
            timestamp="2024-01-01",
        )
        
        data = sig.get_signing_data()
        
        assert "test" in data
        assert "abc" in data
        # Should not include signature field
        assert "signature" not in json.loads(data)


class TestSignatureManager:
    """Test SignatureManager."""
    
    def test_compute_hash(self, temp_config_dir):
        """Test computing content hash."""
        manager = SignatureManager(keys_dir=temp_config_dir)
        
        # Create test plugin
        plugin_dir = temp_config_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test"}')
        
        hash1 = manager.compute_hash(plugin_dir, "sha256")
        hash2 = manager.compute_hash(plugin_dir, "sha256")
        
        # Should be deterministic
        assert hash1 == hash2
        assert len(hash1) == 64  # sha256 hex length
    
    def test_create_and_verify_signature(self, temp_config_dir):
        """Test creating and verifying signature."""
        manager = SignatureManager(keys_dir=temp_config_dir)
        
        # Create test plugin
        plugin_dir = temp_config_dir / "test-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test"}')
        
        # Create signature
        sig = manager.create_signature(
            plugin_path=plugin_dir,
            plugin_name="test-plugin",
            plugin_version="1.0.0",
            signer="test",
            private_key="secret-key",
        )
        
        assert sig.signature is not None
        assert sig.content_hash is not None
        
        # Verify signature
        valid = manager.verify_signature(plugin_dir, sig, "secret-key")
        assert valid is True
        
        # Wrong key should fail
        invalid = manager.verify_signature(plugin_dir, sig, "wrong-key")
        assert invalid is False
    
    def test_save_and_load_signature(self, temp_config_dir):
        """Test saving and loading signature."""
        manager = SignatureManager(keys_dir=temp_config_dir)
        
        sig = PluginSignature(
            plugin_name="test",
            plugin_version="1.0.0",
            hash_algorithm="sha256",
            content_hash="abc",
            signer="test",
            timestamp="2024-01-01",
        )
        
        sig_path = temp_config_dir / ".signature.json"
        manager.save_signature(sig, sig_path)
        
        loaded = manager.load_signature(sig_path)
        
        assert loaded is not None
        assert loaded.plugin_name == "test"
    
    def test_load_nonexistent_signature(self, temp_config_dir):
        """Test loading signature that doesn't exist."""
        manager = SignatureManager(keys_dir=temp_config_dir)
        
        loaded = manager.load_signature(temp_config_dir / "nonexistent.json")
        
        assert loaded is None


class TestTrustStore:
    """Test TrustStore."""
    
    def test_create_trust_store(self, temp_config_dir):
        """Test creating trust store."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        assert store is not None
        # Should have default official entry
        assert "anthropics" in [p.publisher_id for p in store.list_publishers()]
    
    def test_get_publisher(self, temp_config_dir):
        """Test getting publisher."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        pub = store.get_publisher("anthropics")
        
        assert pub is not None
        assert pub.publisher_id == "anthropics"
        assert pub.trust_level == TrustLevel.OFFICIAL
    
    def test_get_or_create_publisher(self, temp_config_dir):
        """Test getting or creating publisher."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        # Create new
        pub = store.get_or_create("new-publisher", "New Publisher")
        
        assert pub.publisher_id == "new-publisher"
        assert pub.name == "New Publisher"
        assert pub.trust_level == TrustLevel.UNTRUSTED
    
    def test_set_trust_level(self, temp_config_dir):
        """Test setting trust level."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.set_trust_level("test-pub", TrustLevel.TRUSTED)
        
        pub = store.get_publisher("test-pub")
        assert pub.trust_level == TrustLevel.TRUSTED
    
    def test_block_publisher(self, temp_config_dir):
        """Test blocking publisher."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.block("bad-actor")
        
        pub = store.get_publisher("bad-actor")
        assert pub.trust_level == TrustLevel.BLOCKED
        assert pub.can_install() is False
    
    def test_trust_publisher(self, temp_config_dir):
        """Test trusting publisher."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.trust("good-dev")
        
        pub = store.get_publisher("good-dev")
        assert pub.trust_level == TrustLevel.TRUSTED
        assert pub.can_auto_update() is True
    
    def test_list_publishers_by_level(self, temp_config_dir):
        """Test listing publishers filtered by trust level."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.set_trust_level("pub1", TrustLevel.TRUSTED)
        store.set_trust_level("pub2", TrustLevel.TRUSTED)
        store.set_trust_level("pub3", TrustLevel.BLOCKED)
        
        trusted = store.list_publishers(TrustLevel.TRUSTED)
        
        assert len(trusted) == 2
    
    def test_is_blocked(self, temp_config_dir):
        """Test checking if publisher is blocked."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.block("blocked-pub")
        
        assert store.is_blocked("blocked-pub") is True
        assert store.is_blocked("unknown-pub") is False
    
    def test_add_public_key(self, temp_config_dir):
        """Test adding public key for publisher."""
        store = TrustStore(store_path=temp_config_dir / "trust.json")
        
        store.add_public_key("test-pub", "public-key-data", "fingerprint123")
        
        key = store.get_public_key("test-pub")
        
        assert key == "public-key-data"


class TestPluginVerifier:
    """Test PluginVerifier."""
    
    def test_verify_unsigned_plugin(self, temp_config_dir):
        """Test verifying unsigned plugin."""
        verifier = PluginVerifier()
        
        # Create unsigned plugin
        plugin_dir = temp_config_dir / "unsigned"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "unsigned"}')
        
        result = verifier.verify(plugin_dir)
        
        assert result.status == VerificationStatus.UNVERIFIED
        assert result.can_install is True
    
    def test_verify_with_missing_signature_required(self, temp_config_dir):
        """Test verifying when signature is required."""
        verifier = PluginVerifier()
        verifier.set_policy(require_signature=True)
        
        plugin_dir = temp_config_dir / "unsigned"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "unsigned"}')
        
        result = verifier.verify(plugin_dir)
        
        assert result.status == VerificationStatus.INVALID
        assert result.can_install is False
    
    def test_quick_check(self, temp_config_dir):
        """Test quick verification check."""
        verifier = PluginVerifier()
        
        plugin_dir = temp_config_dir / "test"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test"}')
        
        can_install, message = verifier.quick_check(plugin_dir)
        
        assert can_install is True
        # Message should indicate the security status
        assert any(word in message.lower() for word in ["unverified", "verified", "not signed", "caution"])
