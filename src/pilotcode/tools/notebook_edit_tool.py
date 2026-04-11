"""Notebook Edit Tool for editing Jupyter notebooks."""

import json
from typing import Any
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class NotebookEditInput(BaseModel):
    """Input for NotebookEdit tool."""

    notebook_path: str = Field(description="Path to the notebook file")
    action: str = Field(description="Action: 'read', 'edit_cell', 'add_cell', 'delete_cell'")
    cell_index: int | None = Field(default=None, description="Cell index for edit/delete")
    cell_type: str | None = Field(default=None, description="Cell type: 'code' or 'markdown'")
    source: str | None = Field(default=None, description="Cell content")
    new_source: str | None = Field(default=None, description="New content for edit")


class NotebookCell(BaseModel):
    """Notebook cell."""

    cell_type: str
    source: str | list[str]
    metadata: dict = {}
    outputs: list = []


class NotebookOutput(BaseModel):
    """Output from NotebookEdit tool."""

    notebook_path: str
    action: str
    cells: list[NotebookCell] | None = None
    cell_count: int = 0
    message: str = ""


def read_notebook(notebook_path: str) -> dict:
    """Read notebook file."""
    with open(notebook_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_notebook(notebook_path: str, notebook: dict) -> None:
    """Write notebook file."""
    with open(notebook_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=2)


async def notebook_edit_call(
    input_data: NotebookEditInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[NotebookOutput]:
    """Execute notebook edit."""
    try:
        notebook = read_notebook(input_data.notebook_path)
        cells = notebook.get("cells", [])

        if input_data.action == "read":
            return ToolResult(
                data=NotebookOutput(
                    notebook_path=input_data.notebook_path,
                    action=input_data.action,
                    cells=[NotebookCell(**cell) for cell in cells],
                    cell_count=len(cells),
                    message=f"Read {len(cells)} cells",
                )
            )

        elif input_data.action == "edit_cell":
            if input_data.cell_index is None or input_data.new_source is None:
                return ToolResult(
                    data=NotebookOutput(
                        notebook_path=input_data.notebook_path, action=input_data.action
                    ),
                    error="cell_index and new_source required for edit",
                )

            if input_data.cell_index >= len(cells):
                return ToolResult(
                    data=NotebookOutput(
                        notebook_path=input_data.notebook_path, action=input_data.action
                    ),
                    error=f"Cell index {input_data.cell_index} out of range",
                )

            cells[input_data.cell_index]["source"] = input_data.new_source.split("\n")
            write_notebook(input_data.notebook_path, notebook)

            return ToolResult(
                data=NotebookOutput(
                    notebook_path=input_data.notebook_path,
                    action=input_data.action,
                    cell_count=len(cells),
                    message=f"Edited cell {input_data.cell_index}",
                )
            )

        elif input_data.action == "add_cell":
            if not input_data.cell_type or input_data.source is None:
                return ToolResult(
                    data=NotebookOutput(
                        notebook_path=input_data.notebook_path, action=input_data.action
                    ),
                    error="cell_type and source required for add",
                )

            new_cell = {
                "cell_type": input_data.cell_type,
                "source": input_data.source.split("\n"),
                "metadata": {},
            }

            if input_data.cell_type == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None

            insert_index = (
                input_data.cell_index if input_data.cell_index is not None else len(cells)
            )
            cells.insert(insert_index, new_cell)
            write_notebook(input_data.notebook_path, notebook)

            return ToolResult(
                data=NotebookOutput(
                    notebook_path=input_data.notebook_path,
                    action=input_data.action,
                    cell_count=len(cells),
                    message=f"Added {input_data.cell_type} cell at index {insert_index}",
                )
            )

        elif input_data.action == "delete_cell":
            if input_data.cell_index is None:
                return ToolResult(
                    data=NotebookOutput(
                        notebook_path=input_data.notebook_path, action=input_data.action
                    ),
                    error="cell_index required for delete",
                )

            if input_data.cell_index >= len(cells):
                return ToolResult(
                    data=NotebookOutput(
                        notebook_path=input_data.notebook_path, action=input_data.action
                    ),
                    error=f"Cell index {input_data.cell_index} out of range",
                )

            deleted = cells.pop(input_data.cell_index)
            write_notebook(input_data.notebook_path, notebook)

            return ToolResult(
                data=NotebookOutput(
                    notebook_path=input_data.notebook_path,
                    action=input_data.action,
                    cell_count=len(cells),
                    message=f"Deleted {deleted.get('cell_type')} cell at index {input_data.cell_index}",
                )
            )

        else:
            return ToolResult(
                data=NotebookOutput(
                    notebook_path=input_data.notebook_path, action=input_data.action
                ),
                error=f"Unknown action: {input_data.action}",
            )

    except Exception as e:
        return ToolResult(
            data=NotebookOutput(notebook_path=input_data.notebook_path, action=input_data.action),
            error=str(e),
        )


async def notebook_description(input_data: NotebookEditInput, options: dict[str, Any]) -> str:
    """Get description for notebook edit."""
    return f"Notebook {input_data.action}: {input_data.notebook_path}"


# Create the NotebookEdit tool
NotebookEditTool = build_tool(
    name="NotebookEdit",
    description=notebook_description,
    input_schema=NotebookEditInput,
    output_schema=NotebookOutput,
    call=notebook_edit_call,
    aliases=["notebook", "jupyter", "ipynb"],
    search_hint="Edit Jupyter notebook files",
    is_read_only=lambda x: x.action == "read" if x else True,
    is_concurrency_safe=lambda x: x.action == "read" if x else True,
)

register_tool(NotebookEditTool)
