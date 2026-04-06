"""State store implementation."""

from typing import Callable, TypeVar, Generic
from dataclasses import dataclass, fields
import copy

from .app_state import AppState

T = TypeVar("T")
StateSelector = Callable[[AppState], T]
StateUpdater = Callable[[AppState], AppState]


class Store:
    """Simple state store similar to Zustand."""

    def __init__(self, initial_state: AppState):
        self._state = initial_state
        self._listeners: list[Callable[[AppState], None]] = []

    def get_state(self) -> AppState:
        """Get current state."""
        return self._state

    def set_state(self, updater: StateUpdater) -> None:
        """Update state."""
        new_state = updater(copy.deepcopy(self._state))
        self._state = new_state
        self._notify_listeners()

    def subscribe(self, listener: Callable[[AppState], None]) -> Callable[[], None]:
        """Subscribe to state changes.

        Returns unsubscribe function.
        """
        self._listeners.append(listener)

        def unsubscribe():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _notify_listeners(self) -> None:
        """Notify all listeners of state change."""
        for listener in self._listeners:
            try:
                listener(self._state)
            except Exception:
                pass

    def select(self, selector: StateSelector[T]) -> T:
        """Select a value from state."""
        return selector(self._state)


# Global store (for convenience)
_global_store: Store | None = None


def get_store() -> Store:
    """Get global store."""
    global _global_store
    if _global_store is None:
        from .app_state import get_default_app_state

        _global_store = Store(get_default_app_state())
    return _global_store


def set_global_store(store: Store) -> None:
    """Set global store."""
    global _global_store
    _global_store = store
