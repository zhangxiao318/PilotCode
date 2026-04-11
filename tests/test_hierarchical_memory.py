"""Tests for hierarchical memory module."""

import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch

from pilotcode.services.hierarchical_memory import (
    KnowledgeFragment,
    EpisodeSummary,
    WorkingMemory,
    EpisodicMemory,
    SemanticMemory,
    MemorySnapshotGenerator,
    HierarchicalMemory,
    get_hierarchical_memory,
    reset_hierarchical_memory,
)
from pilotcode.services.context_manager import ContextMessage


class TestKnowledgeFragment:
    """Tests for KnowledgeFragment."""

    def test_access_updates_count(self):
        fragment = KnowledgeFragment(key="test", value="value")
        
        time.sleep(0.01)  # Ensure time difference
        fragment.access()

        assert fragment.access_count == 1
        assert fragment.last_accessed >= fragment.created_at

    def test_to_dict(self):
        fragment = KnowledgeFragment(
            key="test",
            value="value",
            source_episodes=["ep1"],
            confidence=0.9,
        )

        d = fragment.to_dict()

        assert d["key"] == "test"
        assert d["value"] == "value"
        assert d["confidence"] == 0.9

    def test_from_dict(self):
        data = {
            "key": "test",
            "value": "value",
            "source_episodes": ["ep1"],
            "confidence": 0.9,
            "created_at": time.time(),
            "access_count": 5,
            "last_accessed": time.time(),
        }

        fragment = KnowledgeFragment.from_dict(data)

        assert fragment.key == "test"
        assert fragment.access_count == 5


class TestEpisodeSummary:
    """Tests for EpisodeSummary."""

    def test_to_context_string(self):
        summary = EpisodeSummary(
            episode_id="ep1",
            started_at=time.time(),
            ended_at=time.time(),
            primary_request="Implement login",
            solutions_implemented=["Created auth.py", "Added JWT middleware"],
            files_modified=["src/auth.py"],
            key_technical_concepts=["JWT", "Authentication"],
        )

        text = summary.to_context_string()

        assert "Implement login" in text
        assert "auth.py" in text
        assert "JWT" in text

    def test_to_dict(self):
        summary = EpisodeSummary(
            episode_id="ep1",
            started_at=time.time(),
            ended_at=time.time(),
            primary_request="Test",
        )

        d = summary.to_dict()

        assert d["episode_id"] == "ep1"
        assert d["primary_request"] == "Test"

    def test_from_dict(self):
        data = {
            "episode_id": "ep1",
            "started_at": time.time(),
            "ended_at": time.time(),
            "primary_request": "Test",
            "solutions_implemented": ["Solution 1"],
        }

        summary = EpisodeSummary.from_dict(data)

        assert summary.episode_id == "ep1"
        assert summary.solutions_implemented == ["Solution 1"]


class TestWorkingMemory:
    """Tests for WorkingMemory."""

    def test_add_and_get(self):
        wm = WorkingMemory()
        msg = ContextMessage(role="user", content="Hello")

        wm.add(msg)

        assert len(wm.messages) == 1

    def test_get_recent(self):
        wm = WorkingMemory()

        for i in range(5):
            wm.add(ContextMessage(role="user", content=f"Msg {i}"))

        recent = wm.get_recent(3)

        assert len(recent) == 3
        assert recent[0].content == "Msg 2"

    def test_estimate_tokens(self):
        wm = WorkingMemory()
        wm.add(ContextMessage(role="user", content="A" * 400))  # ~100 tokens

        tokens = wm.estimate_tokens()

        assert tokens > 0


