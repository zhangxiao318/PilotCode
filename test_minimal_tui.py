#!/usr/bin/env python3
"""Minimal TUI test to verify display works."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from textual.app import App
from textual.widgets import Static, Header, Footer
from textual.containers import Vertical
from pilotcode.tui_v2.components.prompt.input import PromptInput, PromptWithMode


class MinimalTestApp(App):
    """Minimal test app."""
    
    CSS = """
    Screen {
        background: #1e1e1e;
        color: #ffffff;
    }
    Header {
        dock: top;
        height: 1;
        background: #2d2d2d;
        color: #ffffff;
    }
    Footer {
        dock: bottom;
        height: 1;
        background: #2d2d2d;
        color: #a0a0a0;
    }
    #main {
        width: 100%;
        height: 1fr;
        background: #1e1e1e;
    }
    #message-area {
        width: 100%;
        height: 1fr;
        background: #1e1e1e;
        color: #ffffff;
        padding: 1;
    }
    #input-area {
        height: auto;
        min-height: 3;
        dock: bottom;
        background: #2d2d2d;
        border-top: solid #3e3e3e;
    }
    Static.test-message {
        height: auto;
        padding: 1;
        color: #ffffff;
    }
    """
    
    def compose(self):
        yield Header(show_clock=True)
        
        with Vertical(id="main"):
            with Vertical(id="message-area"):
                yield Static("🚀 Welcome to Test TUI!", classes="test-message")
                yield Static("Type below and press Enter:", classes="test-message")
                self.result = Static("Result: (nothing yet)", classes="test-message")
                yield self.result
            
            with Vertical(id="input-area"):
                self.input = PromptInput()
                yield self.input
        
        yield Footer()
    
    def on_mount(self):
        self.input.focus()
    
    def on_prompt_input_submitted(self, event):
        self.result.update(f"Result: You typed '{event.text}'")
        self.input.text = ""


if __name__ == "__main__":
    print("Starting minimal TUI test...")
    print("Press Ctrl+C to exit")
    app = MinimalTestApp()
    app.run()
