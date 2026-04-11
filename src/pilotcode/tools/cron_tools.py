"""Cron tools for scheduled tasks."""

import json
import os
from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool
from .registry import register_tool

CRON_FILE = os.path.expanduser("~/.local/share/pilotcode/cron.json")


def ensure_cron_dir():
    """Ensure cron directory exists."""
    os.makedirs(os.path.dirname(CRON_FILE), exist_ok=True)


def load_cron_jobs():
    """Load cron jobs."""
    if os.path.exists(CRON_FILE):
        try:
            with open(CRON_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cron_jobs(jobs):
    """Save cron jobs."""
    ensure_cron_dir()
    with open(CRON_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


class CronCreateInput(BaseModel):
    """Input for CronCreate tool."""

    name: str = Field(description="Cron job name")
    command: str = Field(description="Command to execute")
    schedule: str = Field(description="Schedule expression (e.g., '0 9 * * *' for 9am daily)")
    description: str | None = Field(default=None, description="Job description")


class CronCreateOutput(BaseModel):
    """Output from CronCreate tool."""

    job_id: str
    name: str
    schedule: str
    message: str


async def cron_create_call(
    input_data: CronCreateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CronCreateOutput]:
    """Create a cron job."""
    jobs = load_cron_jobs()

    job_id = f"cron_{len(jobs) + 1}"

    jobs[job_id] = {
        "name": input_data.name,
        "command": input_data.command,
        "schedule": input_data.schedule,
        "description": input_data.description,
        "created_at": datetime.now().isoformat(),
        "enabled": True,
        "last_run": None,
        "run_count": 0,
    }

    save_cron_jobs(jobs)

    return ToolResult(
        data=CronCreateOutput(
            job_id=job_id,
            name=input_data.name,
            schedule=input_data.schedule,
            message=f"Created cron job: {input_data.name} ({input_data.schedule})",
        )
    )


class CronDeleteInput(BaseModel):
    """Input for CronDelete tool."""

    job_id: str = Field(description="Job ID to delete")


class CronDeleteOutput(BaseModel):
    """Output from CronDelete tool."""

    job_id: str
    success: bool
    message: str


async def cron_delete_call(
    input_data: CronDeleteInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CronDeleteOutput]:
    """Delete a cron job."""
    jobs = load_cron_jobs()

    if input_data.job_id not in jobs:
        return ToolResult(
            data=CronDeleteOutput(
                job_id=input_data.job_id,
                success=False,
                message=f"Job not found: {input_data.job_id}",
            )
        )

    deleted_name = jobs[input_data.job_id]["name"]
    del jobs[input_data.job_id]
    save_cron_jobs(jobs)

    return ToolResult(
        data=CronDeleteOutput(
            job_id=input_data.job_id, success=True, message=f"Deleted cron job: {deleted_name}"
        )
    )


class CronListInput(BaseModel):
    """Input for CronList tool."""

    enabled_only: bool = Field(default=False, description="Show only enabled jobs")


class CronJobInfo(BaseModel):
    """Cron job info."""

    job_id: str
    name: str
    schedule: str
    enabled: bool
    run_count: int
    last_run: str | None


class CronListOutput(BaseModel):
    """Output from CronList tool."""

    jobs: list[CronJobInfo]
    total: int
    enabled: int


async def cron_list_call(
    input_data: CronListInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CronListOutput]:
    """List cron jobs."""
    jobs = load_cron_jobs()

    job_list = []
    for job_id, job in jobs.items():
        if input_data.enabled_only and not job.get("enabled", True):
            continue

        job_list.append(
            CronJobInfo(
                job_id=job_id,
                name=job["name"],
                schedule=job["schedule"],
                enabled=job.get("enabled", True),
                run_count=job.get("run_count", 0),
                last_run=job.get("last_run"),
            )
        )

    return ToolResult(
        data=CronListOutput(
            jobs=job_list,
            total=len(jobs),
            enabled=sum(1 for j in jobs.values() if j.get("enabled", True)),
        )
    )


class CronUpdateInput(BaseModel):
    """Input for CronUpdate tool."""

    job_id: str = Field(description="Job ID")
    enabled: bool | None = Field(default=None, description="Enable/disable job")
    schedule: str | None = Field(default=None, description="New schedule")
    command: str | None = Field(default=None, description="New command")


class CronUpdateOutput(BaseModel):
    """Output from CronUpdate tool."""

    job_id: str
    changes: list[str]
    message: str


async def cron_update_call(
    input_data: CronUpdateInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[CronUpdateOutput]:
    """Update a cron job."""
    jobs = load_cron_jobs()

    if input_data.job_id not in jobs:
        return ToolResult(
            data=CronUpdateOutput(job_id=input_data.job_id, changes=[], message=""),
            error=f"Job not found: {input_data.job_id}",
        )

    changes = []
    job = jobs[input_data.job_id]

    if input_data.enabled is not None:
        job["enabled"] = input_data.enabled
        changes.append(f"enabled={input_data.enabled}")

    if input_data.schedule is not None:
        job["schedule"] = input_data.schedule
        changes.append(f"schedule={input_data.schedule}")

    if input_data.command is not None:
        job["command"] = input_data.command
        changes.append(f"command={input_data.command[:30]}...")

    save_cron_jobs(jobs)

    return ToolResult(
        data=CronUpdateOutput(
            job_id=input_data.job_id, changes=changes, message=f"Updated {len(changes)} fields"
        )
    )


# Register cron tools
CronCreateTool = build_tool(
    name="CronCreate",
    description=lambda x, o: f"Create cron job: {x.name}",
    input_schema=CronCreateInput,
    output_schema=CronCreateOutput,
    call=cron_create_call,
    aliases=["cron_create"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

CronDeleteTool = build_tool(
    name="CronDelete",
    description=lambda x, o: f"Delete cron job: {x.job_id}",
    input_schema=CronDeleteInput,
    output_schema=CronDeleteOutput,
    call=cron_delete_call,
    aliases=["cron_delete"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

CronListTool = build_tool(
    name="CronList",
    description=lambda x, o: "List cron jobs",
    input_schema=CronListInput,
    output_schema=CronListOutput,
    call=cron_list_call,
    aliases=["cron_list", "crontab"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

CronUpdateTool = build_tool(
    name="CronUpdate",
    description=lambda x, o: f"Update cron job: {x.job_id}",
    input_schema=CronUpdateInput,
    output_schema=CronUpdateOutput,
    call=cron_update_call,
    aliases=["cron_update"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

register_tool(CronCreateTool)
register_tool(CronDeleteTool)
register_tool(CronListTool)
register_tool(CronUpdateTool)
