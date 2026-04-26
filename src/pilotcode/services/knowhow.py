"""Knowhow — model-agnostic known-problem library for code review.

Each entry defines a common mistake made by weak LLMs (e.g. escape-sequence
double-escaping, wrong indentation style) together with:
- A detection pattern (regex, AST, or literal)
- An optional auto-fix
- Severity and human-readable explanation

The library is checked automatically after every FileEdit/FileWrite so that
weak-model mistakes are caught before they reach the user.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowhowMatch:
    """A single instance of a known problem found in code."""

    entry_id: str
    name: str
    description: str
    severity: str  # "error" | "warning" | "info"
    line_number: int
    column: int
    matched_text: str
    suggestion: str
    auto_fix: str | None = None  # If set, can be applied automatically


@dataclass
class KnowhowEntry:
    """A single rule in the knowhow library."""

    id: str
    name: str
    description: str
    # Detection
    pattern: str
    pattern_type: str = "regex"  # "regex" | "literal" | "ast"
    # Scope
    applies_to_globs: list[str] = field(default_factory=lambda: ["*.py"])
    # Fix
    fix_type: str = "warn"  # "replace" | "remove" | "warn"
    fix_replacement: str | None = None
    # Metadata
    severity: str = "warning"  # "error" | "warning" | "info"
    tags: list[str] = field(default_factory=list)

    def detect(self, source: str, file_path: str | None = None) -> list[KnowhowMatch]:
        """Run detection against source code."""
        if file_path and not self._applies_to(file_path):
            return []

        if self.pattern_type == "regex":
            return self._detect_regex(source)
        if self.pattern_type == "literal":
            return self._detect_literal(source)
        if self.pattern_type == "ast":
            return self._detect_ast(source)
        return []

    def _applies_to(self, file_path: str) -> bool:
        from fnmatch import fnmatch

        path = Path(file_path).name
        return any(fnmatch(path, g) for g in self.applies_to_globs)

    def _detect_regex(self, source: str) -> list[KnowhowMatch]:
        matches: list[KnowhowMatch] = []
        lines = source.split("\n")
        for line_no, line in enumerate(lines, start=1):
            for m in re.finditer(self.pattern, line):
                matched = m.group(0)
                auto_fix = None
                if self.fix_type == "replace" and self.fix_replacement is not None:
                    auto_fix = re.sub(self.pattern, self.fix_replacement, matched, count=1)
                matches.append(
                    KnowhowMatch(
                        entry_id=self.id,
                        name=self.name,
                        description=self.description,
                        severity=self.severity,
                        line_number=line_no,
                        column=m.start(),
                        matched_text=matched,
                        suggestion=self.description,
                        auto_fix=auto_fix,
                    )
                )
        return matches

    def _detect_literal(self, source: str) -> list[KnowhowMatch]:
        matches: list[KnowhowMatch] = []
        lines = source.split("\n")
        for line_no, line in enumerate(lines, start=1):
            idx = line.find(self.pattern)
            while idx != -1:
                matched = self.pattern
                auto_fix = None
                if self.fix_type == "replace" and self.fix_replacement is not None:
                    auto_fix = self.fix_replacement
                matches.append(
                    KnowhowMatch(
                        entry_id=self.id,
                        name=self.name,
                        description=self.description,
                        severity=self.severity,
                        line_number=line_no,
                        column=idx,
                        matched_text=matched,
                        suggestion=self.description,
                        auto_fix=auto_fix,
                    )
                )
                idx = line.find(self.pattern, idx + 1)
        return matches

    def _detect_ast(self, source: str) -> list[KnowhowMatch]:
        """AST-based detection (placeholder for future rules)."""
        matches: list[KnowhowMatch] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return matches
        # AST walking would go here
        return matches


# ---------------------------------------------------------------------------
# Built-in library — known weak-model mistakes
# ---------------------------------------------------------------------------

_BUILTIN_KNOWHOW: list[KnowhowEntry] = [
    # --- Python string escapes ---
    KnowhowEntry(
        id="py-string-escape-double-n",
        name="Double-escaped newline",
        description="In Python source code, '\\n' inside a string literal produces the two characters backslash+n, not a newline. Use a single backslash if you want a real newline.",
        pattern=r'"[^"]*\\\\n[^"]*"|' r"'[^']*\\\\n[^']*'",
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="replace",
        fix_replacement=r"\g<0>",  # placeholder — real fix done in post-processing
        severity="error",
        tags=["python", "string", "escape"],
    ),
    KnowhowEntry(
        id="py-string-escape-double-t",
        name="Double-escaped tab",
        description="In Python source code, '\\t' inside a string literal produces the two characters backslash+t, not a tab. Use a single backslash if you want a real tab.",
        pattern=r'"[^"]*\\\\t[^"]*"|' r"'[^']*\\\\t[^']*'",
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="replace",
        fix_replacement=r"\g<0>",
        severity="error",
        tags=["python", "string", "escape"],
    ),
    KnowhowEntry(
        id="py-string-escape-double-quote",
        name="Double-escaped quote",
        description="In Python source code, '\\\"' inside a double-quoted string literal produces the two characters backslash+quote, not an escaped quote.",
        pattern=r'"[^"]*\\\\"[^"]*"',
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="replace",
        fix_replacement=r"\g<0>",
        severity="error",
        tags=["python", "string", "escape"],
    ),
    KnowhowEntry(
        id="py-string-escape-double-backslash-return",
        name="Double-escaped backslash in f-string/join",
        description="'\\\\n' or '\\\\t' in an f-string or regular string produces literal backslash sequences instead of escapes.",
        pattern=r'"\\\\n"|"\\\\t"|"\\\\r"',
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="replace",
        fix_replacement=r"\g<0>",
        severity="error",
        tags=["python", "string", "escape"],
    ),
    # --- Python f-string issues ---
    KnowhowEntry(
        id="py-fstring-escaped-brace",
        name="F-string with escaped braces",
        description="Weak models sometimes write f'{{var}}' thinking it inserts var. In f-strings {{ }} are literal braces; use {var} for interpolation.",
        pattern=r'f[\'"]\s*\{\{[^}]+\}\}',
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="warn",
        severity="warning",
        tags=["python", "fstring"],
    ),
    # --- Indentation / whitespace ---
    KnowhowEntry(
        id="py-mixed-indentation",
        name="Mixed tabs and spaces",
        description="Line uses both tabs and spaces for indentation. Python 3 disallows this.",
        pattern=r"^(\t+ +| +\t+)",
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="warn",
        severity="error",
        tags=["python", "whitespace"],
    ),
    # --- Common API mistakes ---
    KnowhowEntry(
        id="py-asyncio-run-in-async",
        name="asyncio.run inside async function",
        description="asyncio.run() cannot be called from a running event loop (e.g. inside another async function). Use 'await' directly instead.",
        pattern=r"asyncio\.run\(",
        pattern_type="regex",
        applies_to_globs=["*.py"],
        fix_type="warn",
        severity="warning",
        tags=["python", "async"],
    ),
]


class KnowhowLibrary:
    """Registry of known problems."""

    def __init__(self, entries: list[KnowhowEntry] | None = None) -> None:
        self.entries = list(entries) if entries is not None else list(_BUILTIN_KNOWHOW)
        self._by_id = {e.id: e for e in self.entries}

    def add(self, entry: KnowhowEntry) -> None:
        """Add a new knowhow entry."""
        self.entries.append(entry)
        self._by_id[entry.id] = entry

    def check(self, source: str, file_path: str | None = None) -> list[KnowhowMatch]:
        """Check source against all applicable rules."""
        all_matches: list[KnowhowMatch] = []
        for entry in self.entries:
            all_matches.extend(entry.detect(source, file_path))
        # Sort by line number
        all_matches.sort(key=lambda m: (m.line_number, m.column))
        return all_matches

    def check_file(self, file_path: str) -> list[KnowhowMatch]:
        """Check a file on disk."""
        path = Path(file_path)
        if not path.exists():
            return []
        source = path.read_text(encoding="utf-8", errors="replace")
        return self.check(source, str(path))

    def apply_auto_fixes(self, source: str, matches: list[KnowhowMatch]) -> str:
        """Apply all auto-fixable matches to source.

        Returns the corrected source code.  Non-auto-fixable matches are left
        as-is but reported via the returned matches list.
        """
        lines = source.split("\n")
        # Group by line, process from right-most column to left so offsets
        # don't shift during replacement.
        by_line: dict[int, list[KnowhowMatch]] = {}
        for m in matches:
            if m.auto_fix is not None:
                by_line.setdefault(m.line_number, []).append(m)

        for line_no, ms in by_line.items():
            idx = line_no - 1
            if idx < 0 or idx >= len(lines):
                continue
            line = lines[idx]
            ms.sort(key=lambda m: m.column, reverse=True)
            for m in ms:
                start = m.column
                end = start + len(m.matched_text)
                # For regex-based rules, compute the real replacement
                replacement = self._compute_replacement(m)
                if replacement is not None:
                    line = line[:start] + replacement + line[end:]
            lines[idx] = line

        return "\n".join(lines)

    @staticmethod
    def _compute_replacement(match: KnowhowMatch) -> str | None:
        """Compute the replacement string for a match.

        Handles the special case of double-escaped sequences.
        """
        text = match.matched_text
        entry_id = match.entry_id

        if entry_id in (
            "py-string-escape-double-n",
            "py-string-escape-double-t",
            "py-string-escape-double-quote",
            "py-string-escape-double-backslash-return",
        ):
            # Replace \\n -> \n, \\t -> \t, \\" -> \", etc.
            return (
                text.replace("\\\\n", "\\n")
                .replace("\\\\t", "\\t")
                .replace('\\\\"', '\\"')
                .replace("\\\\r", "\\r")
            )

        return match.auto_fix

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        return {
            "total_rules": len(self.entries),
            "by_severity": {
                "error": len([e for e in self.entries if e.severity == "error"]),
                "warning": len([e for e in self.entries if e.severity == "warning"]),
                "info": len([e for e in self.entries if e.severity == "info"]),
            },
            "by_tag": {},
        }


# Global singleton
_default_library: KnowhowLibrary | None = None


def get_knowhow_library() -> KnowhowLibrary:
    """Get the default knowhow library instance."""
    global _default_library
    if _default_library is None:
        _default_library = KnowhowLibrary()
    return _default_library
