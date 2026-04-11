"""Code Intelligence Commands - LSP-powered code navigation.

This module provides code intelligence commands using the LSP Manager:
- /symbols - List code symbols in a file
- /references - Find references to a symbol
- /definitions - Go to definition
- /hover - Show type/documentation info
- /implementations - Find implementations
"""

from __future__ import annotations

import os
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

from pilotcode.types.command import CommandContext
from pilotcode.commands.base import CommandHandler, register_command
from pilotcode.services.lsp_manager import get_lsp_manager, Language
from pilotcode.utils.git import get_repo_info_sync

console = Console()


def get_language_from_file(filepath: str) -> Optional[Language]:
    """Get language from file extension."""
    ext = filepath.split(".")[-1].lower() if "." in filepath else ""

    mapping = {
        "py": Language.PYTHON,
        "js": Language.TYPESCRIPT,
        "ts": Language.TYPESCRIPT,
        "jsx": Language.TYPESCRIPT,
        "tsx": Language.TYPESCRIPT,
        "rs": Language.RUST,
        "go": Language.GO,
        "java": Language.JAVA,
    }

    return mapping.get(ext)


def format_symbol_kind(kind: int) -> str:
    """Format LSP symbol kind to human-readable string."""
    kinds = {
        1: "File",
        2: "Module",
        3: "Namespace",
        4: "Package",
        5: "Class",
        6: "Method",
        7: "Property",
        8: "Field",
        9: "Constructor",
        10: "Enum",
        11: "Interface",
        12: "Function",
        13: "Variable",
        14: "Constant",
        15: "String",
        16: "Number",
        17: "Boolean",
        18: "Array",
        19: "Object",
        20: "Key",
        21: "Null",
        22: "EnumMember",
        23: "Struct",
        24: "Event",
        25: "Operator",
        26: "TypeParameter",
    }
    return kinds.get(kind, "Unknown")


def get_symbol_icon(kind: int) -> str:
    """Get icon for symbol kind."""
    icons = {
        5: "🔷",  # Class
        6: "🔹",  # Method
        7: "⚡",  # Property
        8: "📦",  # Field
        9: "🏗️",  # Constructor
        10: "🔶",  # Enum
        11: "🔌",  # Interface
        12: "⚙️",  # Function
        13: "📍",  # Variable
        14: "🔒",  # Constant
        23: "🧱",  # Struct
    }
    return icons.get(kind, "📄")


async def symbols_command(args: list[str], context: CommandContext) -> str:
    """List code symbols in a file.

    Usage: /symbols <file_path>

    Shows all symbols (classes, functions, variables, etc.) defined in the file.
    """
    if not args or args[0] in ["--help", "-h"]:
        return """[bold]Symbols Command[/bold]

Usage: /symbols <file_path>

Lists all code symbols (classes, functions, variables, etc.) in a file.

Examples:
  /symbols src/main.py
  /symbols src/pilotcode/tools/base.py
"""

    filepath = args[0]

    # Resolve path
    import os

    if not os.path.isabs(filepath):
        filepath = os.path.join(context.cwd, filepath)

    if not os.path.exists(filepath):
        return f"[red]File not found: {filepath}[/red]"

    language = get_language_from_file(filepath)
    if not language:
        return f"[yellow]Unsupported file type: {filepath}[/yellow]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        await lsp_manager.start_server(language.value, root_path)

        # Get document symbols
        symbols = await lsp_manager.get_document_symbols(language.value, filepath)

        if not symbols:
            return f"[dim]No symbols found in {filepath}[/dim]"

        # Build tree view
        tree = Tree(f"[bold cyan]{filepath}[/bold cyan]")

        # Group symbols by kind
        symbol_groups: dict[str, list] = {}
        for symbol in symbols:
            kind_name = format_symbol_kind(symbol.get("kind", 0))
            if kind_name not in symbol_groups:
                symbol_groups[kind_name] = []
            symbol_groups[kind_name].append(symbol)

        # Add to tree
        for kind_name, kind_symbols in sorted(symbol_groups.items()):
            kind_node = tree.add(f"[bold]{kind_name}s[/bold] ({len(kind_symbols)})")
            for symbol in kind_symbols:
                name = symbol.get("name", "Unknown")
                icon = get_symbol_icon(symbol.get("kind", 0))
                location = symbol.get("location", {}).get("range", {}).get("start", {})
                line = location.get("line", 0) + 1
                kind_node.add(f"{icon} {name} [dim]:{line}[/dim]")

        console.print(tree)
        return f"\n[dim]Found {len(symbols)} symbol(s)[/dim]"

    except Exception as e:
        return f"[red]Failed to get symbols: {e}[/red]"


