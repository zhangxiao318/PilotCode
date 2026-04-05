"""Session provider for TUI state management."""

from typing import Optional, Callable, Any
from dataclasses import dataclass, field


@dataclass
class TUISessionState:
    """TUI-specific session state."""
    current_screen: str = "session"
    sidebar_visible: bool = True
    input_history: list[str] = field(default_factory=list)
    history_index: int = -1
    scroll_position: int = 0
    is_processing: bool = False
    status_message: str = ""


class SessionProvider:
    """Provides session state management for TUI."""
    
    def __init__(self):
        self._state = TUISessionState()
        self._subscribers: list[Callable[[TUISessionState], None]] = []
    
    def get_state(self) -> TUISessionState:
        """Get current state."""
        return self._state
    
    def update_state(self, **kwargs) -> None:
        """Update state and notify subscribers."""
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)
        self._notify()
    
    def subscribe(self, callback: Callable[[TUISessionState], None]) -> None:
        """Subscribe to state changes."""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[TUISessionState], None]) -> None:
        """Unsubscribe from state changes."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def _notify(self) -> None:
        """Notify all subscribers."""
        for callback in self._subscribers:
            callback(self._state)
    
    # Convenience methods
    def add_input_history(self, text: str) -> None:
        """Add input to history."""
        if text and (not self._state.input_history or self._state.input_history[-1] != text):
            self._state.input_history.append(text)
        self._state.history_index = -1
    
    def get_previous_input(self) -> Optional[str]:
        """Get previous input from history."""
        if not self._state.input_history:
            return None
        self._state.history_index = min(
            self._state.history_index + 1,
            len(self._state.input_history) - 1
        )
        return self._state.input_history[-(self._state.history_index + 1)]
    
    def get_next_input(self) -> Optional[str]:
        """Get next input from history."""
        if self._state.history_index <= 0:
            self._state.history_index = -1
            return None
        self._state.history_index -= 1
        return self._state.input_history[-(self._state.history_index + 1)]
    
    def set_processing(self, is_processing: bool) -> None:
        """Set processing state."""
        self.update_state(is_processing=is_processing)
    
    def set_status(self, message: str) -> None:
        """Set status message."""
        self.update_state(status_message=message)


# Global instance
_session_provider: Optional[SessionProvider] = None


def get_session_provider() -> SessionProvider:
    """Get global session provider."""
    global _session_provider
    if _session_provider is None:
        _session_provider = SessionProvider()
    return _session_provider
