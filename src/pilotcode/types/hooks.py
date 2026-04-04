"""Hooks type definitions."""

from typing import Any
from pydantic import BaseModel


class HookProgress(BaseModel):
    """Progress update for hooks."""
    type: str
    message: str
    progress: float | None = None


class PromptRequest(BaseModel):
    """Request for prompt generation."""
    context: dict[str, Any]
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]


class PromptResponse(BaseModel):
    """Response from prompt generation."""
    system_prompt: str | None = None
    messages: list[dict[str, Any]] | None = None
    error: str | None = None
