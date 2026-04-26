"""Tests for Knowhow library."""

import tempfile
from pathlib import Path

from pilotcode.services.knowhow import (
    KnowhowLibrary,
    KnowhowEntry,
    KnowhowMatch,
    get_knowhow_library,
    clear_knowhow_cache,
    model_slug,
    init_knowhow_for_model,
    _BUILTIN_KNOWHOW,
    QWEN3_CODER_30B_STARTER_ENTRIES,
)

_ALL_TEST_ENTRIES = _BUILTIN_KNOWHOW + QWEN3_CODER_30B_STARTER_ENTRIES


class TestKnowhowDetection:
    """Test detection of known weak-model patterns."""

    def test_detect_double_escaped_newline(self):
        source = 'x = "hello\\\\nworld"\n'
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        assert len(matches) == 1
        assert matches[0].entry_id == "py-string-escape-double-n"
        assert matches[0].line_number == 1
        assert "\\\\n" in matches[0].matched_text

    def test_detect_double_escaped_tab(self):
        source = "x = 'a\\\\tb'\n"
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        assert len(matches) == 1
        assert matches[0].entry_id == "py-string-escape-double-t"

    def test_detect_double_escaped_quote(self):
        source = 'x = "say \\\\"hello\\""\n'
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        # Should match double-escaped quote
        quote_matches = [m for m in matches if m.entry_id == "py-string-escape-double-quote"]
        assert len(quote_matches) == 1

    def test_no_false_positive_single_escape(self):
        source = 'x = "hello\\nworld"\n'
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        # Single \n should NOT match
        assert len(matches) == 0

    def test_applies_to_glob_filter(self):
        source = 'x = "hello\\\\nworld"\n'
        lib = KnowhowLibrary()
        matches_js = lib.check(source, "test.js")
        assert len(matches_js) == 0  # Python rules don't apply to .js

    def test_mixed_indentation(self):
        source = "def foo():\n\t    pass\n"
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        mixed = [m for m in matches if m.entry_id == "py-mixed-indentation"]
        assert len(mixed) == 1


class TestKnowhowAutoFix:
    """Test auto-fix application."""

    def test_fix_double_escaped_newline(self):
        source = 'x = "hello\\\\nworld"\n'
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        fixed = lib.apply_auto_fixes(source, matches)
        assert 'x = "hello\\nworld"' in fixed
        assert "\\\\n" not in fixed

    def test_fix_multiple_issues(self):
        source = 'x = "a\\\\nb\\\\tc"\n'
        lib = KnowhowLibrary()
        matches = lib.check(source, "test.py")
        fixed = lib.apply_auto_fixes(source, matches)
        assert "\\\\n" not in fixed
        assert "\\\\t" not in fixed
        assert "\\n" in fixed
        assert "\\t" in fixed

    def test_fix_on_real_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('def hello():\n    return "hi\\\\nthere"\n')
            path = f.name

        try:
            lib = KnowhowLibrary()
            matches = lib.check_file(path)
            assert len(matches) == 1
            assert matches[0].entry_id == "py-string-escape-double-n"

            source = Path(path).read_text()
            fixed = lib.apply_auto_fixes(source, matches)
            assert "\\\\n" not in fixed
            assert "\\n" in fixed
        finally:
            Path(path).unlink()


class TestKnowhowLibraryStats:
    """Test library metadata."""

    def test_builtin_rules_loaded(self):
        # With no model name, returns empty library (skip detection)
        lib = get_knowhow_library(None)
        stats = lib.get_stats()
        assert stats["total_rules"] == 7
        assert stats["has_model_file"] is True

    def test_add_custom_rule(self):
        lib = KnowhowLibrary()
        lib.add(
            KnowhowEntry(
                id="custom-test",
                name="Test rule",
                description="A test rule",
                pattern="foobar",
                pattern_type="literal",
                severity="warning",
            )
        )
        matches = lib.check("x = foobar\n", "test.py")
        assert len(matches) == 1
        assert matches[0].name == "Test rule"


