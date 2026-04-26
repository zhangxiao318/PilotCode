"""Task state machine for P-EVR orchestration.

Maps to P-EVR Architecture Section 3.1:
PENDING → ASSIGNED → IN_PROGRESS → SUBMITTED → UNDER_REVIEW
                                              ↓
                                      VERIFIED / REJECTED
                                         ↓        ↓
                                        DONE  NEEDS_REWORK → IN_PROGRESS
"""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable


class TaskState(Enum):
    """States in the P-EVR task lifecycle."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REWORK = "needs_rework"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Transition(Enum):
    """Valid state transitions."""

    ASSIGN = "assign"
    START = "start"
    SUBMIT = "submit"
    BEGIN_REVIEW = "begin_review"
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REWORK = "request_rework"
    RESUME = "resume"
    COMPLETE = "complete"
    BLOCK = "block"
    UNBLOCK = "unblock"
    CANCEL = "cancel"


# Valid transitions: (from_state, transition) → to_state
TRANSITION_TABLE: dict[tuple[TaskState, Transition], TaskState] = {
    (TaskState.PENDING, Transition.ASSIGN): TaskState.ASSIGNED,
    (TaskState.PENDING, Transition.BLOCK): TaskState.BLOCKED,
    (TaskState.PENDING, Transition.CANCEL): TaskState.CANCELLED,
    (TaskState.ASSIGNED, Transition.START): TaskState.IN_PROGRESS,
    (TaskState.ASSIGNED, Transition.CANCEL): TaskState.CANCELLED,
    (TaskState.IN_PROGRESS, Transition.SUBMIT): TaskState.SUBMITTED,
    (TaskState.IN_PROGRESS, Transition.CANCEL): TaskState.CANCELLED,
    (TaskState.SUBMITTED, Transition.BEGIN_REVIEW): TaskState.UNDER_REVIEW,
    (TaskState.UNDER_REVIEW, Transition.APPROVE): TaskState.VERIFIED,
    (TaskState.UNDER_REVIEW, Transition.REJECT): TaskState.REJECTED,
    (TaskState.UNDER_REVIEW, Transition.REQUEST_REWORK): TaskState.NEEDS_REWORK,
    (TaskState.VERIFIED, Transition.COMPLETE): TaskState.DONE,
    (TaskState.REJECTED, Transition.REQUEST_REWORK): TaskState.NEEDS_REWORK,
    (TaskState.REJECTED, Transition.CANCEL): TaskState.CANCELLED,
    (TaskState.NEEDS_REWORK, Transition.RESUME): TaskState.IN_PROGRESS,
    (TaskState.NEEDS_REWORK, Transition.CANCEL): TaskState.CANCELLED,
    (TaskState.BLOCKED, Transition.UNBLOCK): TaskState.PENDING,
    (TaskState.BLOCKED, Transition.CANCEL): TaskState.CANCELLED,
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: TaskState, transition: Transition):
        self.from_state = from_state
        self.transition = transition
        super().__init__(f"Invalid transition '{transition.value}' from state '{from_state.value}'")


@dataclass
class StateChangeEvent:
    """Record of a state change."""

    task_id: str
    from_state: TaskState
    to_state: TaskState
    transition: Transition
    timestamp: str
    reason: str = ""
    actor: str = ""  # "orchestrator", "worker", "verifier", "user"


class StateMachine:
    """State machine for a single task.

    Thread-safe within a single async event loop.
    """

    def __init__(self, task_id: str, initial_state: TaskState = TaskState.PENDING):
        self.task_id = task_id
        self.state = initial_state
        self._history: list[StateChangeEvent] = []
        self._callbacks: list[Callable[[StateChangeEvent], None]] = []
        self._state_entered_at: dict[TaskState, str] = {}
        self._record_state_entry(initial_state)

    def _record_state_entry(self, state: TaskState) -> None:
        from datetime import datetime, timezone

        self._state_entered_at[state] = datetime.now(timezone.utc).isoformat()

    def on_state_change(self, callback: Callable[[StateChangeEvent], None]):
        """Register a callback for state changes."""
        self._callbacks.append(callback)

    def can_transition(self, transition: Transition) -> bool:
        """Check if a transition is valid from current state."""
        return (self.state, transition) in TRANSITION_TABLE

    def get_valid_transitions(self) -> list[Transition]:
        """Get all valid transitions from current state."""
        return [t for (s, t), _ in TRANSITION_TABLE.items() if s == self.state]

    def transition(
        self,
        transition: Transition,
        reason: str = "",
        actor: str = "orchestrator",
    ) -> TaskState:
        """Execute a state transition.

        Raises:
            InvalidTransitionError: If the transition is not valid.
        """
        key = (self.state, transition)
        if key not in TRANSITION_TABLE:
            raise InvalidTransitionError(self.state, transition)

        old_state = self.state
        new_state = TRANSITION_TABLE[key]
        self.state = new_state
        self._record_state_entry(new_state)

        from datetime import datetime, timezone

        event = StateChangeEvent(
            task_id=self.task_id,
            from_state=old_state,
            to_state=new_state,
            transition=transition,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            actor=actor,
        )
        self._history.append(event)

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                import logging

                logging.getLogger(__name__).warning("State change callback failed", exc_info=True)

        return new_state

    def time_in_current_state(self) -> float:
        """Return seconds spent in the current state."""
        entered = self._state_entered_at.get(self.state)
        if not entered:
            return 0.0
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(entered)
        return (datetime.now(timezone.utc) - dt).total_seconds()

    def get_history(self) -> list[StateChangeEvent]:
        """Get full state change history."""
        return list(self._history)

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self.state in {TaskState.DONE, TaskState.CANCELLED, TaskState.REJECTED}

    def is_active(self) -> bool:
        """Check if task is currently being worked on."""
        return self.state in {
            TaskState.ASSIGNED,
            TaskState.IN_PROGRESS,
            TaskState.SUBMITTED,
            TaskState.UNDER_REVIEW,
        }

    def is_verified(self) -> bool:
        """Check if task has passed verification (or completed)."""
        return self.state in {TaskState.VERIFIED, TaskState.DONE}

    def is_blocked(self) -> bool:
        """Check if task is blocked."""
        return self.state == TaskState.BLOCKED

    def __repr__(self) -> str:
        return f"StateMachine({self.task_id}: {self.state.value})"
