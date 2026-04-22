"""UI framework - Four-layer display architecture.

All UI modes (REPL, Simple CLI, TUI v2, Web) render content through
four unified layers:

    ┌──────────────────────────────────────┐
    │  1. Status Layer                      │
    │     - Token usage, model info, budget │
    │     - Session duration, git branch    │
    │     - Persistent status bar / panel   │
    ├──────────────────────────────────────┤
    │  2. Conversational Layer              │
    │     - User input, assistant response  │
    │     - Thinking content                │
    │     - Tool calls and results          │
    │     - Time-ordered chat stream        │
    ├──────────────────────────────────────┤
    │  3. System Layer                      │
    │     - Notifications (auto-compact)    │
    │     - Warnings (context limit)        │
    │     - Progress indicators             │
    │     - Errors and exceptions           │
    ├──────────────────────────────────────┤
    │  4. Interactive Layer                 │
    │     - Permission requests             │
    │     - User questions / choices        │
    │     - Modal dialogs / inline prompts  │
    └──────────────────────────────────────┘

Usage in a UI class:

    class MyUI:
        def _render_status(self, event: DisplayEvent) -> None: ...
        def _render_conversational(self, event: DisplayEvent) -> None: ...
        def _render_system(self, event: DisplayEvent) -> None: ...
        def _render_interactive(self, event: DisplayEvent) -> Any: ...
"""
