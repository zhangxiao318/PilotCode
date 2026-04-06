"""Built-in hooks for common functionality."""

import time
from typing import Any
from dataclasses import dataclass

from rich.console import Console

from .hook_manager import HookContext, HookResult, get_hook_manager, HookType
from ..state.store import get_store

console = Console()


@dataclass
class ToolExecutionRecord:
    """Record of tool execution."""

    tool_name: str
    input_data: dict
    output_data: Any
    start_time: float
    end_time: float
    success: bool
    error: str | None = None


class LoggingHook:
    """Hook for logging tool execution."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.history: list[ToolExecutionRecord] = []

    async def pre_tool_use(self, context: HookContext) -> HookResult:
        """Log before tool use."""
        if self.verbose and context.tool_name:
            console.print(f"[dim]→ Executing {context.tool_name}...[/dim]")

        # Store start time in metadata
        context.metadata["_start_time"] = time.time()

        return HookResult(allow_execution=True)

    async def post_tool_use(self, context: HookContext) -> HookResult:
        """Log after tool use."""
        start_time = context.metadata.get("_start_time", time.time())
        end_time = time.time()
        duration = end_time - start_time

        if context.tool_name:
            status = "✓" if not context.metadata.get("error") else "✗"
            color = "green" if status == "✓" else "red"

            if self.verbose:
                console.print(
                    f"[dim][{color}]{status} {context.tool_name} ({duration:.2f}s)[/{color}][/dim]"
                )

            # Record execution
            record = ToolExecutionRecord(
                tool_name=context.tool_name,
                input_data=context.tool_input or {},
                output_data=context.tool_output,
                start_time=start_time,
                end_time=end_time,
                success=status == "✓",
                error=str(context.error) if context.error else None,
            )
            self.history.append(record)

        return HookResult(allow_execution=True)

    async def on_error(self, context: HookContext) -> HookResult:
        """Log errors."""
        if context.error:
            console.print(f"[red]Error in {context.tool_name or 'unknown'}: {context.error}[/red]")

        return HookResult(allow_execution=True)

    def get_history(self) -> list[ToolExecutionRecord]:
        """Get execution history."""
        return self.history.copy()

    def clear_history(self):
        """Clear execution history."""
        self.history.clear()

    def register(self):
        """Register with hook manager."""
        manager = get_hook_manager()
        manager.register(HookType.PRE_TOOL_USE, self.pre_tool_use, priority=100)
        manager.register(HookType.POST_TOOL_USE, self.post_tool_use, priority=-100)
        manager.register(HookType.ON_ERROR, self.on_error, priority=0)


class CostTrackingHook:
    """Hook for tracking API costs."""

    # Approximate costs per 1K tokens (example pricing)
    COSTS = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "claude-3-opus": {"input": 0.015, "output": 0.075},
        "claude-3-sonnet": {"input": 0.003, "output": 0.015},
        "default": {"input": 0.01, "output": 0.03},
    }

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.session_costs: list[dict] = []

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        # Very rough approximation: ~4 chars per token
        return len(text) // 4

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "default",
    ) -> float:
        """Calculate cost for token usage."""
        costs = self.COSTS.get(model, self.COSTS["default"])

        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]

        return input_cost + output_cost

    async def post_agent_run(self, context: HookContext) -> HookResult:
        """Track cost after agent run."""
        if context.tool_output:
            # Estimate output tokens
            output_text = str(context.tool_output)
            output_tokens = self.estimate_tokens(output_text)

            # Estimate input from metadata
            input_text = context.metadata.get("prompt", "")
            input_tokens = self.estimate_tokens(input_text)

            # Calculate cost
            model = context.metadata.get("model", "default")
            cost = self.calculate_cost(input_tokens, output_tokens, model)

            # Update totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += cost

            # Store session record
            self.session_costs.append(
                {
                    "agent_id": context.agent_id,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                }
            )

        return HookResult(allow_execution=True)

    def get_summary(self) -> dict:
        """Get cost summary."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost": self.total_cost,
            "session_count": len(self.session_costs),
        }

    def display_summary(self):
        """Display cost summary."""
        summary = self.get_summary()

        console.print("\n[bold]Cost Summary[/bold]")
        console.print(f"  Input tokens:  {summary['total_input_tokens']:,}")
        console.print(f"  Output tokens: {summary['total_output_tokens']:,}")
        console.print(f"  Total tokens:  {summary['total_tokens']:,}")
        console.print(f"  [bold green]Total cost:    ${summary['total_cost']:.4f}[/bold green]")

    def register(self):
        """Register with hook manager."""
        manager = get_hook_manager()
        manager.register(HookType.POST_AGENT_RUN, self.post_agent_run, priority=50)


