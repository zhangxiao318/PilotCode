"""Config Tool for managing configuration."""

import json
from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..utils.config import get_config_manager, get_global_config, GlobalConfig


class ConfigInput(BaseModel):
    """Input for Config tool."""

    action: str = Field(description="Action: 'get', 'set', 'list', 'reset'")
    key: str | None = Field(default=None, description="Configuration key")
    value: str | None = Field(default=None, description="Configuration value (for set)")
    scope: str = Field(default="global", description="Scope: 'global' or 'project'")


class ConfigOutput(BaseModel):
    """Output from Config tool."""

    action: str
    key: str | None
    value: Any | None
    success: bool
    message: str


async def config_call(
    input_data: ConfigInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[ConfigOutput]:
    """Execute config action."""
    manager = get_config_manager()

    if input_data.action == "get":
        if not input_data.key:
            return ToolResult(
                data=ConfigOutput(
                    action=input_data.action,
                    key=None,
                    value=None,
                    success=False,
                    message="Key required for get action",
                )
            )

        config = get_global_config()
        value = getattr(config, input_data.key, None)

        return ToolResult(
            data=ConfigOutput(
                action=input_data.action,
                key=input_data.key,
                value=value,
                success=True,
                message=f"{input_data.key} = {value}",
            )
        )

    elif input_data.action == "set":
        if not input_data.key or input_data.value is None:
            return ToolResult(
                data=ConfigOutput(
                    action=input_data.action,
                    key=input_data.key,
                    value=None,
                    success=False,
                    message="Key and value required for set action",
                )
            )

        config = get_global_config()

        if not hasattr(config, input_data.key):
            return ToolResult(
                data=ConfigOutput(
                    action=input_data.action,
                    key=input_data.key,
                    value=None,
                    success=False,
                    message=f"Unknown configuration key: {input_data.key}",
                )
            )

        # Parse value based on existing type
        current_value = getattr(config, input_data.key)
        if isinstance(current_value, bool):
            new_value = input_data.value.lower() in ("true", "1", "yes", "on")
        elif isinstance(current_value, int):
            new_value = int(input_data.value)
        elif isinstance(current_value, list):
            new_value = input_data.value.split(",")
        else:
            new_value = input_data.value

        setattr(config, input_data.key, new_value)
        manager.save_global_config(config)

        return ToolResult(
            data=ConfigOutput(
                action=input_data.action,
                key=input_data.key,
                value=new_value,
                success=True,
                message=f"Set {input_data.key} = {new_value}",
            )
        )

    elif input_data.action == "list":
        config = get_global_config()
        config_dict = {k: v for k, v in config.__dict__.items() if not k.startswith("_")}

        return ToolResult(
            data=ConfigOutput(
                action=input_data.action,
                key=None,
                value=config_dict,
                success=True,
                message=json.dumps(config_dict, indent=2),
            )
        )

    elif input_data.action == "reset":
        # Reset to defaults
        default_config = GlobalConfig()
        manager.save_global_config(default_config)

        return ToolResult(
            data=ConfigOutput(
                action=input_data.action,
                key=None,
                value=None,
                success=True,
                message="Configuration reset to defaults",
            )
        )

    else:
        return ToolResult(
            data=ConfigOutput(
                action=input_data.action,
                key=input_data.key,
                value=None,
                success=False,
                message=f"Unknown action: {input_data.action}",
            )
        )


async def config_description(input_data: ConfigInput, options: dict[str, Any]) -> str:
    """Get description for config tool."""
    if input_data.action == "set":
        return f"Config set: {input_data.key} = {input_data.value}"
    return f"Config {input_data.action}: {input_data.key or 'all'}"


ConfigTool = build_tool(
    name="Config",
    description=config_description,
    input_schema=ConfigInput,
    output_schema=ConfigOutput,
    call=config_call,
    aliases=["config", "cfg", "setting"],
    search_hint="Manage configuration settings",
    is_read_only=lambda x: x.action in ("get", "list") if x else True,
    is_concurrency_safe=lambda x: x.action in ("get", "list") if x else True,
)

register_tool(ConfigTool)
