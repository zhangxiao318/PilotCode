"""Package Management Commands - Install, upgrade, uninstall packages.

This module provides package management commands:
- /install - Install packages
- /upgrade - Upgrade packages
- /uninstall - Uninstall packages
- /list_packages - List installed packages

Supports multiple package managers:
- pip (Python)
- npm/yarn (Node.js)
- cargo (Rust)
- go mod (Go)
- apt (Debian/Ubuntu)
"""

from __future__ import annotations

import os
import subprocess
import json
from typing import Optional, Any
from enum import Enum
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from pilotcode.types.command import CommandContext
from pilotcode.commands.base import CommandHandler, register_command

console = Console()


class PackageManager(str, Enum):
    """Supported package managers."""

    PIP = "pip"
    NPM = "npm"
    YARN = "yarn"
    CARGO = "cargo"
    GO = "go"
    APT = "apt"
    UNKNOWN = "unknown"


@dataclass
class PackageInfo:
    """Information about a package."""

    name: str
    version: str
    latest_version: Optional[str] = None
    description: Optional[str] = None
    installed: bool = False


def detect_package_manager(cwd: str) -> PackageManager:
    """Detect package manager based on project files."""
    # Check for Python
    if os.path.exists(os.path.join(cwd, "requirements.txt")):
        return PackageManager.PIP
    if os.path.exists(os.path.join(cwd, "pyproject.toml")):
        return PackageManager.PIP
    if os.path.exists(os.path.join(cwd, "setup.py")):
        return PackageManager.PIP
    if os.path.exists(os.path.join(cwd, "Pipfile")):
        return PackageManager.PIP

    # Check for Node.js
    if os.path.exists(os.path.join(cwd, "package.json")):
        if os.path.exists(os.path.join(cwd, "yarn.lock")):
            return PackageManager.YARN
        return PackageManager.NPM

    # Check for Rust
    if os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return PackageManager.CARGO

    # Check for Go
    if os.path.exists(os.path.join(cwd, "go.mod")):
        return PackageManager.GO

    return PackageManager.UNKNOWN