class PermissionCheckHook:
    """Hook for checking permissions before tool execution."""

    # Tools that require confirmation
    DANGEROUS_TOOLS = {
        "Bash": ["rm -rf", ">", "|", "sudo", "curl", "wget"],
        "FileWrite": [],
        "FileEdit": [],
    }

    def __init__(self, auto_confirm: bool = False):
        self.auto_confirm = auto_confirm
        self._always_allow: set[str] = set()
        self._always_deny: set[str] = set()

    def is_dangerous(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        """Check if tool usage is potentially dangerous."""
        if tool_name not in self.DANGEROUS_TOOLS:
            return False, ""

        # Check bash commands
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            dangerous_patterns = self.DANGEROUS_TOOLS["Bash"]

            for pattern in dangerous_patterns:
                if pattern in command:
                    return True, f"Command contains potentially dangerous pattern: {pattern}"

        # Check file operations
        if tool_name in ("FileWrite", "FileEdit"):
            path = tool_input.get("path", "")

            # Check for sensitive paths
            sensitive_paths = ["/etc", "/usr", "/bin", "/sbin", "/sys", "/dev"]
            for sensitive in sensitive_paths:
                if path.startswith(sensitive):
                    return True, f"Path is in sensitive system directory: {sensitive}"

        return False, ""

    async def pre_tool_use(self, context: HookContext) -> HookResult:
        """Check permissions before tool use."""
        if not context.tool_name or not context.tool_input:
            return HookResult(allow_execution=True)

        tool_key = f"{context.tool_name}:{hash(str(context.tool_input))}"

        # Check always allow/deny lists
        if tool_key in self._always_allow:
            return HookResult(allow_execution=True)

        if tool_key in self._always_deny:
            return HookResult(
                allow_execution=False,
                message="Tool execution denied by user policy",
            )

        # Check if dangerous
        is_danger, reason = self.is_dangerous(context.tool_name, context.tool_input)

        if is_danger and not self.auto_confirm:
            # Use permission manager for non-TUI mode
            from ..permissions.permission_manager import get_permission_manager, PermissionRequest

            pm = get_permission_manager()
            request = PermissionRequest(
                tool_name=context.tool_name,
                tool_input=context.tool_input,
                description=f"Execute {context.tool_name}",
                risk_level="high",
            )

            # Check if already permitted
            is_permitted, perm_reason = pm.check_permission(context.tool_name, context.tool_input)
            if is_permitted:
                return HookResult(allow_execution=True)

            # In non-TUI mode, auto-allow dangerous operations for now
            # TODO: Add simple CLI permission prompt
            return HookResult(allow_execution=True)

        return HookResult(allow_execution=True)

    def register(self):
        """Register with hook manager."""
        manager = get_hook_manager()
        manager.register(HookType.PRE_TOOL_USE, self.pre_tool_use, priority=200)


class MetricsHook:
    """Hook for collecting metrics."""

    def __init__(self):
        self.tool_counts: dict[str, int] = {}
        self.agent_counts: dict[str, int] = {}
        self.total_executions = 0
        self.failed_executions = 0

    async def post_tool_use(self, context: HookContext) -> HookResult:
        """Track tool usage metrics."""
        self.total_executions += 1

        if context.tool_name:
            self.tool_counts[context.tool_name] = self.tool_counts.get(context.tool_name, 0) + 1

        if context.error:
            self.failed_executions += 1

        return HookResult(allow_execution=True)

    async def post_agent_run(self, context: HookContext) -> HookResult:
        """Track agent usage metrics."""
        if context.agent_id:
            self.agent_counts[context.agent_id] = self.agent_counts.get(context.agent_id, 0) + 1

        return HookResult(allow_execution=True)

    def get_metrics(self) -> dict:
        """Get collected metrics."""
        return {
            "total_executions": self.total_executions,
            "failed_executions": self.failed_executions,
            "success_rate": 1.0 - (self.failed_executions / max(self.total_executions, 1)),
            "tool_usage": self.tool_counts.copy(),
            "agent_usage": self.agent_counts.copy(),
        }

    def display_metrics(self):
        """Display metrics."""
        metrics = self.get_metrics()

        console.print("\n[bold]Execution Metrics[/bold]")
        console.print(f"  Total executions: {metrics['total_executions']}")
        console.print(f"  Failed: {metrics['failed_executions']}")
        console.print(f"  Success rate: {metrics['success_rate']:.1%}")

        if metrics["tool_usage"]:
            console.print("\n  Tool usage:")
            for tool, count in sorted(metrics["tool_usage"].items(), key=lambda x: -x[1]):
                console.print(f"    {tool}: {count}")

    def register(self):
        """Register with hook manager."""
        manager = get_hook_manager()
        manager.register(HookType.POST_TOOL_USE, self.post_tool_use, priority=-50)
        manager.register(HookType.POST_AGENT_RUN, self.post_agent_run, priority=-50)


def setup_builtin_hooks(
    verbose: bool = False,
    auto_confirm: bool = False,
    track_costs: bool = True,
    track_metrics: bool = True,
):
    """Set up all built-in hooks.

    Args:
        verbose: Enable verbose logging
        auto_confirm: Auto-confirm dangerous operations
        track_costs: Enable cost tracking
        track_metrics: Enable metrics tracking
    """
    # Logging hook
    logging_hook = LoggingHook(verbose=verbose)
    logging_hook.register()

    # Permission check hook
    permission_hook = PermissionCheckHook(auto_confirm=auto_confirm)
    permission_hook.register()

    # Cost tracking hook
    if track_costs:
        cost_hook = CostTrackingHook()
        cost_hook.register()

    # Metrics hook
    if track_metrics:
        metrics_hook = MetricsHook()
        metrics_hook.register()

    console.print("[dim]Built-in hooks initialized[/dim]")
