"""Enhanced TUI App for PilotCode."""

import sys
import argparse
from pathlib import Path

from textual.app import App

from pilotcode.state.store import Store, set_global_store, get_store
from pilotcode.state.app_state import get_default_app_state
from pilotcode.tui_v2.screens.session import SessionScreen
from pilotcode.tui_v2.providers.theme import get_theme_provider


class EnhancedApp(App):
    """Enhanced PilotCode TUI Application."""
    
    CSS = """
    /* Base styles */
    Screen {
        background: $background;
        color: $text;
    }
    
    /* Theme variables - will be overridden by theme provider */
    $theme_primary: #0066cc;
    $theme_secondary: #6c757d;
    $theme_success: #28a745;
    $theme_danger: #dc3545;
    $theme_warning: #ffc107;
    $theme_info: #17a2b8;
    $theme_background: #1e1e1e;
    $theme_surface: #2d2d2d;
    $theme_text: #ffffff;
    $theme_text_muted: #a0a0a0;
    $theme_border: #3e3e3e;
    $theme_user_message: #0066cc;
    $theme_assistant_message: #2d2d2d;
    $theme_tool_message: #ffc107;
    """
    
    def __init__(self, auto_allow: bool = False, theme: str = "default", **kwargs):
        super().__init__(**kwargs)
        self.auto_allow = auto_allow
        self.theme_name = theme
        self._store: Store | None = None
    
    def on_mount(self):
        """Called when app is mounted."""
        # Initialize store
        app_state = get_default_app_state()
        self._store = Store(app_state)
        set_global_store(self._store)
        
        # Apply theme
        self._apply_theme()
        
        # Push main screen
        self.push_screen(SessionScreen(auto_allow=self.auto_allow))
    
    def _apply_theme(self):
        """Apply current theme."""
        theme_provider = get_theme_provider()
        theme_provider.set_theme(self.theme_name)
        # Theme CSS is applied through the provider
    
    def get_store(self) -> Store | None:
        """Get the global store."""
        return self._store


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
        choices=["default", "light"],
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