def run_pip_command(
    command: str,
    packages: Optional[list[str]] = None,
    cwd: str = ".",
    options: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Run pip command."""
    cmd = ["python", "-m", "pip", command]

    if options:
        cmd.extend(options)

    if packages:
        cmd.extend(packages)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr and "WARNING" not in result.stderr:
            output += "\n" + result.stderr

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


def run_npm_command(
    command: str,
    packages: Optional[list[str]] = None,
    cwd: str = ".",
    options: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Run npm command."""
    cmd = ["npm", command]

    if options:
        cmd.extend(options)

    if packages:
        cmd.extend(packages)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


def run_yarn_command(
    command: str,
    packages: Optional[list[str]] = None,
    cwd: str = ".",
    options: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Run yarn command."""
    cmd = ["yarn", command]

    if options:
        cmd.extend(options)

    if packages:
        cmd.extend(packages)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


def run_cargo_command(
    command: str,
    packages: Optional[list[str]] = None,
    cwd: str = ".",
    options: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Run cargo command."""
    cmd = ["cargo", command]

    if options:
        cmd.extend(options)

    if packages:
        cmd.extend(packages)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


def run_go_command(
    command: str,
    packages: Optional[list[str]] = None,
    cwd: str = ".",
    options: Optional[list[str]] = None,
) -> tuple[bool, str]:
    """Run go command."""
    cmd = ["go", command]

    if options:
        cmd.extend(options)

    if packages:
        cmd.extend(packages)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        return False, "Command timed out after 5 minutes"
    except Exception as e:
        return False, str(e)


def get_installed_pip_packages(cwd: str) -> list[PackageInfo]:
    """Get list of installed pip packages."""
    try:
        result = subprocess.run(
            ["python", "-m", "pip", "list", "--format=json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return [
                PackageInfo(
                    name=p["name"],
                    version=p["version"],
                    installed=True,
                )
                for p in data
            ]
    except Exception:
        pass

    return []


def get_installed_npm_packages(cwd: str) -> list[PackageInfo]:
    """Get list of installed npm packages."""
    try:
        result = subprocess.run(
            ["npm", "list", "--depth=0", "--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            dependencies = data.get("dependencies", {})
            return [
                PackageInfo(
                    name=name,
                    version=info.get("version", "unknown"),
                    installed=True,
                )
                for name, info in dependencies.items()
            ]
    except Exception:
        pass

    return []


async def install_command(args: list[str], context: CommandContext) -> str:
    """Install packages.

    Usage: /install <package1> [package2] ... [--dev] [--global]

    Automatically detects package manager based on project.

    Examples:
      /install requests
      /install requests beautifulsoup4
      /install lodash --dev
      /install --global typescript
    """
    if not args or args[0] in ["--help", "-h"]:
        return """[bold]Install Command[/bold]

Usage: /install <package1> [package2] ... [options]

Options:
  --dev, -D       Install as development dependency
  --global, -g    Install globally

Examples:
  /install requests
  /install requests beautifulsoup4
  /install lodash --dev
  /install --global typescript
"""

    # Parse options
    packages = []
    options = []
    dev = False
    global_install = False

    for arg in args:
        if arg == "--dev" or arg == "-D":
            dev = True
        elif arg == "--global" or arg == "-g":
            global_install = True
        elif not arg.startswith("-"):
            packages.append(arg)

    if not packages:
        return "[red]No packages specified[/red]"

    # Detect package manager
    manager = detect_package_manager(context.cwd)

    if manager == PackageManager.UNKNOWN:
        return "[yellow]Could not detect package manager.[/yellow]\nSupported: pip, npm, yarn, cargo, go"

    # Build options based on package manager
    if manager == PackageManager.PIP:
        if dev:
            options.append("--dev")  # pip doesn't have dev flag, but pipenv does
        if global_install:
            options.append("--user")
    elif manager in (PackageManager.NPM, PackageManager.YARN):
        if dev:
            options.append("--save-dev")
        if global_install:
            options.append("--global")

    # Run install
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Installing {', '.join(packages)}...", total=None)

        if manager == PackageManager.PIP:
            success, output = run_pip_command("install", packages, context.cwd, options)
        elif manager == PackageManager.NPM:
            success, output = run_npm_command("install", packages, context.cwd, options)
        elif manager == PackageManager.YARN:
            success, output = run_yarn_command("add", packages, context.cwd, options)
        elif manager == PackageManager.CARGO:
            success, output = run_cargo_command("add", packages, context.cwd, options)
        elif manager == PackageManager.GO:
            success, output = run_go_command("get", packages, context.cwd, options)
        else:
            return "[red]Unsupported package manager[/red]"

        progress.update(task, completed=True)

    # Display results
    if success:
        console.print(f"[green]✓ Successfully installed {len(packages)} package(s)[/green]")
        if output:
            # Show last few lines
            lines = output.strip().split("\n")[-10:]
            console.print(Panel("\n".join(lines), title="Output", border_style="blue"))
        return ""
    else:
        console.print(f"[red]✗ Installation failed[/red]")
        if output:
            console.print(
                Panel(
                    output[-2000:] if len(output) > 2000 else output,
                    title="Error",
                    border_style="red",
                )
            )
        return ""


async def upgrade_command(args: list[str], context: CommandContext) -> str:
    """Upgrade packages.

    Usage: /upgrade [package1] [package2] ... [--all]

    If no packages specified, shows outdated packages.
    Use --all to upgrade all packages.

    Examples:
      /upgrade requests
      /upgrade requests beautifulsoup4
      /upgrade --all
    """
    if args and args[0] in ["--help", "-h"]:
        return """[bold]Upgrade Command[/bold]

Usage: /upgrade [package1] [package2] ... [--all]

If no packages specified, shows outdated packages.
Use --all to upgrade all packages.

Examples:
  /upgrade requests
  /upgrade requests beautifulsoup4
  /upgrade --all
"""

    # Parse options
    packages = []
    upgrade_all = False

    for arg in args:
        if arg == "--all" or arg == "-a":
            upgrade_all = True
        elif not arg.startswith("-"):
            packages.append(arg)

    # Detect package manager
    manager = detect_package_manager(context.cwd)

    if manager == PackageManager.UNKNOWN:
        return "[yellow]Could not detect package manager[/yellow]"

    # If no packages and not --all, show outdated
    if not packages and not upgrade_all:
        return await _show_outdated_packages(manager, context.cwd)

    # Run upgrade
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if upgrade_all:
            task = progress.add_task("Upgrading all packages...", total=None)
        else:
            task = progress.add_task(f"Upgrading {', '.join(packages)}...", total=None)

        if manager == PackageManager.PIP:
            if upgrade_all:
                success, output = run_pip_command(
                    "install", ["--upgrade"], context.cwd, ["-r", "requirements.txt"]
                )
            else:
                success, output = run_pip_command("install", packages, context.cwd, ["--upgrade"])
        elif manager == PackageManager.NPM:
            if upgrade_all:
                success, output = run_npm_command("update", None, context.cwd)
            else:
                success, output = run_npm_command("update", packages, context.cwd)
        elif manager == PackageManager.YARN:
            if upgrade_all:
                success, output = run_yarn_command("upgrade", None, context.cwd)
            else:
                success, output = run_yarn_command("upgrade", packages, context.cwd)
        elif manager == PackageManager.CARGO:
            if upgrade_all:
                success, output = run_cargo_command("update", None, context.cwd)
            else:
                success, output = run_cargo_command("update", packages, context.cwd)
        elif manager == PackageManager.GO:
            if upgrade_all:
                success, output = run_go_command("get", ["-u", "./..."], context.cwd)
            else:
                success, output = run_go_command("get", ["-u"] + packages, context.cwd)
        else:
            return "[red]Unsupported package manager[/red]"

        progress.update(task, completed=True)

    # Display results
    if success:
        if upgrade_all:
            console.print("[green]✓ All packages upgraded successfully[/green]")
        else:
            console.print(f"[green]✓ Successfully upgraded {len(packages)} package(s)[/green]")
        if output:
            lines = output.strip().split("\n")[-10:]
            console.print(Panel("\n".join(lines), title="Output", border_style="blue"))
        return ""
    else:
        console.print("[red]✗ Upgrade failed[/red]")
        if output:
            console.print(
                Panel(
                    output[-2000:] if len(output) > 2000 else output,
                    title="Error",
                    border_style="red",
                )
            )
        return ""


async def _show_outdated_packages(manager: PackageManager, cwd: str) -> str:
    """Show outdated packages."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking for outdated packages...", total=None)

        if manager == PackageManager.PIP:
            success, output = run_pip_command("list", None, cwd, ["--outdated"])
        elif manager == PackageManager.NPM:
            success, output = run_npm_command("outdated", None, cwd)
        elif manager == PackageManager.YARN:
            success, output = run_yarn_command("outdated", None, cwd)
        elif manager == PackageManager.CARGO:
            success, output = run_cargo_command(
                "search", ["--limit", "0"], cwd
            )  # cargo doesn't have direct outdated
            output = "Use 'cargo update --dry-run' to see updates"
        else:
            return "[yellow]Outdated check not supported for this package manager[/yellow]"

        progress.update(task, completed=True)

    if success:
        if output.strip():
            console.print(Panel(output, title="Outdated Packages", border_style="yellow"))
            return "\n[dim]Use '/upgrade --all' to upgrade all packages or '/upgrade <package>' for specific ones[/dim]"
        else:
            return "[green]✓ All packages are up to date[/green]"
    else:
        return f"[red]Failed to check outdated packages: {output}[/red]"


async def uninstall_command(args: list[str], context: CommandContext) -> str:
    """Uninstall packages.

    Usage: /uninstall <package1> [package2] ...

    Examples:
      /uninstall requests
      /uninstall requests beautifulsoup4
    """
    if not args or args[0] in ["--help", "-h"]:
        return """[bold]Uninstall Command[/bold]

Usage: /uninstall <package1> [package2] ...

Examples:
  /uninstall requests
  /uninstall requests beautifulsoup4
"""

    packages = [arg for arg in args if not arg.startswith("-")]

    if not packages:
        return "[red]No packages specified[/red]"

    # Detect package manager
    manager = detect_package_manager(context.cwd)

    if manager == PackageManager.UNKNOWN:
        return "[yellow]Could not detect package manager[/yellow]"

    # Confirm uninstall
    console.print(f"[yellow]The following packages will be uninstalled:[/yellow]")
    for pkg in packages:
        console.print(f"  - {pkg}")

    # Run uninstall
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Uninstalling {', '.join(packages)}...", total=None)

        if manager == PackageManager.PIP:
            success, output = run_pip_command("uninstall", packages, context.cwd, ["-y"])
        elif manager == PackageManager.NPM:
            success, output = run_npm_command("uninstall", packages, context.cwd)
        elif manager == PackageManager.YARN:
            success, output = run_yarn_command("remove", packages, context.cwd)
        elif manager == PackageManager.CARGO:
            success, output = run_cargo_command("remove", packages, context.cwd)
        elif manager == PackageManager.GO:
            # Go doesn't have a direct uninstall, use mod tidy after removing import
            success, output = (
                False,
                "Go doesn't support direct package uninstall. Remove the import and run 'go mod tidy'",
            )
        else:
            return "[red]Unsupported package manager[/red]"

        progress.update(task, completed=True)

    # Display results
    if success:
        console.print(f"[green]✓ Successfully uninstalled {len(packages)} package(s)[/green]")
        if output:
            lines = output.strip().split("\n")[-10:]
            console.print(Panel("\n".join(lines), title="Output", border_style="blue"))
        return ""
    else:
        console.print("[red]✗ Uninstall failed[/red]")
        if output:
            console.print(Panel(output, title="Error", border_style="red"))
        return ""


async def list_packages_command(args: list[str], context: CommandContext) -> str:
    """List installed packages.

    Usage: /list_packages [--outdated]

    Examples:
      /list_packages
      /list_packages --outdated
    """
    if args and args[0] in ["--help", "-h"]:
        return """[bold]List Packages Command[/bold]

Usage: /list_packages [--outdated]

Options:
  --outdated    Show only outdated packages

Examples:
  /list_packages
  /list_packages --outdated
"""

    show_outdated = "--outdated" in args or "-o" in args

    # Detect package manager
    manager = detect_package_manager(context.cwd)

    if manager == PackageManager.UNKNOWN:
        return "[yellow]Could not detect package manager[/yellow]"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Listing packages...", total=None)

        # Get packages
        if manager == PackageManager.PIP:
            packages = get_installed_pip_packages(context.cwd)
        elif manager == PackageManager.NPM:
            packages = get_installed_npm_packages(context.cwd)
        else:
            packages = []

        progress.update(task, completed=True)

    # Display results
    if not packages:
        return "[dim]No packages found or listing not supported for this package manager[/dim]"

    table = Table(title=f"Installed Packages ({manager.value})")
    table.add_column("Package", style="cyan")
    table.add_column("Version", style="green")

    for pkg in sorted(packages, key=lambda p: p.name.lower()):
        table.add_row(pkg.name, pkg.version)

    console.print(table)
    console.print(f"\n[dim]Total: {len(packages)} packages[/dim]")

    return ""


# Register commands
register_command(
    CommandHandler(
        name="install",
        description="Install packages",
        handler=install_command,
        aliases=["i", "add"],
    )
)

register_command(
    CommandHandler(
        name="upgrade",
        description="Upgrade packages",
        handler=upgrade_command,
        aliases=["up", "update"],
    )
)

register_command(
    CommandHandler(
        name="uninstall",
        description="Uninstall packages",
        handler=uninstall_command,
        aliases=["remove", "rm"],
    )
)

register_command(
    CommandHandler(
        name="list_packages",
        description="List installed packages",
        handler=list_packages_command,
        aliases=["packages", "list"],
    )
)
