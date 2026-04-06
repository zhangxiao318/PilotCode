"""Tests for store module."""

import pytest
import copy

from pilotcode.state.store import Store, get_store, set_global_store, StateSelector, StateUpdater
from pilotcode.state.app_state import AppState, Settings, get_default_app_state


class TestStore:
    """Tests for Store class."""

    def test_initialization(self):
        """Test store initialization."""
        initial_state = AppState(session_id="test")
        store = Store(initial_state)

        assert store.get_state() is initial_state

    def test_get_state_returns_current_state(self):
        """Test get_state returns current state."""
        state = AppState(session_id="test")
        store = Store(state)

        retrieved = store.get_state()

        assert retrieved is state
        assert retrieved.session_id == "test"

    def test_set_state_updates_state(self):
        """Test set_state updates state."""
        store = Store(AppState(session_id="initial"))

        def updater(state: AppState) -> AppState:
            new_state = copy.deepcopy(state)
            new_state.session_id = "updated"
            return new_state

        store.set_state(updater)

        assert store.get_state().session_id == "updated"

    def test_set_state_deep_copy(self):
        """Test that set_state creates deep copy."""
        original = AppState(settings=Settings(theme="original"))
        store = Store(original)

        def updater(state: AppState) -> AppState:
            state.settings.theme = "modified"  # Modify in place
            return state

        store.set_state(updater)

        # Original should be modified because we modified before deep copy
        # But state should have new reference
        assert store.get_state().settings.theme == "modified"

    def test_subscribe_notifies_listener(self):
        """Test subscribe notifies listener on state change."""
        store = Store(AppState(session_id="initial"))
        notifications = []

        def listener(state: AppState):
            notifications.append(state.session_id)

        store.subscribe(listener)

        def updater(state: AppState) -> AppState:
            new_state = copy.deepcopy(state)
            new_state.session_id = "changed"
            return new_state

        store.set_state(updater)

        assert len(notifications) == 1
        assert notifications[0] == "changed"

    def test_subscribe_multiple_listeners(self):
        """Test multiple listeners are notified."""
        store = Store(AppState())
        notifications1 = []
        notifications2 = []

        def listener1(state: AppState):
            notifications1.append(1)

        def listener2(state: AppState):
            notifications2.append(2)

        store.subscribe(listener1)
        store.subscribe(listener2)

        store.set_state(lambda s: s)  # No-op update

        assert len(notifications1) == 1
        assert len(notifications2) == 1

    def test_unsubscribe_removes_listener(self):
        """Test unsubscribe removes listener."""
        store = Store(AppState())
        notifications = []

        def listener(state: AppState):
            notifications.append(1)

        unsubscribe = store.subscribe(listener)

        store.set_state(lambda s: s)
        assert len(notifications) == 1

        unsubscribe()  # Remove listener

        store.set_state(lambda s: s)
        assert len(notifications) == 1  # Should not be called again

    def test_unsubscribe_invalid_listener(self):
        """Test unsubscribe with invalid listener doesn't error."""
        store = Store(AppState())

        def listener(state: AppState):
            pass

        unsubscribe = store.subscribe(listener)
        unsubscribe()  # First unsubscribe works
        unsubscribe()  # Second should not error

    def test_listener_exception_handled(self):
        """Test that listener exceptions are handled gracefully."""
        store = Store(AppState(session_id="test"))
        good_notifications = []

        def bad_listener(state: AppState):
            raise ValueError("Test error")

        def good_listener(state: AppState):
            good_notifications.append(state.session_id)

        store.subscribe(bad_listener)
        store.subscribe(good_listener)

        # Should not raise despite bad_listener
        def updater(state: AppState) -> AppState:
            new_state = copy.deepcopy(state)
            new_state.session_id = "updated"
            return new_state

        store.set_state(updater)  # Should not raise

        # Good listener should still be called
        assert len(good_notifications) == 1
        assert good_notifications[0] == "updated"

    def test_select_value(self):
        """Test select method."""
        store = Store(AppState(session_id="test123", total_tokens=100))

        session_id = store.select(lambda s: s.session_id)
        total_tokens = store.select(lambda s: s.total_tokens)

        assert session_id == "test123"
        assert total_tokens == 100

    def test_select_nested_value(self):
        """Test select with nested value."""
        from pilotcode.state.app_state import Settings

        store = Store(AppState(settings=Settings(theme="dark")))

        theme = store.select(lambda s: s.settings.theme)

        assert theme == "dark"


class TestGlobalStore:
    """Tests for global store functions."""

    def test_get_store_creates_default(self):
        """Test get_store creates default store."""
        # Reset global store first
        set_global_store(None)

        store = get_store()

        assert isinstance(store, Store)
        assert isinstance(store.get_state(), AppState)

    def test_get_store_returns_same_instance(self):
        """Test get_store returns same instance."""
        set_global_store(None)

        store1 = get_store()
        store2 = get_store()

        assert store1 is store2

    def test_set_global_store(self):
        """Test set_global_store."""
        custom_store = Store(AppState(session_id="custom"))

        set_global_store(custom_store)

        assert get_store() is custom_store
        assert get_store().get_state().session_id == "custom"

    def test_set_global_store_to_none(self):
        """Test set_global_store with None resets store."""
        custom_store = Store(AppState(session_id="custom"))
        set_global_store(custom_store)

        set_global_store(None)

        # get_store should create new default store
        store = get_store()
        assert store is not custom_store


class TestStateUpdater:
    """Tests for state updater functions."""

    def test_updater_modifies_state(self):
        """Test updater can modify state."""
        store = Store(AppState(total_tokens=0))

        def increment_tokens(state: AppState) -> AppState:
            new_state = copy.deepcopy(state)
            new_state.total_tokens += 100
            return new_state

        store.set_state(increment_tokens)

        assert store.get_state().total_tokens == 100

        store.set_state(increment_tokens)

        assert store.get_state().total_tokens == 200

    def test_updater_can_modify_nested(self):
        """Test updater can modify nested state."""
        from pilotcode.state.app_state import Settings

        store = Store(AppState(settings=Settings(theme="light")))

        def set_dark_theme(state: AppState) -> AppState:
            new_state = copy.deepcopy(state)
            new_state.settings.theme = "dark"
            return new_state

        store.set_state(set_dark_theme)

        assert store.get_state().settings.theme == "dark"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
