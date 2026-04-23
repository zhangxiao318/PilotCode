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
            return "Usage: /workflow sequential '<prompt>' [--agents <types>]"

        # Parse --agents parameter
        prompt_parts = []
        agent_types = ["planner", "coder", "reviewer"]
        i = 1
        while i < len(args):
            if args[i] == "--agents" and i + 1 < len(args):
                agent_types = [a.strip() for a in args[i + 1].split(",")]
                i += 2
            else:
                prompt_parts.append(args[i])
                i += 1

        prompt = " ".join(prompt_parts)
        if not prompt:
            return "Usage: /workflow sequential '<prompt>' [--agents <types>]"

        # Build steps from specified agent types
        steps = []
        for idx, agent_type in enumerate(agent_types):
            step_id = f"step_{idx}"
            depends_on = [f"step_{idx - 1}"] if idx > 0 else []
            if idx == 0:
                step_prompt = f"Create a plan for: {prompt}"
                output_key = "plan"
            elif idx == len(agent_types) - 1:
                prev_key = f"step_{idx - 1}"
                step_prompt = f"Review this result: {{{{{prev_key}}}}}\n\nOriginal task: {prompt}"
                output_key = "review"
            else:
                prev_key = f"step_{idx - 1}"
                step_prompt = f"Execute this plan: {{{{{prev_key}}}}}\n\nOriginal task: {prompt}"
                output_key = f"result_{idx}"

            steps.append(
                WorkflowStep(
                    step_id=step_id,
                    agent_type=agent_type,
                    prompt=step_prompt,
                    depends_on=depends_on,
                    output_key=output_key,
                )
            )

        console.print("[bold green]Running sequential workflow...[/bold green]")

        result = await orchestrator.run_sequential(steps, {"original_prompt": prompt})

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Results:[/bold]")
            for key, value in result.results.items():
                console.print(f"\n[cyan]{key}:[/cyan]")
                console.print(str(value)[:500])

            return "\nWorkflow completed successfully"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "parallel":
        """Run parallel workflow with multiple agents."""
        if len(args) < 2:
            return "Usage: /workflow parallel '<prompt>' [--agents <types>]"

        # Parse --agents parameter
        prompt_parts = []
        agent_types = ["coder", "debugger", "reviewer"]
        i = 1
        while i < len(args):
            if args[i] == "--agents" and i + 1 < len(args):
                agent_types = [a.strip() for a in args[i + 1].split(",")]
                i += 2
            else:
                prompt_parts.append(args[i])
                i += 1

        prompt = " ".join(prompt_parts)
        if not prompt:
            return "Usage: /workflow parallel '<prompt>' [--agents <types>]"

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

            return "\nParallel workflow completed successfully"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "supervisor":
        """Run supervisor-worker pattern."""
        if len(args) < 2:
            return "Usage: /workflow supervisor '<task>' [--supervisor <type>] [--workers <types>]"

        # Parse --supervisor and --workers parameters
        task_parts = []
        supervisor_type = "planner"
        worker_types = None
        i = 1
        while i < len(args):
            if args[i] == "--supervisor" and i + 1 < len(args):
                supervisor_type = args[i + 1]
                i += 2
            elif args[i] == "--workers" and i + 1 < len(args):
                worker_types = [w.strip() for w in args[i + 1].split(",")]
                i += 2
            else:
                task_parts.append(args[i])
                i += 1

        task = " ".join(task_parts)
        if not task:
            return "Usage: /workflow supervisor '<task>' [--supervisor <type>] [--workers <types>]"

        if worker_types is None:
            worker_types = ["coder", "debugger"]

        console.print(
            f"[bold green]Running supervisor workflow with {len(worker_types)} workers "
            f"(supervisor: {supervisor_type})...[/bold green]"
        )

        result = await orchestrator.run_supervisor(
            task, worker_types, supervisor_type=supervisor_type
        )

        if result.status == AgentStatus.COMPLETED:
            console.print("\n[bold]Final Answer:[/bold]")
            console.print(result.results.get("final_answer", "No final answer")[:1000])

            return "\nSupervisor workflow completed"
        else:
            return f"Workflow failed: {', '.join(result.errors)}"

    elif action == "debate":
        """Run debate between agents."""
        if len(args) < 2:
            return "Usage: /workflow debate '<topic>' [--agents <types>] [--rounds <n>]"

        # Parse --agents and --rounds parameters
        topic_parts = []
        agent_types = ["explainer", "reviewer", "planner"]
        rounds = 3
        i = 1
        while i < len(args):
            if args[i] == "--agents" and i + 1 < len(args):
                agent_types = [a.strip() for a in args[i + 1].split(",")]
                i += 2
            elif args[i] == "--rounds" and i + 1 < len(args):
                try:
                    rounds = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                topic_parts.append(args[i])
                i += 1

        topic = " ".join(topic_parts)
        if not topic:
            return "Usage: /workflow debate '<topic>' [--agents <types>] [--rounds <n>]"

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

            return "\nDebate completed"
        else:
            return "Debate failed"

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
  /workflow sequential '<prompt>' [--agents <types>] - Run sequential workflow
  /workflow parallel '<prompt>' [--agents <types>] - Run parallel workflow
  /workflow supervisor '<task>' [--supervisor <type>] [--workers <types>] - Run supervisor workflow
  /workflow debate '<topic>' [--agents <types>] [--rounds <n>] - Run debate
  /workflow show <id>          - Show workflow details"""


register_command(
    CommandHandler(
        name="workflow",
        description="Multi-agent workflow orchestration",
        handler=workflow_command,
    )
)
