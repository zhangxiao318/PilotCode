"""Tests for Knowhow library."""

import tempfile
from pathlib import Path

from pilotcode.services.knowhow import (
    KnowhowLibrary,
    KnowhowEntry,
    KnowhowMatch,
    get_knowhow_library,
)


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
        lib = get_knowhow_library()
        stats = lib.get_stats()
        assert stats["total_rules"] > 0
        assert stats["by_severity"]["error"] > 0

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
