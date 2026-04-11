"""Code diff visualization component for displaying code changes."""

import re
from typing import Optional, List, Tuple
from textual.widgets import Static
from textual.reactive import reactive
from rich.console import RenderableType
from rich.panel import Panel
from rich.text import Text


class DiffLine:
    """Represents a single line in a diff."""

    def __init__(
        self,
        content: str,
        line_type: str = "context",
        old_line_num: Optional[int] = None,
        new_line_num: Optional[int] = None,
    ):
        self.content = content
        self.line_type = line_type  # 'addition', 'deletion', 'context', 'header'
        self.old_line_num = old_line_num
        self.new_line_num = new_line_num


class DiffView(Static):
    """Display a unified diff with syntax highlighting.

    Features:
    - Unified diff format support
    - Syntax highlighting for code
    - Line numbers for both old and new versions
    - Collapsible sections
    - Copy diff to clipboard
    """

    DEFAULT_CSS = """
    DiffView {
        height: auto;
        max-height: 30;
        margin: 0 1 1 1;
        padding: 0;
        background: $surface;
        border: solid $border;
    }
    
    DiffView.diff-header {
        background: $surface-lighten-1;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    
    DiffView .diff-line {
        height: 1;
        padding: 0 1;
    }
    
    DiffView .diff-addition {
        background: $success 20%;
    }
    
    DiffView .diff-deletion {
        background: $error 20%;
    }
    
    DiffView .diff-context {
        background: transparent;
    }
    
    DiffView .diff-line-number {
        color: $text-muted;
        text-style: dim;
        width: 4;
    }
    
    DiffView .diff-content-addition {
        color: $success;
    }
    
    DiffView .diff-content-deletion {
        color: $error;
    }
    
    DiffView .diff-content-context {
        color: $text;
    }
    
    DiffView.collapsed {
        max-height: 3;
    }
    
    DiffView .diff-stats {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }
    """

    BINDINGS = [
        ("c", "copy", "Copy"),
        ("space", "toggle", "Toggle"),
        ("y", "yank", "Yank"),
    ]

    collapsed: reactive[bool] = reactive(False)

    def __init__(
        self,
        diff_text: str,
        filename: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.diff_text = diff_text
        self.filename = filename or "file"
        self.language = language or self._detect_language(filename)
        self._lines: List[DiffLine] = []
        self._parse_diff()
        self.can_focus = True

    def _detect_language(self, filename: Optional[str]) -> str:
        """Detect programming language from filename."""
        if not filename:
            return "python"

        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".html": "html",
            ".css": "css",
            ".md": "markdown",
            ".sql": "sql",
            ".dockerfile": "docker",
        }

        if filename:
            for ext, lang in ext_map.items():
                if filename.endswith(ext):
                    return lang

        return "text"

    def _parse_diff(self):
        """Parse unified diff format."""
        lines = self.diff_text.split("\n")

        old_line = 0
        new_line = 0
        in_hunk = False

        for line in lines:
            if line.startswith("@@"):
                # Hunk header: @@ -old_start,old_count +new_start,new_count @@
                in_hunk = True
                match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    old_line = int(match.group(1))
                    new_line = int(match.group(2))
                self._lines.append(DiffLine(line, "header"))
            elif line.startswith("---"):
                self._lines.append(DiffLine(line, "header"))
            elif line.startswith("+++"):
                self._lines.append(DiffLine(line, "header"))
            elif line.startswith("+"):
                if in_hunk:
                    self._lines.append(DiffLine(line[1:], "addition", None, new_line))
                    new_line += 1
                else:
                    self._lines.append(DiffLine(line, "addition"))
            elif line.startswith("-"):
                if in_hunk:
                    self._lines.append(DiffLine(line[1:], "deletion", old_line, None))
                    old_line += 1
                else:
                    self._lines.append(DiffLine(line, "deletion"))
            elif line.startswith(" "):
                if in_hunk:
                    content = line[1:] if len(line) > 0 else ""
                    self._lines.append(DiffLine(content, "context", old_line, new_line))
                    old_line += 1
                    new_line += 1
                else:
                    self._lines.append(DiffLine(line, "context"))
            elif line.startswith("\\"):
                # "\ No newline at end of file"
                self._lines.append(DiffLine(line, "context"))
            else:
                # Context line without leading space (e.g., diff --git line)
                self._lines.append(DiffLine(line, "context"))

    def _get_stats(self) -> Tuple[int, int]:
        """Get diff statistics (additions, deletions)."""
        additions = sum(1 for line in self._lines if line.line_type == "addition")
        deletions = sum(1 for line in self._lines if line.line_type == "deletion")
        return additions, deletions

    def render(self) -> RenderableType:
        """Render the diff view."""
        additions, deletions = self._get_stats()

        # Build the diff display
        diff_lines = []

        for line in self._lines:
            if line.line_type == "header":
                # Header line
                text = Text(line.content, style="cyan bold")
                diff_lines.append(text)
            elif line.line_type == "addition":
                # Addition line
                old_num = "    " if line.old_line_num is None else f"{line.old_line_num:4}"
                new_num = f"{line.new_line_num:4}" if line.new_line_num else "    "
                content = self._highlight_code(line.content) if line.content else ""
                text = Text()
                text.append(f"{old_num} {new_num} ", style="dim")
                text.append(f"+ {content}", style="green")
                diff_lines.append(text)
            elif line.line_type == "deletion":
                # Deletion line
                old_num = f"{line.old_line_num:4}" if line.old_line_num else "    "
                new_num = "    " if line.new_line_num is None else f"{line.new_line_num:4}"
                content = self._highlight_code(line.content) if line.content else ""
                text = Text()
                text.append(f"{old_num} {new_num} ", style="dim")
                text.append(f"- {content}", style="red")
                diff_lines.append(text)
            else:  # context
                # Context line
                old_num = f"{line.old_line_num:4}" if line.old_line_num else "    "
                new_num = f"{line.new_line_num:4}" if line.new_line_num else "    "
                content = self._highlight_code(line.content) if line.content else ""
                text = Text()
                text.append(f"{old_num} {new_num} ", style="dim")
                text.append(f"  {content}", style="default")
                diff_lines.append(text)

        # Create panel
        title = f"📄 {self.filename}"
        subtitle = f"+{additions}/-{deletions}"

        if self.collapsed:
            return Panel(
                f"[dim]Diff collapsed. Press space to expand.[/] {subtitle}",
                title=title,
                title_align="left",
                border_style="dim",
            )

        content = Text("\n").join(diff_lines) if diff_lines else Text("No changes")

        return Panel(
            content, title=title, title_align="left", subtitle=subtitle, border_style="cyan"
        )

    def _highlight_code(self, code: str) -> str:
        """Apply basic syntax highlighting to code."""
        # For now, return plain code
        # In a full implementation, you'd use pygments or tree-sitter
        return code

    def action_copy(self):
        """Copy diff to clipboard."""
        self._copy_to_clipboard(self.diff_text)
        self.app.notify("📋 Diff copied!", severity="information", timeout=2)

    def action_yank(self):
        """Yank diff (vim alias)."""
        self.action_copy()

    def action_toggle(self):
        """Toggle collapsed state."""
        self.collapsed = not self.collapsed

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to clipboard."""
        import subprocess
        import platform

        system = platform.system()
        try:
            if system == "Linux":
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                    capture_output=True,
                )
                return True
            elif system == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True, capture_output=True)
                return True
            elif system == "Windows":
                subprocess.run(["clip.exe"], input=text.encode(), check=True, capture_output=True)
                return True
        except Exception:
            pass
        return False

    def watch_collapsed(self, collapsed: bool):
        """React to collapsed state changes."""
        if collapsed:
            self.add_class("collapsed")
        else:
            self.remove_class("collapsed")
        self.refresh()


class DiffSummary(Static):
    """Summary of multiple file changes."""

    DEFAULT_CSS = """
    DiffSummary {
        height: auto;
        margin: 0 1 1 1;
        padding: 1;
        background: $surface;
        border: solid $border;
    }
    """

    def __init__(self, changes: List[Tuple[str, int, int]], **kwargs):
        """
        Args:
            changes: List of (filename, additions, deletions) tuples
        """
        super().__init__(**kwargs)
        self.changes = changes

    def render(self) -> RenderableType:
        """Render the summary."""
        total_additions = sum(add for _, add, _ in self.changes)
        total_deletions = sum(del_ for _, _, del_ in self.changes)

        lines = []
        lines.append(f"[bold]{len(self.changes)} files changed[/]")
        lines.append(f"  [green]+{total_additions}[/] [red]-{total_deletions}[/]")
        lines.append("")

        for filename, additions, deletions in self.changes:
            lines.append(f"  {filename} [green]+{additions}[/] [red]-{deletions}[/]")

        return Panel(
            "\n".join(lines), title="📊 Changes Summary", title_align="left", border_style="blue"
        )


def create_diff(old_content: str, new_content: str, filename: str = "file") -> str:
    """Create a unified diff between two contents.

    This is a helper function for generating diffs.
    """
    import difflib

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure lines end with newline
    old_lines = [line if line.endswith("\n") else line + "\n" for line in old_lines]
    new_lines = [line if line.endswith("\n") else line + "\n" for line in new_lines]

    diff = difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm="\n"
    )

    return "".join(diff)
