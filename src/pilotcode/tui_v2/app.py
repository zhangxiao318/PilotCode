"""Enhanced TUI App for PilotCode."""

import sys
import argparse

from textual.app import App

from pilotcode.state.store import Store, set_global_store
from pilotcode.state.app_state import get_default_app_state
from pilotcode.tui_v2.screens.session import SessionScreen


class EnhancedApp(App):
    """Enhanced PilotCode TUI Application."""

    # App metadata
    TITLE = "PilotCode"
    VERSION = "0.2.0"

    # Dark mode
    dark = True

    CSS = """
    Screen {
        background: #000000;
        color: #ffffff;
    }
    """

    def __init__(
        self,
        auto_allow: bool = False,
        theme: str = "default",
        max_iterations: int = 50,
        session_options: dict | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.auto_allow = auto_allow
        self.max_iterations = max_iterations
        self.session_options = session_options or {}
        self._store: Store | None = None

    def on_mount(self):
        """Called when app is mounted."""
        # Initialize store
        app_state = get_default_app_state()
        self._store = Store(app_state)
        set_global_store(self._store)

        # Push main screen
        self.push_screen(
            SessionScreen(
                auto_allow=self.auto_allow,
                max_iterations=self.max_iterations,
                session_options=self.session_options,
            )
        )

    def get_store(self) -> Store | None:
        """Get the global store."""
        return self._store


def main():
    """Entry point for enhanced TUI."""
    parser = argparse.ArgumentParser(description="PilotCode Enhanced TUI")
    parser.add_argument("--auto-allow", action="store_true", help="Auto-allow all tool executions")
    parser.add_argument(
        "--theme",
        default="default",
        choices=["default", "light"],
        help="Theme to use (default: default)",
    )
    parser.add_argument("--model", default=None, help="Model name to use")
    parser.add_argument(
        "--max-iterations",
        "-i",
        type=int,
        default=50,
        help="Maximum tool execution rounds per query (default: 50, env: PILOTCODE_MAX_ITERATIONS)",
    )

    args = parser.parse_args()

    # Check environment variable override
    import os

    env_iterations = os.environ.get("PILOTCODE_MAX_ITERATIONS")
    if env_iterations:
        args.max_iterations = int(env_iterations)

    # Create and run app
    app = EnhancedApp(
        auto_allow=args.auto_allow, theme=args.theme, max_iterations=args.max_iterations
    )

    try:
        app.run()
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")
        sys.exit(0)


if __name__ == "__main__":
    main()
