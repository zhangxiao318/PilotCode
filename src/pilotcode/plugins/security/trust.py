"""Trust store for plugin publishers.

Manages trust levels for plugin publishers and sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class TrustLevel(Enum):
    """Trust levels for publishers."""
    BLOCKED = "blocked"      # Explicitly blocked
    UNTRUSTED = "untrusted"  # Unknown/unverified
    VERIFIED = "verified"    # Verified identity
    TRUSTED = "trusted"      # Explicitly trusted
    OFFICIAL = "official"    # Official/curated


@dataclass
class PublisherTrust:
    """Trust information for a publisher."""
    publisher_id: str
    name: str
    trust_level: TrustLevel
    public_key: Optional[str] = None
    fingerprint: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    verified_by: Optional[str] = None  # Who verified this publisher
    notes: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "publisher_id": self.publisher_id,
            "name": self.name,
            "trust_level": self.trust_level.value,
            "public_key": self.public_key,
            "fingerprint": self.fingerprint,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "verified_by": self.verified_by,
            "notes": self.notes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PublisherTrust":
        return cls(
            publisher_id=data["publisher_id"],
            name=data["name"],
            trust_level=TrustLevel(data.get("trust_level", "untrusted")),
            public_key=data.get("public_key"),
            fingerprint=data.get("fingerprint"),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
            verified_by=data.get("verified_by"),
            notes=data.get("notes"),
        )
    
    def can_install(self) -> bool:
        """Check if plugins from this publisher can be installed."""
        return self.trust_level not in (TrustLevel.BLOCKED,)
    
    def can_auto_update(self) -> bool:
        """Check if auto-updates are allowed."""
        return self.trust_level in (
            TrustLevel.TRUSTED,
            TrustLevel.OFFICIAL,
        )


class TrustStore:
    """Store of trusted publishers.
    
    Manages trust levels for plugin publishers and provides
    trust decisions for plugin operations.
    """
    
    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = store_path or (
            Path.home() / ".config" / "pilotcode" / "trust_store.json"
        )
        self._publishers: dict[str, PublisherTrust] = {}
        self._load()
    
    def _load(self) -> None:
        """Load trust store from disk."""
        if not self.store_path.exists():
            # Create default trust store with official marketplace
            self._publishers["anthropics"] = PublisherTrust(
                publisher_id="anthropics",
                name="Anthropic",
                trust_level=TrustLevel.OFFICIAL,
                verified_by="system",
                first_seen=datetime.now().isoformat(),
            )
            self._save()
            return
        
        try:
            with open(self.store_path, "r") as f:
                data = json.load(f)
            
            for pub_data in data.get("publishers", []):
                pub = PublisherTrust.from_dict(pub_data)
                self._publishers[pub.publisher_id] = pub
        except (json.JSONDecodeError, KeyError):
            pass
    
    def _save(self) -> None:
        """Save trust store to disk."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "publishers": [p.to_dict() for p in self._publishers.values()],
            "updated": datetime.now().isoformat(),
        }
        with open(self.store_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_publisher(self, publisher_id: str) -> Optional[PublisherTrust]:
        """Get trust info for a publisher."""
        return self._publishers.get(publisher_id)
    
    def get_or_create(
        self,
        publisher_id: str,
        name: Optional[str] = None,
    ) -> PublisherTrust:
        """Get or create publisher trust entry."""
        if publisher_id in self._publishers:
            return self._publishers[publisher_id]
        
        pub = PublisherTrust(
            publisher_id=publisher_id,
            name=name or publisher_id,
            trust_level=TrustLevel.UNTRUSTED,
            first_seen=datetime.now().isoformat(),
        )
        self._publishers[publisher_id] = pub
        self._save()
        return pub
    
    def set_trust_level(
        self,
        publisher_id: str,
        level: TrustLevel,
        verified_by: Optional[str] = None,
    ) -> None:
        """Set trust level for a publisher."""
        pub = self.get_or_create(publisher_id)
        pub.trust_level = level
        pub.last_seen = datetime.now().isoformat()
        if verified_by:
            pub.verified_by = verified_by
        self._save()
    
    def block(self, publisher_id: str) -> None:
        """Block a publisher."""
        self.set_trust_level(publisher_id, TrustLevel.BLOCKED)
    
    def trust(self, publisher_id: str, verified_by: Optional[str] = None) -> None:
        """Trust a publisher."""
        self.set_trust_level(publisher_id, TrustLevel.TRUSTED, verified_by)
    
    def verify(self, publisher_id: str, verified_by: str) -> None:
        """Mark publisher as verified."""
        self.set_trust_level(publisher_id, TrustLevel.VERIFIED, verified_by)
    
    def list_publishers(
        self,
        trust_level: Optional[TrustLevel] = None,
    ) -> list[PublisherTrust]:
        """List publishers, optionally filtered by trust level."""
        pubs = list(self._publishers.values())
        if trust_level:
            pubs = [p for p in pubs if p.trust_level == trust_level]
        return pubs
    
    def can_install(self, publisher_id: str) -> bool:
        """Check if can install from publisher."""
        pub = self.get_publisher(publisher_id)
        if not pub:
            # Unknown publisher - use default policy
            return True
        return pub.can_install()
    
    def can_auto_update(self, publisher_id: str) -> bool:
        """Check if auto-updates allowed for publisher."""
        pub = self.get_publisher(publisher_id)
        if not pub:
            return False
        return pub.can_auto_update()
    
    def get_trust_level(self, publisher_id: str) -> TrustLevel:
        """Get trust level for publisher."""
        pub = self.get_publisher(publisher_id)
        if not pub:
            return TrustLevel.UNTRUSTED
        return pub.trust_level
    
    def is_blocked(self, publisher_id: str) -> bool:
        """Check if publisher is blocked."""
        return self.get_trust_level(publisher_id) == TrustLevel.BLOCKED
    
    def add_public_key(
        self,
        publisher_id: str,
        public_key: str,
        fingerprint: Optional[str] = None,
    ) -> None:
        """Add public key for a publisher."""
        pub = self.get_or_create(publisher_id)
        pub.public_key = public_key
        pub.fingerprint = fingerprint
        pub.last_seen = datetime.now().isoformat()
        self._save()
    
    def get_public_key(self, publisher_id: str) -> Optional[str]:
        """Get public key for a publisher."""
        pub = self.get_publisher(publisher_id)
        if pub:
            return pub.public_key
        return None


# Global instance
_trust_store: Optional[TrustStore] = None


def get_trust_store() -> TrustStore:
    """Get global trust store."""
    global _trust_store
    if _trust_store is None:
        _trust_store = TrustStore()
    return _trust_store
