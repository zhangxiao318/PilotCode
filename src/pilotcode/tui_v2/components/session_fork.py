"""Session forking functionality for creating conversation branches."""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.containers import Horizontal
from textual.message import Message

from pilotcode.tui_v2.controller.controller import UIMessage, UIMessageType
from pilotcode.types.message import MessageType


class SessionForked(Message):
    """Message sent when a session is forked."""

    def __init__(self, parent_id: str, fork_id: str, fork_name: str):
        self.parent_id = parent_id
        self.fork_id = fork_id
        self.fork_name = fork_name
        super().__init__()


class SessionForkManager:
    """Manages session forking and branching.

    Provides functionality to:
    - Fork a session from any point
    - List child sessions (branches)
    - Navigate between parent and child sessions
    - Export/import session branches
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path.home() / ".pilotcode" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._forks: Dict[str, List[Dict[str, Any]]] = {}  # parent_id -> list of forks
        self._load_forks()

    def _load_forks(self):
        """Load fork relationships from storage."""
        forks_file = self.storage_dir / "forks.json"
        if forks_file.exists():
            try:
                with open(forks_file, "r") as f:
                    self._forks = json.load(f)
            except Exception:
                self._forks = {}

    def _save_forks(self):
        """Save fork relationships to storage."""
        forks_file = self.storage_dir / "forks.json"
        try:
            with open(forks_file, "w") as f:
                json.dump(self._forks, f, indent=2)
        except Exception as e:
            print(f"Failed to save forks: {e}")

    def fork_session(
        self,
        parent_id: str,
        messages: List[UIMessage],
        fork_at_index: int,
        fork_name: Optional[str] = None,
    ) -> str:
        """Fork a session at a specific message index.

        Args:
            parent_id: ID of the parent session
            messages: All messages in the parent session
            fork_at_index: Index to fork at (messages up to this index are copied)
            fork_name: Optional name for the fork

        Returns:
            The new fork session ID
        """
        import uuid

        fork_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        # Create fork info
        fork_info = {
            "id": fork_id,
            "parent_id": parent_id,
            "name": fork_name or f"fork-{fork_id[:4]}",
            "forked_at": timestamp,
            "fork_at_index": fork_at_index,
            "message_count": fork_at_index + 1,
        }

        # Save fork messages
        fork_messages = messages[: fork_at_index + 1]
        self._save_session_messages(fork_id, fork_messages)

        # Update fork relationships
        if parent_id not in self._forks:
            self._forks[parent_id] = []
        self._forks[parent_id].append(fork_info)
        self._save_forks()

        return fork_id

    def get_forks(self, parent_id: str) -> List[Dict[str, Any]]:
        """Get all forks of a session."""
        return self._forks.get(parent_id, [])

    def get_parent(self, fork_id: str) -> Optional[str]:
        """Get parent session ID of a fork."""
        for parent_id, forks in self._forks.items():
            for fork in forks:
                if fork["id"] == fork_id:
                    return parent_id
        return None

    def _save_session_messages(self, session_id: str, messages: List[UIMessage]):
        """Save session messages to disk."""
        session_file = self.storage_dir / f"{session_id}.json"

        data = {
            "session_id": session_id,
            "saved_at": datetime.now().isoformat(),
            "messages": [
                {
                    "type": msg.type.name,
                    "content": msg.content,
                    "metadata": msg.metadata,
                    "is_complete": msg.is_complete,
                    "is_streaming": msg.is_streaming,
                }
                for msg in messages
            ],
        }

        try:
            with open(session_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save session: {e}")

    def load_session_messages(self, session_id: str) -> Optional[List[UIMessage]]:
        """Load session messages from disk."""
        session_file = self.storage_dir / f"{session_id}.json"

        if not session_file.exists():
            return None

        try:
            with open(session_file, "r") as f:
                data = json.load(f)

            messages = []
            for msg_data in data.get("messages", []):
                msg = UIMessage(
                    type=MessageType[msg_data["type"]],
                    content=msg_data.get("content", ""),
                    metadata=msg_data.get("metadata", {}),
                    is_complete=msg_data.get("is_complete", True),
                    is_streaming=msg_data.get("is_streaming", False),
                )
                messages.append(msg)

            return messages
        except Exception as e:
            print(f"Failed to load session: {e}")
            return None

    def delete_fork(self, parent_id: str, fork_id: str) -> bool:
        """Delete a fork."""
        if parent_id not in self._forks:
            return False

        self._forks[parent_id] = [f for f in self._forks[parent_id] if f["id"] != fork_id]

        # Delete fork file
        fork_file = self.storage_dir / f"{fork_id}.json"
        try:
            fork_file.unlink(missing_ok=True)
        except Exception:
            pass

        self._save_forks()
        return True

    def rename_fork(self, parent_id: str, fork_id: str, new_name: str) -> bool:
        """Rename a fork."""
        if parent_id not in self._forks:
            return False

        for fork in self._forks[parent_id]:
            if fork["id"] == fork_id:
                fork["name"] = new_name
                self._save_forks()
                return True

        return False


class ForkDialog(Static):
    """Dialog for forking a session.

    Allows users to:
    - Choose a message to fork from
    - Name the fork
    - See existing forks
    """

    DEFAULT_CSS = """
    ForkDialog {
        width: 60;
        height: auto;
        max-height: 40;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }
    
    ForkDialog Static.title {
        height: 1;
        content-align: center middle;
        text-style: bold;
        color: $primary;
    }
    
    ForkDialog ListView {
        height: auto;
        max-height: 20;
        border: solid $border;
        margin: 1 0;
    }
    
    ForkDialog ListView > ListItem {
        height: 1;
        padding: 0 1;
    }
    
    ForkDialog ListView > ListItem.--highlight {
        background: $primary;
        color: $text;
    }
    
    ForkDialog Button {
        width: auto;
        margin: 0 1;
    }
    
    ForkDialog Horizontal {
        height: auto;
        align: center middle;
    }
    """

    def __init__(
        self, messages: List[UIMessage], session_id: str, fork_manager: SessionForkManager, **kwargs
    ):
        super().__init__(**kwargs)
        self.messages = messages
        self.session_id = session_id
        self.fork_manager = fork_manager
        self._selected_index: Optional[int] = None

    def compose(self):
        """Compose the dialog."""
        yield Static("🔀 Fork Session", classes="title")
        yield Static("Select a message to fork from:")

        # List of messages
        list_view = ListView()
        for idx, msg in enumerate(self.messages):
            if msg.type in (MessageType.USER, MessageType.ASSISTANT):
                preview = (msg.content or "")[:50]
                if len(msg.content or "") > 50:
                    preview += "..."
                label = f"{idx}: [{msg.type.name}] {preview}"
                list_view.append(ListItem(Label(label), id=f"msg-{idx}"))
        yield list_view

        # Buttons
        with Horizontal():
            yield Button("Fork", id="fork-btn", variant="primary")
            yield Button("Cancel", id="cancel-btn")

    def on_list_view_selected(self, event: ListView.Selected):
        """Handle message selection."""
        item_id = event.item.id
        if item_id and item_id.startswith("msg-"):
            self._selected_index = int(item_id.split("-")[1])

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button presses."""
        if event.button.id == "fork-btn":
            if self._selected_index is not None:
                self._do_fork()
            else:
                self.notify("Please select a message first", severity="warning")
        elif event.button.id == "cancel-btn":
            self.remove()

    def _do_fork(self):
        """Perform the fork operation."""
        if self._selected_index is None:
            return

        fork_id = self.fork_manager.fork_session(
            self.session_id,
            self.messages,
            self._selected_index,
            f"fork-from-{self._selected_index}",
        )

        self.post_message(
            SessionForked(self.session_id, fork_id, f"fork-from-{self._selected_index}")
        )

        self.notify(f"Session forked! ID: {fork_id}", severity="success")
        self.remove()


