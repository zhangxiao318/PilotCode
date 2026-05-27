"""SQLite + FTS5 history search engine for context archives.

Replaces O(N) JSON file traversal with ~10ms FTS5 full-text search
over 10,000+ archived conversation entries.

Design:
- One SQLite database per project: `.pilotcode/context/history.db`
- Virtual table `history` using FTS5 for content + metadata
- `archive_compaction()` automatically indexes new archives
- `search(query, top_k)` returns ranked results with BM25 scoring
- `summarize_top_hits()` passes top results to a lightweight LLM for
  a concise summary suitable for injection into the current context.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class HistoryEntry:
    """A single indexed history entry."""

    archive_id: str
    entry_id: str
    timestamp: str
    message_type: str  # user | assistant | tool_result | summary
    content: str
    session_id: str = ""
    token_count: int = 0
    metadata_json: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_id": self.archive_id,
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "content": self.content,
            "session_id": self.session_id,
            "token_count": self.token_count,
            "metadata": json.loads(self.metadata_json) if self.metadata_json else {},
        }


@dataclass
class SearchResult:
    """Result from FTS5 search."""

    archive_id: str
    entry_id: str
    content: str
    message_type: str
    timestamp: str
    rank: float  # BM25 score (lower is better)
    metadata: dict[str, Any] = field(default_factory=dict)


class HistorySearchEngine:
    """SQLite + FTS5 search over archived conversation context."""

    DB_NAME = "history.db"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.cwd() / ".pilotcode" / "context"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / self.DB_NAME
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        """Create FTS5 virtual table and auxiliary tables if they don't exist."""
        conn = self._get_conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        # FTS5 virtual table for full-text search
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS history USING fts5(
                content,
                archive_id UNINDEXED,
                entry_id UNINDEXED,
                timestamp UNINDEXED,
                message_type UNINDEXED,
                session_id UNINDEXED,
                token_count UNINDEXED,
                metadata_json UNINDEXED,
                content='',
                content_rowid='rowid'
            )
            """)

        # Tracking table to avoid re-indexing same archive
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexed_archives (
                archive_id TEXT PRIMARY KEY,
                indexed_at REAL,
                entry_count INTEGER
            )
            """)

        # Index on archive_id for fast deletion/re-indexing
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_archive_id
            ON history(archive_id)
            """)

        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_archive(self, archive: dict[str, Any]) -> int:
        """Index a single archive (from context_archive.py format).

        Args:
            archive: Dict with keys archive_id, timestamp, entries, etc.

        Returns:
            Number of entries indexed.
        """
        archive_id = archive.get("archive_id", "")
        if not archive_id:
            return 0

        conn = self._get_conn()
        cursor = conn.cursor()

        # Check if already indexed
        cursor.execute(
            "SELECT 1 FROM indexed_archives WHERE archive_id = ?",
            (archive_id,),
        )
        if cursor.fetchone():
            return 0

        entries = archive.get("entries", [])
        if not entries:
            # Still mark as indexed so we don't keep checking
            conn.execute(
                "INSERT OR REPLACE INTO indexed_archives (archive_id, indexed_at, entry_count) VALUES (?, ?, ?)",
                (archive_id, time.time(), 0),
            )
            conn.commit()
            return 0

        session_id = archive.get("session_id", "")
        count = 0

        for entry in entries:
            content = entry.get("content", "")
            if not content or len(content) < 3:
                continue

            entry_id = entry.get("entry_id", f"{archive_id}_{count}")
            msg_type = entry.get("message_type", "unknown")
            timestamp = entry.get("timestamp", archive.get("timestamp", ""))
            token_count = entry.get("token_count", 0)
            metadata = entry.get("metadata", {})

            cursor.execute(
                """
                INSERT INTO history (content, archive_id, entry_id, timestamp, message_type, session_id, token_count, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content,
                    archive_id,
                    entry_id,
                    timestamp,
                    msg_type,
                    session_id,
                    token_count,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            count += 1

        # Mark as indexed
        conn.execute(
            "INSERT OR REPLACE INTO indexed_archives (archive_id, indexed_at, entry_count) VALUES (?, ?, ?)",
            (archive_id, time.time(), count),
        )
        conn.commit()
        return count

    def index_archive_file(self, archive_path: Path) -> int:
        """Index a single archive JSON file on disk."""
        try:
            data = json.loads(archive_path.read_text(encoding="utf-8"))
            return self.index_archive(data)
        except Exception:
            return 0

    def rebuild_index(self, archive_dir: Path | None = None) -> dict[str, Any]:
        """Rebuild the full index from all archive files on disk.

        Returns:
            Stats dict with total_entries, files_indexed, time_ms.
        """
        import time as time_mod

        start = time_mod.time()
        archive_dir = archive_dir or self.base_dir
        conn = self._get_conn()

        # Clear existing data
        conn.execute("DELETE FROM history")
        conn.execute("DELETE FROM indexed_archives")
        conn.commit()

        total_entries = 0
        files_indexed = 0

        for path in sorted(archive_dir.glob("compact_*.json")):
            count = self.index_archive_file(path)
            if count > 0:
                total_entries += count
                files_indexed += 1

        elapsed_ms = int((time_mod.time() - start) * 1000)
        return {
            "total_entries": total_entries,
            "files_indexed": files_indexed,
            "time_ms": elapsed_ms,
        }

    def is_archive_indexed(self, archive_id: str) -> bool:
        """Check whether a specific archive is already indexed."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM indexed_archives WHERE archive_id = ?",
            (archive_id,),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        message_types: list[str] | None = None,
        min_rank: float | None = None,
    ) -> list[SearchResult]:
        """Search archived history using FTS5 BM25 ranking.

        Args:
            query: Search query string.
            top_k: Maximum results to return.
            message_types: Optional filter by message type(s).
            min_rank: Optional minimum BM25 rank threshold.

        Returns:
            List of SearchResult sorted by relevance (best first).
        """
        conn = self._get_conn()

        # Build query
        # FTS5 MATCH syntax: plain terms are ANDed by default
        # We strip special chars that could break MATCH
        safe_query = self._sanitize_query(query)
        if not safe_query:
            return []

        sql = """
            SELECT archive_id, entry_id, content, message_type, timestamp, metadata_json, rank
            FROM history
            WHERE history MATCH ?
        """
        params: list[Any] = [safe_query]

        if message_types:
            placeholders = ",".join("?" for _ in message_types)
            sql += f" AND message_type IN ({placeholders})"
            params.extend(message_types)

        # BM25 ranking: lower is better
        sql += " ORDER BY rank"

        if min_rank is not None:
            sql += " LIMIT ?"
            params.append(top_k * 3)  # Fetch more for post-filter
        else:
            sql += " LIMIT ?"
            params.append(top_k)

        rows = conn.execute(sql, params).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            rank = row["rank"]
            if min_rank is not None and rank > min_rank:
                continue
            try:
                metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            except Exception:
                metadata = {}

            results.append(
                SearchResult(
                    archive_id=row["archive_id"],
                    entry_id=row["entry_id"],
                    content=row["content"],
                    message_type=row["message_type"],
                    timestamp=row["timestamp"],
                    rank=rank,
                    metadata=metadata,
                )
            )
            if len(results) >= top_k:
                break

        return results

    def search_by_archive(self, archive_id: str) -> list[SearchResult]:
        """Return all indexed entries for a specific archive."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT archive_id, entry_id, content, message_type, timestamp, metadata_json, rank
            FROM history
            WHERE archive_id = ?
            ORDER BY rowid
            """,
            (archive_id,),
        ).fetchall()

        results: list[SearchResult] = []
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            except Exception:
                metadata = {}
            results.append(
                SearchResult(
                    archive_id=row["archive_id"],
                    entry_id=row["entry_id"],
                    content=row["content"],
                    message_type=row["message_type"],
                    timestamp=row["timestamp"],
                    rank=row["rank"],
                    metadata=metadata,
                )
            )
        return results

    @staticmethod
    def _sanitize_query(query: str) -> str:
        """Sanitize a query for FTS5 MATCH.

        Removes characters that would break the MATCH syntax.
        """
        # Replace common problematic chars with spaces
        # FTS5 MATCH special chars: " * : ( ) { } [ ] ^ ~ - < > = !
        cleaned = re.sub(r'[\*"\:\(\)\{\}\[\]\^\~\<\>\=\!]', " ", query)
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    # ------------------------------------------------------------------
    # Summarization helper
    # ------------------------------------------------------------------

    async def summarize_top_hits(
        self,
        query: str,
        llm_client: Any,
        top_k: int = 5,
        max_chars: int = 1500,
    ) -> str:
        """Search history and summarize top hits into concise context.

        Args:
            query: The user's query to search for.
            llm_client: An object with an async `complete(prompt)` method.
            top_k: Number of hits to retrieve.
            max_chars: Maximum length of the returned summary.

        Returns:
            Concise summary string ready for context injection.
        """
        hits = self.search(query, top_k=top_k)
        if not hits:
            return ""

        parts: list[str] = []
        for h in hits:
            snippet = h.content[:300].replace("\n", " ")
            parts.append(f"[{h.message_type}] {snippet}")

        combined = "\n".join(parts)

        prompt = (
            f"The user is asking about: '{query}'\n\n"
            f"Here are relevant excerpts from past conversations:\n"
            f"{combined}\n\n"
            f"Summarize the key context in at most {max_chars} characters. "
            f"Focus only on facts, decisions, and errors relevant to the query. "
            f"Return plain text, no markdown formatting."
        )

        try:
            summary = await llm_client.complete(prompt)
            if summary and len(summary) > max_chars:
                summary = summary[:max_chars].rsplit(" ", 1)[0] + "..."
            return summary or ""
        except Exception:
            # Fallback: return raw concatenated snippets
            fallback = " | ".join(h.content[:200] for h in hits)
            if len(fallback) > max_chars:
                fallback = fallback[:max_chars].rsplit(" ", 1)[0] + "..."
            return fallback

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return index statistics."""
        conn = self._get_conn()
        total_entries = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        total_archives = conn.execute("SELECT COUNT(*) FROM indexed_archives").fetchone()[0]
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "total_entries": total_entries,
            "total_archives": total_archives,
            "db_size_bytes": db_size,
            "db_path": str(self.db_path),
        }

    def cleanup_old_entries(self, max_age_days: int = 30) -> int:
        """Remove indexed entries older than max_age_days.

        Returns:
            Number of entries removed.
        """
        import datetime

        cutoff = (datetime.datetime.now() - datetime.timedelta(days=max_age_days)).isoformat()
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM history WHERE timestamp < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_default_engine: HistorySearchEngine | None = None


def get_history_search_engine(base_dir: str | Path | None = None) -> HistorySearchEngine:
    """Get global history search engine instance."""
    global _default_engine
    if _default_engine is None:
        _default_engine = HistorySearchEngine(base_dir)
    return _default_engine


def reset_history_search_engine() -> None:
    """Reset global history search engine."""
    global _default_engine
    if _default_engine:
        _default_engine.close()
    _default_engine = None
