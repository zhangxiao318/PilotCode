"""Plugin signature management.

Handles signing and verification of plugin packages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class PluginSignature:
    """Plugin signature data."""
    plugin_name: str
    plugin_version: str
    hash_algorithm: str  # sha256, sha512
    content_hash: str
    signer: str  # Key ID or entity name
    timestamp: str
    expires: Optional[str] = None
    signature: str = ""  # Base64 encoded signature
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "hash_algorithm": self.hash_algorithm,
            "content_hash": self.content_hash,
            "signer": self.signer,
            "timestamp": self.timestamp,
            "expires": self.expires,
            "signature": self.signature,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PluginSignature":
        """Create from dictionary."""
        return cls(
            plugin_name=data["plugin_name"],
            plugin_version=data["plugin_version"],
            hash_algorithm=data["hash_algorithm"],
            content_hash=data["content_hash"],
            signer=data["signer"],
            timestamp=data["timestamp"],
            expires=data.get("expires"),
            signature=data.get("signature", ""),
        )
    
    def is_expired(self) -> bool:
        """Check if signature has expired."""
        if not self.expires:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires)
            return datetime.now() > expiry
        except ValueError:
            return True
    
    def get_signing_data(self) -> str:
        """Get the data that should be signed (excluding signature field)."""
        data = {
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "hash_algorithm": self.hash_algorithm,
            "content_hash": self.content_hash,
            "signer": self.signer,
            "timestamp": self.timestamp,
            "expires": self.expires,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))


class SignatureManager:
    """Manages plugin signatures.
    
    Provides methods for:
    - Computing content hashes
    - Creating signatures (for plugin authors)
    - Verifying signatures
    - Managing keys
    """
    
    def __init__(self, keys_dir: Optional[Path] = None):
        self.keys_dir = keys_dir or (Path.home() / ".config" / "pilotcode" / "keys")
        self.keys_dir.mkdir(parents=True, exist_ok=True)
    
    def compute_hash(self, plugin_path: Path, algorithm: str = "sha256") -> str:
        """Compute hash of plugin directory contents.
        
        Creates a deterministic hash of all files in the plugin directory.
        
        Args:
            plugin_path: Path to plugin directory
            algorithm: Hash algorithm (sha256, sha512)
            
        Returns:
            Hex digest of content hash
        """
        hasher = hashlib.new(algorithm)
        
        # Get all files sorted for determinism
        files = sorted(plugin_path.rglob("*"))
        
        for file_path in files:
            if file_path.is_file():
                # Add relative path
                rel_path = file_path.relative_to(plugin_path).as_posix()
                hasher.update(rel_path.encode())
                hasher.update(b"\x00")
                
                # Add file content
                try:
                    with open(file_path, "rb") as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                    hasher.update(b"\x00\x00")
                except IOError:
                    pass
        
        return hasher.hexdigest()
    
    def create_signature(
        self,
        plugin_path: Path,
        plugin_name: str,
        plugin_version: str,
        signer: str,
        private_key: str,  # PEM format or HMAC secret
        expires_days: Optional[int] = None,
        algorithm: str = "sha256",
    ) -> PluginSignature:
        """Create a signature for a plugin.
        
        Args:
            plugin_path: Path to plugin directory
            plugin_name: Plugin name
            plugin_version: Plugin version
            signer: Signer identifier
            private_key: Private key or secret
            expires_days: Days until expiration
            algorithm: Hash algorithm
            
        Returns:
            PluginSignature
        """
        # Compute content hash
        content_hash = self.compute_hash(plugin_path, algorithm)
        
        # Create signature object
        timestamp = datetime.now().isoformat()
        expires = None
        if expires_days:
            expires = (datetime.now() + timedelta(days=expires_days)).isoformat()
        
        sig = PluginSignature(
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            hash_algorithm=algorithm,
            content_hash=content_hash,
            signer=signer,
            timestamp=timestamp,
            expires=expires,
        )
        
        # Sign the data
        signing_data = sig.get_signing_data()
        signature = self._sign_data(signing_data, private_key)
        sig.signature = signature
        
        return sig
    
    def verify_signature(
        self,
        plugin_path: Path,
        signature: PluginSignature,
        public_key: str,
    ) -> bool:
        """Verify a plugin signature.
        
        Args:
            plugin_path: Path to installed plugin
            signature: Signature to verify
            public_key: Public key or secret
            
        Returns:
            True if valid
        """
        # Check expiration
        if signature.is_expired():
            return False
        
        # Recompute content hash
        current_hash = self.compute_hash(plugin_path, signature.hash_algorithm)
        if current_hash != signature.content_hash:
            return False
        
        # Verify cryptographic signature
        signing_data = signature.get_signing_data()
        return self._verify_signature(signing_data, signature.signature, public_key)
    
    def _sign_data(self, data: str, key: str) -> str:
        """Sign data with key.
        
        This is a simplified implementation using HMAC.
        For production, use proper asymmetric cryptography.
        """
        import hmac
        import base64
        
        signature = hmac.new(
            key.encode(),
            data.encode(),
            hashlib.sha256,
        ).digest()
        
        return base64.b64encode(signature).decode()
    
    def _verify_signature(self, data: str, signature: str, key: str) -> bool:
        """Verify signature."""
        import hmac
        import base64
        
        expected = self._sign_data(data, key)
        return hmac.compare_digest(expected, signature)
    
    def save_signature(self, signature: PluginSignature, path: Path) -> None:
        """Save signature to file."""
        sig_data = signature.to_dict()
        with open(path, "w") as f:
            json.dump(sig_data, f, indent=2)
    
    def load_signature(self, path: Path) -> Optional[PluginSignature]:
        """Load signature from file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return PluginSignature.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError, KeyError):
            return None
    
    def generate_key_pair(self, key_id: str) -> tuple[str, str]:
        """Generate a new key pair.
        
        Returns:
            Tuple of (private_key, public_key)
            
        Note: This is a simplified implementation.
        For production, use proper RSA/Ed25519 key generation.
        """
        import secrets
        
        # Generate random keys (simplified)
        private_key = secrets.token_hex(32)
        public_key = private_key  # In real implementation, derive public key
        
        # Save keys
        key_file = self.keys_dir / f"{key_id}.json"
        key_data = {
            "key_id": key_id,
            "private_key": private_key,
            "public_key": public_key,
            "created": datetime.now().isoformat(),
        }
        with open(key_file, "w") as f:
            json.dump(key_data, f, indent=2)
        
        return private_key, public_key
    
    def load_key(self, key_id: str) -> Optional[tuple[str, str]]:
        """Load a key pair."""
        key_file = self.keys_dir / f"{key_id}.json"
        try:
            with open(key_file, "r") as f:
                data = json.load(f)
            return data["private_key"], data["public_key"]
        except (FileNotFoundError, KeyError):
            return None


class SignatureError(Exception):
    """Signature-related error."""
    pass