async def references_command(args: list[str], context: CommandContext) -> str:
    """Find references to a symbol.

    Usage: /references <file_path> <line> <character>

    Finds all references to the symbol at the specified position.
    """
    if len(args) < 3 or args[0] in ["--help", "-h"]:
        return """[bold]References Command[/bold]

Usage: /references <file_path> <line> <character>

Finds all references to the symbol at the specified position.
Line and character are 1-indexed.

Examples:
  /references src/main.py 10 5
  /references src/utils.py 25 0
"""

    filepath = args[0]
    try:
        line = int(args[1]) - 1  # Convert to 0-indexed
        character = int(args[2]) - 1  # Convert to 0-indexed
    except ValueError:
        return "[red]Line and character must be numbers[/red]"

    # Resolve path
    import os

    if not os.path.isabs(filepath):
        filepath = os.path.join(context.cwd, filepath)

    if not os.path.exists(filepath):
        return f"[red]File not found: {filepath}[/red]"

    language = get_language_from_file(filepath)
    if not language:
        return f"[yellow]Unsupported file type: {filepath}[/yellow]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        await lsp_manager.start_server(language.value, root_path)

        # Get references
        references = await lsp_manager.get_references(language.value, filepath, line, character)

        if not references:
            return "[dim]No references found[/dim]"

        # Build table
        table = Table(title=f"References ({len(references)} found)")
        table.add_column("File", style="cyan")
        table.add_column("Line", style="green", justify="right")
        table.add_column("Column", style="yellow", justify="right")

        for ref in references:
            uri = ref.get("uri", "")
            range_info = ref.get("range", {})
            start = range_info.get("start", {})
            ref_line = start.get("line", 0) + 1
            ref_char = start.get("character", 0) + 1

            # Show relative path
            rel_path = uri.replace(f"file://{root_path}/", "").replace(f"file://{root_path}", ".")

            table.add_row(rel_path, str(ref_line), str(ref_char))

        console.print(table)
        return ""

    except Exception as e:
        return f"[red]Failed to get references: {e}[/red]"


async def definitions_command(args: list[str], context: CommandContext) -> str:
    """Go to definition of a symbol.

    Usage: /definitions <file_path> <line> <character>

    Finds the definition of the symbol at the specified position.
    """
    if len(args) < 3 or args[0] in ["--help", "-h"]:
        return """[bold]Definitions Command[/bold]

Usage: /definitions <file_path> <line> <character>

Finds the definition of the symbol at the specified position.
Line and character are 1-indexed.

Examples:
  /definitions src/main.py 10 5
  /definitions src/utils.py 25 0
"""

    filepath = args[0]
    try:
        line = int(args[1]) - 1  # Convert to 0-indexed
        character = int(args[2]) - 1  # Convert to 0-indexed
    except ValueError:
        return "[red]Line and character must be numbers[/red]"

    # Resolve path
    import os

    if not os.path.isabs(filepath):
        filepath = os.path.join(context.cwd, filepath)

    if not os.path.exists(filepath):
        return f"[red]File not found: {filepath}[/red]"

    language = get_language_from_file(filepath)
    if not language:
        return f"[yellow]Unsupported file type: {filepath}[/yellow]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        await lsp_manager.start_server(language.value, root_path)

        # Get definition
        definitions = await lsp_manager.get_definition(language.value, filepath, line, character)

        if not definitions:
            return "[dim]No definition found[/dim]"

        # Build output
        for i, definition in enumerate(definitions, 1):
            uri = definition.get("uri", "")
            range_info = definition.get("range", {})
            start = range_info.get("start", {})
            range_info.get("end", {})

            def_line = start.get("line", 0) + 1
            def_char = start.get("character", 0) + 1

            # Show relative path
            rel_path = uri.replace(f"file://{root_path}/", "").replace(f"file://{root_path}", ".")

            panel_content = f"""[bold cyan]{rel_path}[/bold cyan]

[dim]Line:[/dim] {def_line}
[dim]Column:[/dim] {def_char}
"""
            console.print(
                Panel(
                    panel_content, title=f"Definition {i}/{len(definitions)}", border_style="blue"
                )
            )

        return f"[dim]Found {len(definitions)} definition(s)[/dim]"

    except Exception as e:
        return f"[red]Failed to get definition: {e}[/red]"