class TestKnowhowLibraryForModel:
    """Test per-model library loading."""

    def test_no_model_file_returns_empty(self, monkeypatch, tmp_path):
        """If no model-specific JSON exists, check() returns [] (skipped)."""
        monkeypatch.setattr("pilotcode.services.knowhow._get_knowhow_dir", lambda: tmp_path)
        clear_knowhow_cache()

        lib = KnowhowLibrary.for_model("unprofiled-model")
        assert not lib._has_model_file
        assert lib.check("x = 1\n", "test.py") == []

    def test_model_file_exists_loads_entries(self, monkeypatch, tmp_path):
        """If model JSON exists, entries are loaded and detection runs."""
        monkeypatch.setattr("pilotcode.services.knowhow._get_knowhow_dir", lambda: tmp_path)
        clear_knowhow_cache()

        import json

        model_file = tmp_path / "test-model.json"
        model_file.write_text(
            json.dumps(
                {
                    "model_name": "test-model",
                    "entries": [
                        {
                            "id": "test-rule",
                            "name": "Test rule",
                            "description": "Finds foobar",
                            "pattern": "foobar",
                            "pattern_type": "literal",
                            "severity": "warning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        lib = KnowhowLibrary.for_model("test-model")
        assert lib._has_model_file
        matches = lib.check("x = foobar\n", "test.py")
        assert len(matches) == 1
        assert matches[0].entry_id == "test-rule"

    def test_global_rules_loaded_with_model(self, monkeypatch, tmp_path):
        """global.json rules are loaded alongside model-specific rules."""
        monkeypatch.setattr("pilotcode.services.knowhow._get_knowhow_dir", lambda: tmp_path)
        clear_knowhow_cache()

        import json

        global_file = tmp_path / "global.json"
        global_file.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "id": "global-rule",
                            "name": "Global",
                            "description": "Global test",
                            "pattern": "globaltest",
                            "pattern_type": "literal",
                            "severity": "warning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        model_file = tmp_path / "test-model.json"
        model_file.write_text(
            json.dumps(
                {
                    "model_name": "test-model",
                    "entries": [
                        {
                            "id": "model-rule",
                            "name": "Model",
                            "description": "Model test",
                            "pattern": "modeltest",
                            "pattern_type": "literal",
                            "severity": "warning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        lib = KnowhowLibrary.for_model("test-model")
        source = "globaltest modeltest\n"
        matches = lib.check(source, "test.py")
        ids = {m.entry_id for m in matches}
        assert ids == {"global-rule", "model-rule"}

    def test_no_model_file_skips_even_with_global(self, monkeypatch, tmp_path):
        """If model file is missing, detection is skipped even if global.json exists."""
        monkeypatch.setattr("pilotcode.services.knowhow._get_knowhow_dir", lambda: tmp_path)
        clear_knowhow_cache()

        import json

        global_file = tmp_path / "global.json"
        global_file.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "id": "global-rule",
                            "name": "Global",
                            "description": "Global test",
                            "pattern": "globaltest",
                            "pattern_type": "literal",
                            "severity": "warning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        lib = KnowhowLibrary.for_model("unprofiled-model")
        assert not lib._has_model_file
        assert lib.check("globaltest\n", "test.py") == []


class TestKnowhowSerialization:
    """Test Entry to/from dict and JSON persistence."""

    def test_entry_roundtrip(self):
        original = KnowhowEntry(
            id="test-id",
            name="Test",
            description="Desc",
            pattern=r"hello\n",
            pattern_type="regex",
            applies_to_globs=["*.py", "*.js"],
            fix_type="replace",
            fix_replacement=r"world",
            severity="error",
            tags=["a", "b"],
        )
        d = original.to_dict()
        restored = KnowhowEntry.from_dict(d)
        assert restored.id == original.id
        assert restored.pattern == original.pattern
        assert restored.applies_to_globs == original.applies_to_globs
        assert restored.fix_replacement == original.fix_replacement

    def test_json_file_roundtrip(self, tmp_path):
        import json

        entries = [
            KnowhowEntry(
                id="json-test",
                name="JSON test",
                description="Testing JSON save/load",
                pattern="foobar",
                pattern_type="literal",
                severity="warning",
            )
        ]
        path = init_knowhow_for_model(
            model_name="json-test-model",
            entries=entries,
            notes="Test notes",
        )
        assert path.exists()

        lib = KnowhowLibrary.for_model("json-test-model")
        assert lib._has_model_file
        assert any(e.id == "json-test" for e in lib.entries)

        path.unlink()


class TestModelSlug:
    """Test model name → slug conversion."""

    def test_simple_name(self):
        assert model_slug("qwen3-coder-30b") == "qwen3-coder-30b"

    def test_uppercase(self):
        assert model_slug("Qwen3-Coder-30B") == "qwen3-coder-30b"

    def test_namespace(self):
        assert model_slug("Qwen/Qwen3-Coder-30B") == "qwen-qwen3-coder-30b"

    def test_special_chars(self):
        assert model_slug("model@v1.0") == "model-v1.0"


class TestGetKnowhowLibrary:
    """Test the convenience get_knowhow_library() function."""

    def test_none_returns_empty(self):
        lib = get_knowhow_library(None)
        assert lib.check("anything\n", "test.py") == []

    def test_caches_per_model(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pilotcode.services.knowhow._get_knowhow_dir", lambda: tmp_path)
        clear_knowhow_cache()

        import json

        model_file = tmp_path / "cached-model.json"
        model_file.write_text(
            json.dumps(
                {
                    "model_name": "cached-model",
                    "entries": [
                        {
                            "id": "cache-test",
                            "name": "Cache",
                            "description": "Cache test",
                            "pattern": "cacheme",
                            "pattern_type": "literal",
                            "severity": "warning",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        lib1 = get_knowhow_library("cached-model")
        lib2 = get_knowhow_library("cached-model")
        assert lib1 is lib2  # Same cached instance
