"""MCP Tools for Model Context Protocol integration."""

from typing import Any
from pydantic import BaseModel, Field, create_model

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool
from ..services.mcp_client import get_mcp_client


class MCPListResourcesInput(BaseModel):
    """Input for ListMcpResources tool."""

    server_name: str = Field(description="MCP server name")


class MCPListResourcesOutput(BaseModel):
    """Output from ListMcpResources tool."""

    server_name: str
    resources: list[dict]
    total: int


async def mcp_list_resources_call(
    input_data: MCPListResourcesInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[MCPListResourcesOutput]:
    """List MCP resources."""
    client = get_mcp_client()

    connection = client.connections.get(input_data.server_name)
    if not connection:
        return ToolResult(
            data=MCPListResourcesOutput(server_name=input_data.server_name, resources=[], total=0),
            error=f"MCP server '{input_data.server_name}' not connected",
        )

    return ToolResult(
        data=MCPListResourcesOutput(
            server_name=input_data.server_name,
            resources=[],  # Would be populated from server
            total=0,
        )
    )


class MCPReadResourceInput(BaseModel):
    """Input for ReadMcpResource tool."""

    server_name: str = Field(description="MCP server name")
    resource_uri: str = Field(description="Resource URI")


class MCPReadResourceOutput(BaseModel):
    """Output from ReadMcpResource tool."""

    server_name: str
    resource_uri: str
    content: str | None
    mime_type: str | None


async def mcp_read_resource_call(
    input_data: MCPReadResourceInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[MCPReadResourceOutput]:
    """Read MCP resource."""
    return ToolResult(
        data=MCPReadResourceOutput(
            server_name=input_data.server_name,
            resource_uri=input_data.resource_uri,
            content=None,
            mime_type=None,
        ),
        error="MCP resource reading not fully implemented",
    )


class MCPCallToolInput(BaseModel):
    """Input for MCPTool."""

    server_name: str = Field(description="MCP server name")
    tool_name: str = Field(description="Tool name")
    arguments: dict = Field(default_factory=dict, description="Tool arguments")


class MCPCallToolOutput(BaseModel):
    """Output from MCPTool."""

    server_name: str
    tool_name: str
    result: dict | None
    is_error: bool


async def mcp_call_tool_call(
    input_data: MCPCallToolInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[MCPCallToolOutput]:
    """Call MCP tool."""
    client = get_mcp_client()

    try:
        result = await client.call_tool(
            input_data.server_name, input_data.tool_name, input_data.arguments
        )

        return ToolResult(
            data=MCPCallToolOutput(
                server_name=input_data.server_name,
                tool_name=input_data.tool_name,
                result=result,
                is_error=False,
            )
        )
    except Exception as e:
        return ToolResult(
            data=MCPCallToolOutput(
                server_name=input_data.server_name,
                tool_name=input_data.tool_name,
                result=None,
                is_error=True,
            ),
            error=str(e),
        )


# ------------------------------------------------------------------
# Unified MCP tool (replaces ListMcpResources/ReadMcpResource/MCP)
# ------------------------------------------------------------------


class MCPInput(BaseModel):
    """Input for unified MCP tool."""

    action: str = Field(description="Action: list_resources, read_resource, call_tool")
    server_name: str = Field(description="MCP server name")
    resource_uri: str | None = Field(default=None, description="For read_resource: resource URI")
    tool_name: str | None = Field(default=None, description="For call_tool: tool name")
    arguments: dict = Field(default_factory=dict, description="For call_tool: tool arguments")


class MCPOutputUnified(BaseModel):
    """Unified output for MCP tool."""

    result: dict[str, Any] = Field(default_factory=dict)
    message: str = Field(default="")


async def mcp_call(
    input_data: MCPInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[MCPOutputUnified]:
    """Unified MCP handler."""
    action = input_data.action

    if action == "list_resources":
        result = await mcp_list_resources_call(
            MCPListResourcesInput(server_name=input_data.server_name),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=MCPOutputUnified(
                result=result.data.model_dump() if result.data else {},
                message="MCP resources listed",
            ),
            error=result.error,
        )

    elif action == "read_resource":
        if not input_data.resource_uri:
            return ToolResult(
                data=MCPOutputUnified(), error="resource_uri required for read_resource"
            )
        result = await mcp_read_resource_call(
            MCPReadResourceInput(
                server_name=input_data.server_name, resource_uri=input_data.resource_uri
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=MCPOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="MCP resource read"
            ),
            error=result.error,
        )

    elif action == "call_tool":
        if not input_data.tool_name:
            return ToolResult(data=MCPOutputUnified(), error="tool_name required for call_tool")
        result = await mcp_call_tool_call(
            MCPCallToolInput(
                server_name=input_data.server_name,
                tool_name=input_data.tool_name,
                arguments=input_data.arguments,
            ),
            context,
            can_use_tool,
            parent_message,
            on_progress,
        )
        return ToolResult(
            data=MCPOutputUnified(
                result=result.data.model_dump() if result.data else {}, message="MCP tool called"
            ),
            error=result.error,
        )

    else:
        return ToolResult(data=MCPOutputUnified(), error=f"Unknown action: {action}")


MCPUnifiedTool = build_tool(
    name="MCP",
    description=lambda x, o: f"MCP {x.action}",
    input_schema=MCPInput,
    output_schema=MCPOutputUnified,
    call=mcp_call,
    aliases=["mcp"],
    is_read_only=lambda x: x.action in ("list_resources", "read_resource") if x else True,
    is_concurrency_safe=lambda x: x.action in ("list_resources", "read_resource") if x else True,
)

register_tool(MCPUnifiedTool)

# ------------------------------------------------------------------
# Dynamic MCP tool expansion — register each MCP tool as a native Tool
# ------------------------------------------------------------------


def _json_schema_type_to_python(schema_type: str, items: dict | None = None) -> type:
    """Map JSON Schema type to Python type (simplified)."""
    mapping = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
    }
    if schema_type == "array":
        return list
    if schema_type == "object":
        return dict
    return mapping.get(schema_type, str)


def _build_pydantic_model_from_json_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic BaseModel from a JSON Schema inputSchema (simplified)."""
    fields: dict[str, tuple[type, Any]] = {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        prop_type = prop_schema.get("type", "string")
        py_type = _json_schema_type_to_python(prop_type, prop_schema.get("items"))
        description = prop_schema.get("description", "")
        enum = prop_schema.get("enum")

        if enum and isinstance(enum, list) and all(isinstance(e, str) for e in enum):
            # Use Literal for string enums when possible
            try:
                from typing import Literal

                py_type = Literal[tuple(enum)]  # type: ignore[assignment]
            except Exception:
                pass

        is_required = prop_name in required
        if is_required:
            field_def = (py_type, Field(description=description))
        else:
            field_def = (py_type | None, Field(default=None, description=description))
        fields[prop_name] = field_def

    # Add server_name/tool_name as hidden fields (not exposed to LLM)
    # Actually we don't need them in the schema because we'll bind them
    # in the call closure.
    model = create_model(name, __base__=BaseModel, **fields)
    return model


def register_mcp_tools_as_native(server_name: str, tools: list[dict[str, Any]]) -> list[Tool]:
    """Register MCP tools as first-class PilotCode Tool objects.

    Each tool gets its own name, description, and Pydantic input schema.
    The LLM can call them directly without wrapping in the unified MCP tool.
    """
    from .registry import get_tool_registry

    registry = get_tool_registry()
    registered: list[Tool] = []

    for tool_def in tools:
        if not isinstance(tool_def, dict):
            continue
        tool_name = tool_def.get("name", "")
        if not tool_name:
            continue

        # Namespace to avoid collisions with built-in tools
        native_name = f"MCP_{server_name}_{tool_name}"
        # Sanitize: remove spaces and special chars
        native_name = "".join(c if c.isalnum() or c == "_" else "_" for c in native_name)

        description_text = tool_def.get(
            "description", f"MCP tool '{tool_name}' from server '{server_name}'"
        )
        input_schema = tool_def.get("inputSchema", {})

        try:
            InputModel = _build_pydantic_model_from_json_schema(
                f"MCPInput_{server_name}_{tool_name}", input_schema
            )
        except Exception:
            # Fallback to a simple dict model if schema is too complex
            class FallbackInput(BaseModel):
                arguments: dict = Field(
                    default_factory=dict, description=f"Arguments for {tool_name}"
                )

            InputModel = FallbackInput

        async def _make_call(
            input_data: BaseModel,
            context: ToolUseContext,
            can_use_tool: Any,
            parent_message: Any,
            on_progress: Any,
            _server: str = server_name,
            _tool: str = tool_name,
        ) -> ToolResult[MCPCallToolOutput]:
            client = get_mcp_client()
            args = (
                input_data.model_dump(exclude_unset=True)
                if hasattr(input_data, "model_dump")
                else {}
            )
            # Remove internal fields if any
            args.pop("server_name", None)
            args.pop("tool_name", None)
            try:
                result = await client.call_tool(_server, _tool, args)
                return ToolResult(
                    data=MCPCallToolOutput(
                        server_name=_server,
                        tool_name=_tool,
                        result=result,
                        is_error=False,
                    )
                )
            except Exception as e:
                return ToolResult(
                    data=MCPCallToolOutput(
                        server_name=_server,
                        tool_name=_tool,
                        result=None,
                        is_error=True,
                    ),
                    error=str(e),
                )

        native_tool = build_tool(
            name=native_name,
            description=lambda _x, _o, _desc=description_text: _desc,
            input_schema=InputModel,
            output_schema=MCPCallToolOutput,
            call=_make_call,
            is_read_only=False,
            is_concurrency_safe=False,
        )
        registry.register(native_tool)
        registered.append(native_tool)

    return registered


# Old fine-grained tools kept for direct import compatibility only.
ListMcpResourcesTool = build_tool(
    name="ListMcpResources",
    description=lambda x, o: f"List MCP resources from {x.server_name}",
    input_schema=MCPListResourcesInput,
    output_schema=MCPListResourcesOutput,
    call=mcp_list_resources_call,
    aliases=["mcp_resources", "list_mcp"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

ReadMcpResourceTool = build_tool(
    name="ReadMcpResource",
    description=lambda x, o: f"Read MCP resource {x.resource_uri}",
    input_schema=MCPReadResourceInput,
    output_schema=MCPReadResourceOutput,
    call=mcp_read_resource_call,
    aliases=["mcp_read", "read_mcp"],
    is_read_only=lambda _: True,
    is_concurrency_safe=lambda _: True,
)

MCPTool = build_tool(
    name="MCP",
    description=lambda x, o: f"Call MCP tool {x.tool_name}",
    input_schema=MCPCallToolInput,
    output_schema=MCPCallToolOutput,
    call=mcp_call_tool_call,
    aliases=["mcp_call", "call_mcp"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: False,
)

# register_tool(ListMcpResourcesTool)  # Merged into MCP
# register_tool(ReadMcpResourceTool)
# register_tool(MCPTool)
