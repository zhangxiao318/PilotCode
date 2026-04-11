"""Enhanced theme system with multiple built-in themes and custom theme support."""

from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class Theme:
    """A color theme definition."""

    # Basic colors
    background: str = "#1e1e1e"
    surface: str = "#2d2d2d"
    text: str = "#ffffff"
    text_muted: str = "#a0a0a0"
    border: str = "#3e3e3e"

    # Accent colors
    primary: str = "#0066cc"
    secondary: str = "#6c757d"
    success: str = "#28a745"
    danger: str = "#dc3545"
    warning: str = "#ffc107"
    info: str = "#17a2b8"

    # Message-specific colors
    user_message: str = "#0066cc"
    assistant_message: str = "#2d2d2d"
    tool_message: str = "#ffc107"
    error_message: str = "#dc3545"
    system_message: str = "#6c757d"

    # Syntax highlighting
    syntax_keyword: str = "#ff79c6"
    syntax_string: str = "#f1fa8c"
    syntax_comment: str = "#6272a4"
    syntax_function: str = "#50fa7b"
    syntax_variable: str = "#f8f8f2"
    syntax_operator: str = "#ff79c6"
    syntax_file_ref: str = "#4FC1FF"
    syntax_command: str = "#FF79C6"
    syntax_mention: str = "#50FA7B"

    # UI elements
    cursor: str = "#ffffff"
    selection: str = "#264f78"
    scrollbar: str = "#424242"

    # Metadata
    name: str = "default"
    is_dark: bool = True


# Built-in themes
BUILT_IN_THEMES: Dict[str, Theme] = {
    "default": Theme(
        name="default",
        background="#1e1e1e",
        surface="#2d2d2d",
        text="#ffffff",
    ),
    "light": Theme(
        name="light",
        is_dark=False,
        background="#ffffff",
        surface="#f5f5f5",
        text="#333333",
        text_muted="#666666",
        border="#dddddd",
        primary="#0066cc",
        user_message="#0066cc",
        assistant_message="#f0f0f0",
        syntax_keyword="#d73a49",
        syntax_string="#032f62",
        syntax_comment="#6a737d",
        syntax_function="#6f42c1",
        syntax_variable="#24292e",
        cursor="#333333",
        selection="#b4d7ff",
        scrollbar="#c1c1c1",
    ),
    "dracula": Theme(
        name="dracula",
        background="#282a36",
        surface="#44475a",
        text="#f8f8f2",
        text_muted="#6272a4",
        border="#6272a4",
        primary="#bd93f9",
        success="#50fa7b",
        danger="#ff5555",
        warning="#ffb86c",
        info="#8be9fd",
        user_message="#bd93f9",
        assistant_message="#44475a",
        tool_message="#ffb86c",
        error_message="#ff5555",
        syntax_keyword="#ff79c6",
        syntax_string="#f1fa8c",
        syntax_comment="#6272a4",
        syntax_function="#50fa7b",
        syntax_variable="#f8f8f2",
        syntax_operator="#ff79c6",
    ),
    "monokai": Theme(
        name="monokai",
        background="#272822",
        surface="#383830",
        text="#f8f8f2",
        text_muted="#75715e",
        border="#49483e",
        primary="#66d9ef",
        success="#a6e22e",
        danger="#f92672",
        warning="#fd971f",
        info="#66d9ef",
        user_message="#66d9ef",
        assistant_message="#383830",
        tool_message="#fd971f",
        error_message="#f92672",
        syntax_keyword="#f92672",
        syntax_string="#e6db74",
        syntax_comment="#75715e",
        syntax_function="#a6e22e",
        syntax_variable="#f8f8f2",
        syntax_operator="#f92672",
    ),
    "nord": Theme(
        name="nord",
        background="#2e3440",
        surface="#3b4252",
        text="#eceff4",
        text_muted="#4c566a",
        border="#434c5e",
        primary="#88c0d0",
        success="#a3be8c",
        danger="#bf616a",
        warning="#ebcb8b",
        info="#81a1c1",
        user_message="#88c0d0",
        assistant_message="#3b4252",
        tool_message="#ebcb8b",
        error_message="#bf616a",
        syntax_keyword="#81a1c1",
        syntax_string="#a3be8c",
        syntax_comment="#616e88",
        syntax_function="#88c0d0",
        syntax_variable="#eceff4",
        syntax_operator="#81a1c1",
    ),
    "gruvbox": Theme(
        name="gruvbox",
        background="#282828",
        surface="#3c3836",
        text="#ebdbb2",
        text_muted="#928374",
        border="#504945",
        primary="#83a598",
        success="#b8bb26",
        danger="#fb4934",
        warning="#fabd2f",
        info="#8ec07c",
        user_message="#83a598",
        assistant_message="#3c3836",
        tool_message="#fabd2f",
        error_message="#fb4934",
        syntax_keyword="#fb4934",
        syntax_string="#b8bb26",
        syntax_comment="#928374",
        syntax_function="#8ec07c",
        syntax_variable="#ebdbb2",
        syntax_operator="#fb4934",
    ),
    "high-contrast": Theme(
        name="high-contrast",
        background="#000000",
        surface="#1a1a1a",
        text="#ffffff",
        text_muted="#aaaaaa",
        border="#ffffff",
        primary="#00ffff",
        success="#00ff00",
        danger="#ff0000",
        warning="#ffff00",
        info="#00ffff",
        user_message="#00ffff",
        assistant_message="#1a1a1a",
        tool_message="#ffff00",
        error_message="#ff0000",
        cursor="#ffffff",
        selection="#0080ff",
    ),
}


