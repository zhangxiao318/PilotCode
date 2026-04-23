"""Enhanced agents command implementation."""

from rich.table import Table
from rich.tree import Tree
from rich import box

from .base import CommandHandler, register_command, CommandContext
from ..agent import get_agent_manager, AgentStatus, ENHANCED_AGENT_DEFINITIONS


async def agents_command(args: list[str], context: CommandContext) -> str:
    """Handle /agents command."""
    from rich.console import Console

    console = Console()

    manager = get_agent_manager()

    if not args:
        # List all agents
        agents = manager.list_agents()

        if not agents:
            return "No agents found. Use '/agents create <type>' to create one."

        table = Table(
            title="Agent Status",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
        )

        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="yellow")
        table.add_column("Turns", justify="right")
        table.add_column("Parent", style="dim")

        for agent in agents:
            status_color = {
                AgentStatus.PENDING: "dim",
                AgentStatus.RUNNING: "bold green",
                AgentStatus.PAUSED: "yellow",
                AgentStatus.COMPLETED: "blue",
                AgentStatus.FAILED: "red",
                AgentStatus.CANCELLED: "dim",
            }.get(agent.status, "white")

            table.add_row(
                agent.agent_id,
                agent.definition.name,
                agent.definition.name,
                f"[{status_color}]{agent.status.value}[/{status_color}]",
                str(agent.turns),
                agent.parent_id or "-",
            )

        console.print(table)
        return f"\nTotal: {len(agents)} agents"

    action = args[0]

    if action == "create":
        if len(args) < 2:
            types_list = ", ".join(ENHANCED_AGENT_DEFINITIONS.keys())
            return f"Usage: /agents create <type> [name]\nAvailable types: {types_list}"

        agent_type = args[1]
        name = args[2] if len(args) > 2 else None

        if agent_type not in ENHANCED_AGENT_DEFINITIONS:
            types_list = ", ".join(ENHANCED_AGENT_DEFINITIONS.keys())
            return f"Unknown agent type: {agent_type}\nAvailable: {types_list}"

        agent = manager.create_agent(agent_type=agent_type, name=name)

        # Show agent info
        definition = agent.definition
        return f"""Created agent:
  ID: {agent.agent_id}
  Name: {definition.name}
  Description: {definition.description}
  Allowed tools: {", ".join(definition.allowed_tools[:5])}..."""

    elif action == "show":
        if len(args) < 2:
            return "Usage: /agents show <agent_id>"

        agent_id = args[1]
        agent = manager.get_agent(agent_id)

        if not agent:
            return f"Agent not found: {agent_id}"

        definition = agent.definition

        table = Table(box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("ID", agent.agent_id)
        table.add_row("Name", definition.name)
        table.add_row("Description", definition.description)
        table.add_row("Status", agent.status.value)
        table.add_row("Turns", str(agent.turns))
        table.add_row("Max Turns", str(agent.max_turns))
        table.add_row("Model", definition.model or "default")
        table.add_row("Temperature", str(definition.temperature))
        table.add_row("Parent", agent.parent_id or "None")
        table.add_row("Children", ", ".join(agent.child_ids) or "None")
        table.add_row("Created", agent.created_at)

        if agent.started_at:
            table.add_row("Started", agent.started_at)
        if agent.completed_at:
            table.add_row("Completed", agent.completed_at)

        console.print(table)

        if agent.output:
            console.print("\n[bold]Output:[/bold]")
            console.print(agent.output[:1000])

        return ""

    elif action == "tree":
        if len(args) < 2:
            return "Usage: /agents tree <agent_id>"

        agent_id = args[1]
        tree_data = manager.get_agent_tree(agent_id)

        if not tree_data:
            return f"Agent not found: {agent_id}"

        def build_tree(data, tree=None):
            agent_data = data["agent"]
            name = agent_data["definition"]["name"]
            agent_id = agent_data["agent_id"]
            status = agent_data["status"]

            label = f"{name} ({agent_id}) [{status}]"

            if tree is None:
                tree = Tree(label)
            else:
                tree = tree.add(label)

            for child in data.get("children", []):
                build_tree(child, tree)

            return tree

        tree = build_tree(tree_data)
        console.print(tree)
        return ""

    elif action == "types":
        """List available agent types."""
        table = Table(
            title="Available Agent Types",
            box=box.ROUNDED,
        )

        table.add_column("Type", style="cyan")
        table.add_column("Icon", style="yellow")
        table.add_column("Description", style="white")
        table.add_column("Tools", style="dim")

        for agent_type, definition in ENHANCED_AGENT_DEFINITIONS.items():
            tools_preview = ", ".join(definition.allowed_tools[:3])
            if len(definition.allowed_tools) > 3:
                tools_preview += "..."

            table.add_row(
                agent_type,
                definition.icon,
                definition.description,
                tools_preview,
            )

        console.print(table)
        return ""

    elif action == "delete":
        if len(args) < 2:
            return "Usage: /agents delete <agent_id>"

        agent_id = args[1]

        if manager.delete_agent(agent_id):
            return f"Deleted agent: {agent_id}"
        else:
            return f"Agent not found: {agent_id}"

    elif action == "clear":
        """Clear all completed/failed agents."""
        agents = manager.list_agents()
        cleared = 0

        for agent in agents:
            if agent.status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED):
                manager.delete_agent(agent.agent_id)
                cleared += 1

        return f"Cleared {cleared} agents"

    else:
        return f"""Unknown action: {action}

Available actions:
  /agents                    - List all agents
  /agents create <type> [name] - Create new agent
  /agents show <id>          - Show agent details
  /agents tree <id>          - Show agent tree
  /agents types              - List available types
  /agents delete <id>        - Delete agent
  /agents clear              - Clear completed agents"""


register_command(
    CommandHandler(
        name="agents",
        description="Manage sub-agents",
        handler=agents_command,
    )
)
