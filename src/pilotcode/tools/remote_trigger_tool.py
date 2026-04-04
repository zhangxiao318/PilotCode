"""RemoteTrigger tool for triggering remote events/webhooks."""

import httpx
from typing import Any
from pydantic import BaseModel, Field

from .base import Tool, ToolResult, ToolUseContext, build_tool
from .registry import register_tool


class RemoteTriggerInput(BaseModel):
    """Input for RemoteTrigger tool."""
    url: str = Field(description="Webhook URL to trigger")
    method: str = Field(default="POST", description="HTTP method")
    headers: dict = Field(default_factory=dict, description="HTTP headers")
    body: dict | None = Field(default=None, description="Request body")
    timeout: int = Field(default=30, description="Timeout in seconds")


class RemoteTriggerOutput(BaseModel):
    """Output from RemoteTrigger tool."""
    url: str
    status_code: int
    response: str
    success: bool


async def remote_trigger_call(
    input_data: RemoteTriggerInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any
) -> ToolResult[RemoteTriggerOutput]:
    """Trigger remote webhook."""
    
    try:
        async with httpx.AsyncClient(timeout=input_data.timeout) as client:
            method = input_data.method.upper()
            
            if method == "GET":
                response = await client.get(input_data.url, headers=input_data.headers)
            elif method == "POST":
                response = await client.post(
                    input_data.url,
                    headers=input_data.headers,
                    json=input_data.body
                )
            elif method == "PUT":
                response = await client.put(
                    input_data.url,
                    headers=input_data.headers,
                    json=input_data.body
                )
            elif method == "DELETE":
                response = await client.delete(input_data.url, headers=input_data.headers)
            else:
                return ToolResult(
                    data=RemoteTriggerOutput(
                        url=input_data.url,
                        status_code=0,
                        response="",
                        success=False
                    ),
                    error=f"Unsupported method: {input_data.method}"
                )
            
            # Get response content
            try:
                response_text = response.text[:1000]  # Limit size
            except:
                response_text = "<binary response>"
            
            return ToolResult(data=RemoteTriggerOutput(
                url=input_data.url,
                status_code=response.status_code,
                response=response_text,
                success=200 <= response.status_code < 300
            ))
    
    except httpx.TimeoutException:
        return ToolResult(
            data=RemoteTriggerOutput(
                url=input_data.url,
                status_code=0,
                response="",
                success=False
            ),
            error=f"Timeout after {input_data.timeout} seconds"
        )
    
    except Exception as e:
        return ToolResult(
            data=RemoteTriggerOutput(
                url=input_data.url,
                status_code=0,
                response="",
                success=False
            ),
            error=str(e)
        )


RemoteTriggerTool = build_tool(
    name="RemoteTrigger",
    description=lambda x, o: f"Trigger {x.method} {x.url[:50]}...",
    input_schema=RemoteTriggerInput,
    output_schema=RemoteTriggerOutput,
    call=remote_trigger_call,
    aliases=["trigger", "webhook"],
    is_read_only=lambda _: False,
    is_concurrency_safe=lambda _: True,
)

register_tool(RemoteTriggerTool)