class ThemeManager:
    """Manages themes and theme switching.

    Features:
    - Built-in themes
    - Custom theme loading
    - Theme persistence
    - Auto-detection of system theme
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path.home() / ".pilotcode"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.themes_file = self.storage_dir / "custom_themes.json"
        self.config_file = self.storage_dir / "theme_config.json"

        self._themes: Dict[str, Theme] = dict(BUILT_IN_THEMES)
        self._current_theme: str = "default"
        self._change_callbacks: List[Callable[[Theme], None]] = []

        self._load_custom_themes()
        self._load_config()

    def _load_custom_themes(self):
        """Load custom themes from disk."""
        if not self.themes_file.exists():
            return

        try:
            with open(self.themes_file, "r") as f:
                data = json.load(f)

            for name, theme_data in data.items():
                theme = Theme(name=name, **theme_data)
                self._themes[name] = theme
        except Exception as e:
            print(f"Failed to load custom themes: {e}")

    def _save_custom_themes(self):
        """Save custom themes to disk."""
        custom_themes = {
            name: {
                k: v
                for k, v in theme.__dict__.items()
                if k not in ("name",) and not k.startswith("_")
            }
            for name, theme in self._themes.items()
            if name not in BUILT_IN_THEMES
        }

        try:
            with open(self.themes_file, "w") as f:
                json.dump(custom_themes, f, indent=2)
        except Exception as e:
            print(f"Failed to save custom themes: {e}")

    def _load_config(self):
        """Load theme configuration."""
        if not self.config_file.exists():
            return

        try:
            with open(self.config_file, "r") as f:
                config = json.load(f)
            self._current_theme = config.get("current_theme", "default")
        except Exception as e:
            print(f"Failed to load theme config: {e}")

    def _save_config(self):
        """Save theme configuration."""
        try:
            with open(self.config_file, "w") as f:
                json.dump({"current_theme": self._current_theme}, f)
        except Exception as e:
            print(f"Failed to save theme config: {e}")

    def get_theme(self, name: Optional[str] = None) -> Theme:
        """Get a theme by name, or the current theme if no name given."""
        name = name or self._current_theme
        return self._themes.get(name, self._themes["default"])

    def set_theme(self, name: str) -> bool:
        """Set the current theme.

        Returns True if successful, False if theme not found.
        """
        if name not in self._themes:
            return False

        self._current_theme = name
        self._save_config()

        # Notify callbacks
        theme = self._themes[name]
        for callback in self._change_callbacks:
            try:
                callback(theme)
            except Exception as e:
                print(f"Theme change callback failed: {e}")

        return True

    def get_current_theme_name(self) -> str:
        """Get the name of the current theme."""
        return self._current_theme

    def list_themes(self) -> List[str]:
        """List all available theme names."""
        return list(self._themes.keys())

    def list_built_in_themes(self) -> List[str]:
        """List built-in theme names."""
        return list(BUILT_IN_THEMES.keys())

    def add_custom_theme(self, name: str, theme: Theme) -> bool:
        """Add a custom theme.

        Returns False if name conflicts with built-in theme.
        """
        if name in BUILT_IN_THEMES:
            return False

        theme.name = name
        self._themes[name] = theme
        self._save_custom_themes()
        return True

    def remove_custom_theme(self, name: str) -> bool:
        """Remove a custom theme."""
        if name in BUILT_IN_THEMES:
            return False

        if name in self._themes:
            del self._themes[name]
            self._save_custom_themes()

            # Switch to default if current theme was removed
            if self._current_theme == name:
                self.set_theme("default")

            return True

        return False

    def on_theme_change(self, callback: Callable[[Theme], None]):
        """Register a callback for theme changes."""
        self._change_callbacks.append(callback)

    def off_theme_change(self, callback: Callable[[Theme], None]):
        """Unregister a theme change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)

    def get_theme_css(self, name: Optional[str] = None) -> str:
        """Generate CSS for a theme."""
        theme = self.get_theme(name)

        return f"""
        /* Theme: {theme.name} */
        Screen {{
            background: {theme.background};
            color: {theme.text};
        }}
        
        * {{
            background: {theme.background};
            color: {theme.text};
        }}
        
        .surface {{
            background: {theme.surface};
        }}
        
        .primary {{
            color: {theme.primary};
        }}
        
        .success {{
            color: {theme.success};
        }}
        
        .danger {{
            color: {theme.danger};
        }}
        
        .warning {{
            color: {theme.warning};
        }}
        
        .info {{
            color: {theme.info};
        }}
        
        .muted {{
            color: {theme.text_muted};
        }}
        
        /* Syntax highlighting */
        .syntax-file-ref {{
            color: {theme.syntax_file_ref};
        }}
        
        .syntax-command {{
            color: {theme.syntax_command};
        }}
        
        .syntax-mention {{
            color: {theme.syntax_mention};
        }}
        
        .syntax-keyword {{
            color: {theme.syntax_keyword};
        }}
        
        .syntax-string {{
            color: {theme.syntax_string};
        }}
        """

    def auto_detect_theme(self) -> str:
        """Auto-detect system theme preference.

        Returns the recommended theme name.
        """
        import os
        import platform

        system = platform.system()

        # Check for macOS dark mode
        if system == "Darwin":
            try:
                import subprocess

                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True,
                    text=True,
                )
                if "Dark" in result.stdout:
                    return "default"
            except Exception:
                pass

        # Check for GTK dark mode on Linux
        if system == "Linux":
            try:
                theme = os.environ.get("GTK_THEME", "").lower()
                if "dark" in theme:
                    return "default"
            except Exception:
                pass

        # Check Windows
        if system == "Windows":
            try:
                import winreg

                registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                key = winreg.OpenKey(
                    registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                )
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                if value == 0:
                    return "default"
            except Exception:
                pass

        # Default to light if detection fails
        return "light"


# Global theme manager instance
_theme_manager: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def set_theme_manager(manager: ThemeManager):
    """Set the global theme manager instance."""
    global _theme_manager
    _theme_manager = manager