async def hover_command(args: list[str], context: CommandContext) -> str:
    """Show hover information for a symbol.

    Usage: /hover <file_path> <line> <character>

    Shows type information and documentation for the symbol at the position.
    """
    if len(args) < 3 or args[0] in ["--help", "-h"]:
        return """[bold]Hover Command[/bold]

Usage: /hover <file_path> <line> <character>

Shows type information and documentation for the symbol.
Line and character are 1-indexed.

Examples:
  /hover src/main.py 10 5
  /hover src/utils.py 25 0
"""

    filepath = args[0]
    try:
        line = int(args[1]) - 1  # Convert to 0-indexed
        character = int(args[2]) - 1  # Convert to 0-indexed
    except ValueError:
        return "[red]Line and character must be numbers[/red]"

    # Resolve path
    import os

    if not os.path.isabs(filepath):
        filepath = os.path.join(context.cwd, filepath)

    if not os.path.exists(filepath):
        return f"[red]File not found: {filepath}[/red]"

    language = get_language_from_file(filepath)
    if not language:
        return f"[yellow]Unsupported file type: {filepath}[/yellow]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        await lsp_manager.start_server(language.value, root_path)

        # Get hover info
        hover_info = await lsp_manager.get_hover(language.value, filepath, line, character)

        if not hover_info:
            return "[dim]No information available[/dim]"

        contents = hover_info.get("contents", "")

        # Handle markdown content
        if isinstance(contents, dict):
            value = contents.get("value", "")
            kind = contents.get("kind", "plaintext")

            if kind == "markdown":
                console.print(Panel(value, title="Hover Info", border_style="blue"))
            else:
                console.print(Panel(value, title="Hover Info", border_style="blue"))
        elif isinstance(contents, list):
            # Multiple content items
            for item in contents:
                if isinstance(item, dict):
                    value = item.get("value", "")
                    console.print(Panel(value, border_style="blue"))
                else:
                    console.print(Panel(str(item), border_style="blue"))
        else:
            console.print(Panel(str(contents), title="Hover Info", border_style="blue"))

        return ""

    except Exception as e:
        return f"[red]Failed to get hover info: {e}[/red]"


async def implementations_command(args: list[str], context: CommandContext) -> str:
    """Find implementations of an interface or abstract method.

    Usage: /implementations <file_path> <line> <character>

    Finds all implementations of the interface/method at the position.
    """
    if len(args) < 3 or args[0] in ["--help", "-h"]:
        return """[bold]Implementations Command[/bold]

Usage: /implementations <file_path> <line> <character>

Finds all implementations of the interface or method.
Line and character are 1-indexed.

Examples:
  /implementations src/main.py 10 5
  /implementations src/interfaces.py 25 0
"""

    filepath = args[0]
    try:
        line = int(args[1]) - 1  # Convert to 0-indexed
        character = int(args[2]) - 1  # Convert to 0-indexed
    except ValueError:
        return "[red]Line and character must be numbers[/red]"

    # Resolve path
    import os

    if not os.path.isabs(filepath):
        filepath = os.path.join(context.cwd, filepath)

    if not os.path.exists(filepath):
        return f"[red]File not found: {filepath}[/red]"

    language = get_language_from_file(filepath)
    if not language:
        return f"[yellow]Unsupported file type: {filepath}[/yellow]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        await lsp_manager.start_server(language.value, root_path)

        # Get implementations
        implementations = await lsp_manager.get_implementations(
            language.value, filepath, line, character
        )

        if not implementations:
            return "[dim]No implementations found[/dim]"

        # Build table
        table = Table(title=f"Implementations ({len(implementations)} found)")
        table.add_column("File", style="cyan")
        table.add_column("Line", style="green", justify="right")
        table.add_column("Column", style="yellow", justify="right")

        for impl in implementations:
            uri = impl.get("uri", "")
            range_info = impl.get("range", {})
            start = range_info.get("start", {})
            impl_line = start.get("line", 0) + 1
            impl_char = start.get("character", 0) + 1

            # Show relative path
            rel_path = uri.replace(f"file://{root_path}/", "").replace(f"file://{root_path}", ".")

            table.add_row(rel_path, str(impl_line), str(impl_char))

        console.print(table)
        return ""

    except Exception as e:
        return f"[red]Failed to get implementations: {e}[/red]"