class TestEpisodicMemory:
    """Tests for EpisodicMemory."""

    def test_add_episode(self):
        em = EpisodicMemory()
        episode = EpisodeSummary(
            episode_id="ep1",
            started_at=time.time(),
            ended_at=time.time(),
        )

        em.add_episode(episode)

        assert len(em.episodes) == 1

    def test_prune_old_episodes(self):
        em = EpisodicMemory(max_episodes=3)

        for i in range(5):
            em.add_episode(
                EpisodeSummary(
                    episode_id=f"ep{i}",
                    started_at=time.time(),
                    ended_at=time.time(),
                    predicted_utility=i * 0.2,
                )
            )

        assert len(em.episodes) == 3

    def test_retrieve_relevant(self):
        em = EpisodicMemory()

        em.add_episode(
            EpisodeSummary(
                episode_id="ep1",
                started_at=time.time(),
                ended_at=time.time(),
                primary_request="Implement login",
                files_modified=["auth.py"],
                predicted_utility=0.9,
            )
        )

        em.add_episode(
            EpisodeSummary(
                episode_id="ep2",
                started_at=time.time(),
                ended_at=time.time(),
                primary_request="Fix database",
                files_modified=["models.py"],
                predicted_utility=0.5,
            )
        )

        results = em.retrieve_relevant("login authentication", top_k=1)

        assert len(results) == 1
        assert results[0].episode_id == "ep1"

    def test_record_usage(self):
        em = EpisodicMemory()
        em.add_episode(
            EpisodeSummary(
                episode_id="ep1",
                started_at=time.time(),
                ended_at=time.time(),
            )
        )

        em.record_usage("ep1")

        assert em.episodes[0].actual_usage_count == 1

    def test_update_utility(self):
        em = EpisodicMemory()
        em.add_episode(
            EpisodeSummary(
                episode_id="ep1",
                started_at=time.time(),
                ended_at=time.time(),
                predicted_utility=0.5,
            )
        )

        em.update_utility("ep1", success=True)

        assert em.episodes[0].predicted_utility > 0.5


class TestSemanticMemory:
    """Tests for SemanticMemory."""

    def test_add_knowledge(self):
        sm = SemanticMemory()

        sm.add_knowledge("key1", "value1", "ep1", 0.9)

        assert "key1" in sm.knowledge
        assert sm.knowledge["key1"].value == "value1"

    def test_update_existing_knowledge(self):
        sm = SemanticMemory()

        sm.add_knowledge("key1", "value1", "ep1", 0.5)
        sm.add_knowledge("key1", "value2", "ep2", 0.9)

        assert sm.knowledge["key1"].value == "value2"
        assert sm.knowledge["key1"].confidence == 0.9

    def test_get_knowledge(self):
        sm = SemanticMemory()
        sm.add_knowledge("key1", "value1")

        value = sm.get_knowledge("key1")

        assert value == "value1"
        assert sm.knowledge["key1"].access_count == 1

    def test_query_knowledge(self):
        sm = SemanticMemory()
        sm.add_knowledge("file:auth.py", "Auth file", confidence=0.9)
        sm.add_knowledge("file:user.py", "User file", confidence=0.7)

        results = sm.query_knowledge("auth")

        assert len(results) == 1
        assert results[0][0] == "file:auth.py"

    def test_consolidate_removes_low_confidence(self):
        sm = SemanticMemory()
        sm.add_knowledge("key1", "value1", confidence=0.2)
        sm.add_knowledge("key2", "value2", confidence=0.9)

        sm.consolidate()

        assert "key1" not in sm.knowledge
        assert "key2" in sm.knowledge


