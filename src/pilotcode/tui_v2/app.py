"""Enhanced TUI App for PilotCode."""

import sys
import argparse
from pathlib import Path

from textual.app import App

from pilotcode.state.store import Store, set_global_store, get_store
from pilotcode.state.app_state import get_default_app_state
from pilotcode.tui_v2.screens.session import SessionScreen
from pilotcode.tui_v2.providers.theme_enhanced import get_theme_manager, Theme


# Default dark theme colors
DEFAULT_DARK_THEME = {
    "background": "#1e1e1e",
    "surface": "#2d2d2d",
    "text": "#ffffff",
    "text-muted": "#a0a0a0",
    "border": "#3e3e3e",
    "primary": "#0066cc",
    "secondary": "#6c757d",
    "success": "#28a745",
    "danger": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8",
}

# Light theme colors
LIGHT_THEME = {
    "background": "#ffffff",
    "surface": "#f5f5f5",
    "text": "#333333",
    "text-muted": "#666666",
    "border": "#dddddd",
    "primary": "#0066cc",
    "secondary": "#6c757d",
    "success": "#28a745",
    "danger": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8",
}


class EnhancedApp(App):
    """Enhanced PilotCode TUI Application."""
    
    # Enable dark mode by default
    dark = True
    
    CSS = """
    /* Base styles */
    Screen {
        background: $background;
        color: $text;
    }
    """
    
    def __init__(self, auto_allow: bool = False, theme: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.auto_allow = auto_allow
        self.theme_name = theme
        self._store: Store | None = None
        self._theme_manager = get_theme_manager()
    
    def on_mount(self):
        """Called when app is mounted."""
        # Initialize store
        app_state = get_default_app_state()
        self._store = Store(app_state)
        set_global_store(self._store)
        
        # Apply theme (registers CSS variables)
        self._apply_theme()
        
        # Push main screen
        self.push_screen(SessionScreen(auto_allow=self.auto_allow))
    
    def _apply_theme(self):
        """Apply current theme by registering CSS variables."""
        # Get theme colors
        if self.theme_name == "light":
            colors = LIGHT_THEME
            self.dark = False
        else:
            colors = DEFAULT_DARK_THEME
            self.dark = True
        
        # Register CSS variables
        self.register_theme_variables(colors)
        
        # Also apply through theme manager if available
        try:
            self._theme_manager.set_theme(self.theme_name)
        except Exception:
            pass
    
    def register_theme_variables(self, colors: dict):
        """Register theme colors as CSS variables."""
        # Textual allows registering custom CSS variables
        for name, value in colors.items():
            # Convert kebab-case to valid CSS variable name
            var_name = name.replace("-", "_")
            self.register_css_variable(var_name, value)
    
    def register_css_variable(self, name: str, value: str):
        """Register a single CSS variable."""
        # Store in app's CSS variables
        if not hasattr(self, '_css_variables'):
            self._css_variables = {}
        self._css_variables[name] = value
        
        # Apply to all screens
        try:
            self.styles._variables[name] = value
        except Exception:
            pass
    
    def get_store(self) -> Store | None:
        """Get the global store."""
        return self._store
    
    def switch_theme(self, theme_name: str):
        """Switch theme at runtime."""
        self.theme_name = theme_name
        self._apply_theme()
        self.refresh()


def main():
    """Entry point for enhanced TUI."""
    parser = argparse.ArgumentParser(description="PilotCode Enhanced TUI")
    parser.add_argument(
        "--auto-allow",
        action="store_true",
        help="Auto-allow all tool executions"
    )
    parser.add_argument(
        "--theme",
        default="default",
        choices=["default", "light", "dark", "dracula", "monokai", "nord", "gruvbox"],
        help="Theme to use (default: default)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name to use"
    )
    
    args = parser.parse_args()
    
    # Create and run app
    app = EnhancedApp(
        auto_allow=args.auto_allow,
        theme=args.theme
    )
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")
        sys.exit(0)


if __name__ == "__main__":
    main()
