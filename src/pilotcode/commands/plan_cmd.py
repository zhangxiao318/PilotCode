"""Plan command implementation."""

from .base import CommandHandler, register_command, CommandContext

_plan_active = False
_plan_steps = []
_current_step = 0


async def plan_command(args: list[str], context: CommandContext) -> str:
    """Handle /plan command."""
    global _plan_active, _plan_steps, _current_step

    if not args:
        # Show current plan
        if not _plan_active:
            return "No active plan. Start with: /plan start <description>"

        lines = ["Current Plan:", ""]
        for i, step in enumerate(_plan_steps, 1):
            status = "✓" if i < _current_step else "▶" if i == _current_step else "○"
            lines.append(f"  {status} {i}. {step}")

        return "\n".join(lines)

    action = args[0]

    if action == "start":
        description = " ".join(args[1:]) if len(args) > 1 else "Untitled Plan"

        _plan_active = True
        _plan_steps = []
        _current_step = 1

        return f"Started plan: {description}\nAdd steps with: /plan add <step description>"

    elif action == "add":
        if not _plan_active:
            return "No active plan. Start with: /plan start"

        if len(args) < 2:
            return "Usage: /plan add <step description>"

        step = " ".join(args[1:])
        _plan_steps.append(step)

        return f"Added step {_plan_steps.index(step) + 1}: {step}"

    elif action == "next":
        if not _plan_active:
            return "No active plan"

        if _current_step < len(_plan_steps):
            step = _plan_steps[_current_step - 1]
            _current_step += 1
            return f"Next step ({_current_step - 1}/{len(_plan_steps)}): {step}"
        else:
            return "All steps completed!"

    elif action == "complete":
        if not _plan_active:
            return "No active plan"

        completed = _current_step - 1
        total = len(_plan_steps)

        _plan_active = False
        _plan_steps = []
        _current_step = 0

        return f"Plan completed! ({completed}/{total} steps)"

    elif action == "cancel":
        if not _plan_active:
            return "No active plan"

        _plan_active = False
        _plan_steps = []
        _current_step = 0

        return "Plan cancelled"

    else:
        return f"Unknown action: {action}. Use: start, add, next, complete, cancel"


register_command(
    CommandHandler(name="plan", description="Plan mode management", handler=plan_command)
)
