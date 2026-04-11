"""Workflow command for multi-agent orchestration."""

from rich.console import Console
from rich.table import Table
from rich import box

from .base import CommandHandler, register_command, CommandContext
from ..agent import (
    get_agent_manager,
    get_orchestrator,
    WorkflowStep,
    AgentStatus,
)


async def workflow_command(args: list[str], context: CommandContext) -> str:
    """Handle /workflow command."""
    console = Console()
    orchestrator = get_orchestrator()
    manager = get_agent_manager()

    if not args:
        # List workflows
        workflows = list(manager.workflows.values())

        if not workflows:
            return "No workflows found."

        table = Table(
            title="Workflows",
            box=box.ROUNDED,
        )

        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Agents", style="blue")

        for wf in workflows:
            table.add_row(
                wf.workflow_id,
                wf.name,
                wf.status.value,
                str(len(wf.agent_ids)),
            )

        console.print(table)
        return f"\nTotal: {len(workflows)} workflows"

    action = args[0]

    if action == "create":
        if len(args) < 3:
            return "Usage: /workflow create <name> <description>"

        name = args[1]
        description = " ".join(args[2:])

        workflow = manager.create_workflow(name, description)
        return f"Created workflow: {workflow.workflow_id} - {name}"

    elif action == "sequential":
        """Run sequential workflow."""
        if len(args) < 2:
            return "Usage: /workflow sequential '<prompt>'"

        prompt = " ".join(args[1:])

        # Create steps for different agent types
        steps = [
            WorkflowStep(
                step_id="plan",
                agent_type="planner",
                prompt=f"Create a plan for: {prompt}",
                output_key="plan",
            ),
            WorkflowStep(
                step_id="execute",
                agent_type="coder",
                prompt=f"Execute this plan: {{{{plan}}}}\n\nOriginal task: {prompt}",
                depends_on=["plan"],
                output_key="result",
            ),
            WorkflowStep(
                step_id="review",
                agent_type="reviewer",
                prompt=f"Review this result: {{{{result}}}}\n\nOriginal task: {prompt}",
                depends_on=["execute"],
                output_key="review",
            ),
        ]

        console.print("[bold green]Running sequential workflow...[/bold green]")

        result = await orchestrator.run_sequential(steps, {"original_prompt": prompt})

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Results:[/bold]")
            for key, value in result.results.items():
                console.print(f"\n[cyan]{key}:[/cyan]")
                console.print(str(value)[:500])

            return f"\nWorkflow completed successfully"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "parallel":
        """Run parallel workflow with multiple agents."""
        if len(args) < 2:
            return "Usage: /workflow parallel '<prompt>' [agent_types...]"

        prompt = args[1]
        agent_types = args[2:] if len(args) > 2 else ["coder", "debugger", "reviewer"]

        steps = [
            WorkflowStep(
                step_id=f"agent_{i}",
                agent_type=agent_type,
                prompt=f"{agent_type.upper()} perspective on: {prompt}",
                output_key=f"result_{i}",
            )
            for i, agent_type in enumerate(agent_types)
        ]

        console.print(
            f"[bold green]Running parallel workflow with {len(steps)} agents...[/bold green]"
        )

        result = await orchestrator.run_parallel(steps, {"original_prompt": prompt})

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Parallel Results:[/bold]")
            for key, value in result.results.items():
                console.print(f"\n[cyan]{key}:[/cyan]")
                console.print(str(value)[:300])

            return f"\nParallel workflow completed successfully"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "supervisor":
        """Run supervisor-worker pattern."""
        if len(args) < 2:
            return "Usage: /workflow supervisor '<task>' [worker_types...]"

        task = args[1]
        worker_types = args[2:] if len(args) > 2 else ["coder", "debugger"]

        console.print(
            f"[bold green]Running supervisor workflow with {len(worker_types)} workers...[/bold green]"
        )

        result = await orchestrator.run_supervisor(task, worker_types)

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Final Answer:[/bold]")
            console.print(result.results.get("final_answer", "No final answer")[:1000])

            return f"\nSupervisor workflow completed"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "debate":
        """Run debate between agents."""
        if len(args) < 2:
            return "Usage: /workflow debate '<topic>' [rounds]"

        topic = args[1]
        rounds = int(args[2]) if len(args) > 2 else 3

        agent_types = ["explainer", "reviewer", "planner"]

        console.print(f"[bold green]Starting debate on: {topic}[/bold green]")
        console.print(f"Participants: {', '.join(agent_types)}")
        console.print(f"Rounds: {rounds}\n")

        result = await orchestrator.run_debate(topic, agent_types, rounds)

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Debate Summary:[/bold]")
            for round_data in result.results.get("debate_history", []):
                console.print(f"\n[bold]Round {round_data['round']}:[/bold]")
                for resp in round_data["responses"]:
                    console.print(
                        f"  [cyan]{resp['agent']}:[/cyan] {str(resp.get('response', ''))[:200]}..."
                    )

            return f"\nDebate completed"
        else:
            return f"Debate failed"

    elif action == "show":
        if len(args) < 2:
            return "Usage: /workflow show <workflow_id>"

        workflow_id = args[1]
        workflow = manager.get_workflow(workflow_id)

        if not workflow:
            return f"Workflow not found: {workflow_id}"

        table = Table(box=box.ROUNDED)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("ID", workflow.workflow_id)
        table.add_row("Name", workflow.name)
        table.add_row("Description", workflow.description)
        table.add_row("Status", workflow.status.value)
        table.add_row("Agents", ", ".join(workflow.agent_ids) or "None")
        table.add_row("Created", workflow.created_at)

        console.print(table)
        return ""

    else:
        return f"""Unknown action: {action}

Available actions:
  /workflow                    - List workflows
  /workflow create <name> <desc> - Create workflow
  /workflow sequential '<prompt>' - Run sequential workflow
  /workflow parallel '<prompt>' [types...] - Run parallel workflow
  /workflow supervisor '<task>' [workers...] - Run supervisor workflow
  /workflow debate '<topic>' [rounds] - Run debate
  /workflow show <id>          - Show workflow details"""


register_command(
    CommandHandler(
        name="workflow",
        description="Multi-agent workflow orchestration",
        handler=workflow_command,
    )
)