async def workspace_symbol_command(args: list[str], context: CommandContext) -> str:
    """Search for symbols across the entire workspace.

    Usage: /workspace_symbol <query>

    Searches for symbols matching the query string across all files.
    """
    if not args or args[0] in ["--help", "-h"]:
        return """[bold]Workspace Symbol Command[/bold]

Usage: /workspace_symbol <query>

Searches for symbols across the entire workspace.

Examples:
  /workspace_symbol main
  /workspace_symbol class:MyClass
"""

    query = " ".join(args)

    if not query:
        return "[red]Query required[/red]"

    try:
        lsp_manager = get_lsp_manager()

        # Ensure server is started
        repo_info = get_repo_info_sync(context.cwd)
        root_path = repo_info.root_path if repo_info and repo_info.root_path else context.cwd

        # Try to detect language from workspace
        detected_language = None
        for ext, lang in {
            "py": Language.PYTHON,
            "js": Language.TYPESCRIPT,
            "ts": Language.TYPESCRIPT,
            "rs": Language.RUST,
            "go": Language.GO,
        }.items():
            if any(
                f.endswith(f".{ext}")
                for f in os.listdir(context.cwd)
                if os.path.isfile(os.path.join(context.cwd, f))
            ):
                detected_language = lang
                break

        if not detected_language:
            return "[yellow]Could not detect language for workspace[/yellow]"

        await lsp_manager.start_server(detected_language.value, root_path)

        # Search workspace symbols
        symbols = await lsp_manager.get_workspace_symbols(detected_language.value, query)

        if not symbols:
            return f"[dim]No symbols found matching '{query}'[/dim]"

        # Build table
        table = Table(title=f"Workspace Symbols matching '{query}' ({len(symbols)} found)")
        table.add_column("Name", style="cyan")
        table.add_column("Kind", style="blue")
        table.add_column("File", style="green")
        table.add_column("Line", style="yellow", justify="right")

        for symbol in symbols:
            name = symbol.get("name", "Unknown")
            kind = format_symbol_kind(symbol.get("kind", 0))
            location = symbol.get("location", {})
            uri = location.get("uri", "")
            range_info = location.get("range", {})
            line = range_info.get("start", {}).get("line", 0) + 1

            # Show relative path
            rel_path = uri.replace(f"file://{root_path}/", "").replace(f"file://{root_path}", ".")

            table.add_row(name, kind, rel_path, str(line))

        console.print(table)
        return ""

    except Exception as e:
        return f"[red]Failed to search workspace symbols: {e}[/red]"


# Register all commands
register_command(
    CommandHandler(
        name="symbols",
        description="List code symbols in a file",
        handler=symbols_command,
        aliases=["syms", "outline"],
    )
)

register_command(
    CommandHandler(
        name="references",
        description="Find references to a symbol",
        handler=references_command,
        aliases=["refs", "usages"],
    )
)

register_command(
    CommandHandler(
        name="definitions",
        description="Go to definition of a symbol",
        handler=definitions_command,
        aliases=["def", "goto"],
    )
)

register_command(
    CommandHandler(
        name="hover",
        description="Show type/documentation info for a symbol",
        handler=hover_command,
        aliases=["info", "type"],
    )
)

register_command(
    CommandHandler(
        name="implementations",
        description="Find implementations of an interface",
        handler=implementations_command,
        aliases=["impls"],
    )
)

register_command(
    CommandHandler(
        name="workspace_symbol",
        description="Search for symbols across workspace",
        handler=workspace_symbol_command,
        aliases=["ws_symbol", "find_symbol"],
    )
)