class ForkNavigator(Static):
    """Widget for navigating between parent and child sessions (forks)."""

    DEFAULT_CSS = """
    ForkNavigator {
        width: 100%;
        height: auto;
        background: $surface;
        border-bottom: solid $border;
        padding: 0 1;
    }
    
    ForkNavigator Static.fork-info {
        width: auto;
        height: 1;
        color: $text-muted;
        text-style: dim;
    }
    
    ForkNavigator Button {
        width: auto;
        height: 1;
        padding: 0 1;
        margin: 0;
    }
    """

    def __init__(self, current_session_id: str, fork_manager: SessionForkManager, **kwargs):
        super().__init__(**kwargs)
        self.current_session_id = current_session_id
        self.fork_manager = fork_manager

    def compose(self):
        """Compose the navigator."""
        # Check if current session has parent
        parent_id = self.fork_manager.get_parent(self.current_session_id)
        if parent_id:
            yield Static(f"↰ Parent: {parent_id[:8]}", classes="fork-info")

        # Check if current session has children
        forks = self.fork_manager.get_forks(self.current_session_id)
        if forks:
            yield Static(f"↳ {len(forks)} fork(s)", classes="fork-info")
            for fork in forks:
                yield Button(f"📁 {fork['name']}", id=f"fork-{fork['id']}", variant="primary")

    def on_button_pressed(self, event: Button.Pressed):
        """Handle fork button press."""
        if event.button.id and event.button.id.startswith("fork-"):
            fork_id = event.button.id.split("-", 1)[1]
            # Emit message to navigate to fork
            self.post_message(SessionForked(self.current_session_id, fork_id, event.button.label))