class TestMemorySnapshotGenerator:
    """Tests for MemorySnapshotGenerator."""

    def test_generate_snapshot_basic(self):
        gen = MemorySnapshotGenerator()

        messages = [
            ContextMessage(role="user", content="Implement login"),
            ContextMessage(role="assistant", content="I'll create auth.py"),
        ]

        snapshot = gen.generate_snapshot(messages, "ep1")

        assert snapshot.episode_id == "ep1"
        assert snapshot.primary_request == "Implement login"
        assert snapshot.original_message_count == 2

    def test_extract_technical_concepts(self):
        gen = MemorySnapshotGenerator()

        content = """
        def create_user():
            from models import User
            return User()
        """
        concepts = gen._extract_technical_concepts(content)

        assert "create_user" in concepts
        assert "models" in concepts

    def test_extract_file_paths(self):
        gen = MemorySnapshotGenerator()

        content = "Check src/models/user.py and tests/test_user.py"
        files = gen._extract_file_paths(content)

        assert len(files) > 0

    def test_extract_decisions(self):
        gen = MemorySnapshotGenerator()

        content = "I will use JWT for authentication. We should implement middleware."
        decisions = gen._extract_decisions(content)

        assert len(decisions) >= 1

    def test_extract_solutions(self):
        gen = MemorySnapshotGenerator()

        content = "I have created the auth.py file. Fixed the login bug."
        solutions = gen._extract_solutions(content)

        assert len(solutions) >= 1

    def test_estimate_utility(self):
        gen = MemorySnapshotGenerator()

        messages = [
            ContextMessage(role="user", content="Implement login"),
            ContextMessage(role="assistant", content="Done"),
        ]

        summary = EpisodeSummary(
            episode_id="ep1",
            started_at=time.time(),
            ended_at=time.time(),
            solutions_implemented=["Created auth.py"],
            files_modified=["src/auth.py"],
        )

        utility = gen._estimate_utility(messages, summary)

        assert utility >= 0.4  # Should be reasonably high with solutions


class TestHierarchicalMemory:
    """Tests for HierarchicalMemory."""

    def test_start_and_end_episode(self):
        hm = HierarchicalMemory()

        hm.start_episode()
        hm.add_to_working(ContextMessage(role="user", content="Test"))

        snapshot = hm.end_episode()

        assert isinstance(snapshot, EpisodeSummary)
        assert len(hm.working.messages) == 0  # Cleared

    def test_retrieve_context(self):
        hm = HierarchicalMemory()

        hm.start_episode()
        hm.add_to_working(ContextMessage(role="user", content="Test message"))
        hm.end_episode()

        context = hm.retrieve_context("Test", include_episodes=1)

        assert "episodic_memories" in context
        assert len(context["episodic_memories"]) == 1

    def test_format_context_for_prompt(self):
        hm = HierarchicalMemory()

        hm.start_episode()
        hm.add_to_working(ContextMessage(role="user", content="Implement login"))
        hm.end_episode()

        retrieved = hm.retrieve_context("login")
        formatted = hm.format_context_for_prompt(retrieved)

        assert "Implement login" in formatted

    def test_feedback_episode_utility(self):
        hm = HierarchicalMemory()

        hm.start_episode()
        hm.add_to_working(ContextMessage(role="user", content="Test"))
        snapshot = hm.end_episode()

        original_utility = snapshot.predicted_utility
        hm.feedback_episode_utility(snapshot.episode_id, success=True)

        updated = hm.episodic.episodes[0]
        assert updated.predicted_utility > original_utility

    def test_get_stats(self):
        hm = HierarchicalMemory()

        hm.start_episode()
        hm.add_to_working(ContextMessage(role="user", content="Test"))
        hm.end_episode()

        stats = hm.get_stats()

        assert "working_memory" in stats
        assert "episodic_memory" in stats
        assert "semantic_memory" in stats

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            storage_path = f.name

        try:
            # Create and save
            hm1 = HierarchicalMemory(storage_path=storage_path)
            hm1.start_episode()
            hm1.add_to_working(ContextMessage(role="user", content="Test"))
            hm1.end_episode()

            # Load in new instance
            hm2 = HierarchicalMemory(storage_path=storage_path)
            assert len(hm2.episodic.episodes) == 1
        finally:
            os.unlink(storage_path)


class TestGlobalHierarchicalMemory:
    """Tests for global hierarchical memory."""

    def test_singleton(self):
        reset_hierarchical_memory()

        h1 = get_hierarchical_memory()
        h2 = get_hierarchical_memory()

        assert h1 is h2

        reset_hierarchical_memory()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
