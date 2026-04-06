"""Theme provider for TUI."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Theme:
    """Theme definition."""

    name: str
    colors: Dict[str, str]

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "Theme":
        return cls(name=name, colors=data.get("colors", {}))


class ThemeProvider:
    """Provides theme management for TUI."""

    # Default themes embedded in code (MVP)
    DEFAULT_THEMES = {
        "default": {
            "colors": {
                "primary": "#0066cc",
                "secondary": "#6c757d",
                "success": "#28a745",
                "danger": "#dc3545",
                "warning": "#ffc107",
                "info": "#17a2b8",
                "background": "#1e1e1e",
                "surface": "#2d2d2d",
                "text": "#ffffff",
                "text-muted": "#a0a0a0",
                "border": "#3e3e3e",
                "user-message": "#0066cc",
                "assistant-message": "#2d2d2d",
                "tool-message": "#ffc107",
            }
        },
        "light": {
            "colors": {
                "primary": "#0056b3",
                "secondary": "#6c757d",
                "success": "#28a745",
                "danger": "#dc3545",
                "warning": "#ffc107",
                "info": "#17a2b8",
                "background": "#f8f9fa",
                "surface": "#ffffff",
                "text": "#212529",
                "text-muted": "#6c757d",
                "border": "#dee2e6",
                "user-message": "#e3f2fd",
                "assistant-message": "#ffffff",
                "tool-message": "#fff3cd",
            }
        },
    }

    def __init__(self):
        self._themes: Dict[str, Theme] = {}
        self._current_theme: str = "default"
        self._load_default_themes()

    def _load_default_themes(self):
        """Load built-in themes."""
        for name, data in self.DEFAULT_THEMES.items():
            self._themes[name] = Theme.from_dict(name, data)

    def get_theme(self, name: Optional[str] = None) -> Theme:
        """Get theme by name (or current theme)."""
        theme_name = name or self._current_theme
        return self._themes.get(theme_name, self._themes["default"])

    def set_theme(self, name: str) -> bool:
        """Set current theme."""
        if name in self._themes:
            self._current_theme = name
            return True
        return False

    def get_current_theme_name(self) -> str:
        """Get current theme name."""
        return self._current_theme

    def list_themes(self) -> list[str]:
        """List available themes."""
        return list(self._themes.keys())

    def get_css_variables(self) -> str:
        """Get Textual CSS for current theme."""
        theme = self.get_theme()
        css_lines = ["/* Theme CSS Variables */"]
        for key, value in theme.colors.items():
            css_var = key.replace("-", "_")
            css_lines.append(f"$theme_{css_var}: {value};")
        return "\n".join(css_lines)


# Global instance
_theme_provider: Optional[ThemeProvider] = None


def get_theme_provider() -> ThemeProvider:
    """Get global theme provider."""
    global _theme_provider
    if _theme_provider is None:
        _theme_provider = ThemeProvider()
    return _theme_provider
