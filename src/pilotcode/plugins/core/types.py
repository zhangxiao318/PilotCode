"""Core type definitions for the plugin system.

Mirrors ClaudeCode's plugin types with simplified implementations.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from datetime import datetime


class PluginScope(str, Enum):
    """Installation scope for plugins."""

    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class MarketplaceSource(BaseModel):
    """Source configuration for a marketplace.

    Supports multiple source types:
    - github: GitHub repository (owner/repo format)
    - git: Generic git repository URL
    - url: Direct URL to marketplace.json
    - file: Local file path
    - directory: Local directory
    """

    source: Literal["github", "git", "url", "file", "directory"]

    # For github source
    repo: Optional[str] = None
    ref: Optional[str] = None  # branch or tag
    path: Optional[str] = None  # path to marketplace.json within repo

    # For git/url sources
    url: Optional[str] = None

    # For file/directory sources
    file_path: Optional[str] = Field(default=None, alias="path")

    @field_validator("repo")
    @classmethod
    def validate_github_repo(cls, v: Optional[str], info) -> Optional[str]:
        values = info.data
        if values.get("source") == "github" and not v:
            raise ValueError("GitHub source requires 'repo' field")
        return v

    @model_validator(mode="after")
    def validate_github_source(self):
        """Validate that GitHub source has repo field."""
        if self.source == "github" and not self.repo:
            raise ValueError("GitHub source requires 'repo' field")
        if self.source == "file" and not self.file_path:
            raise ValueError("File source requires 'path' field")
        return self

    model_config = {"populate_by_name": True}


class PluginAuthor(BaseModel):
    """Plugin author information."""

    name: str
    email: Optional[str] = None
    url: Optional[str] = None


class MCPServerConfig(BaseModel):
    """MCP server configuration."""

    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class HooksConfig(BaseModel):
    """Hooks configuration for a plugin.

    Hooks allow plugins to intercept and modify system behavior.
    """

    pre_tool_use: list[str] = Field(default_factory=list)
    post_tool_use: list[str] = Field(default_factory=list)
    session_start: list[str] = Field(default_factory=list)
    user_prompt_submit: list[str] = Field(default_factory=list)
    permission_request: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class SkillDefinition(BaseModel):
    """Definition of a skill provided by a plugin.

    Skills are reusable prompts with specific capabilities.
    """

    name: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    when_to_use: Optional[str] = None
    argument_hint: Optional[str] = None
    allowed_tools: list[str] = Field(default_factory=list)
    model: Optional[str] = None
    content: str = ""  # The actual prompt content


class PluginManifest(BaseModel):
    """Plugin manifest file (plugin.json).

    This is the main configuration file for a plugin.
    """

    # Metadata
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: Optional[PluginAuthor] = None
    homepage: Optional[str] = None
    repository: Optional[str] = None
    license: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)

    # Dependencies
    dependencies: list[str] = Field(default_factory=list)

    # Components
    hooks: Optional[Union[HooksConfig, str]] = None  # Config or path to hooks.json
    commands: Optional[Union[dict[str, Any], list[str], str]] = None
    agents: Optional[Union[list[str], str]] = None
    skills: Optional[Union[list[str], str]] = None
    mcp_servers: Optional[dict[str, MCPServerConfig]] = Field(None, alias="mcpServers")

    # Settings to merge when plugin is enabled
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Plugin name cannot contain spaces")
        return v

    model_config = ConfigDict(populate_by_name=True)


class PluginMarketplaceEntry(BaseModel):
    """Entry in a marketplace catalog."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: Optional[PluginAuthor] = None
    source: Union[dict[str, Any], str]  # GitHub repo, URL, or local path
    dependencies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class PluginMarketplace(BaseModel):
    """Marketplace catalog file (marketplace.json)."""

    name: str
    description: str = ""
    version: str = "1.0.0"
    owner: Optional[PluginAuthor] = None
    plugins: list[PluginMarketplaceEntry] = Field(default_factory=list)


class LoadedPlugin(BaseModel):
    """A loaded plugin instance.

    This represents a plugin that has been installed and is ready to use.
    """

    name: str
    manifest: PluginManifest
    path: Path  # Installation path
    source: str  # marketplace@name or 'builtin' or 'local'
    enabled: bool = True
    is_builtin: bool = False

    # Component paths
    commands_path: Optional[Path] = None
    agents_path: Optional[Path] = None
    skills_path: Optional[Path] = None
    hooks_config: Optional[HooksConfig] = None
    mcp_servers: Optional[dict[str, MCPServerConfig]] = None

    # Installation metadata
    scope: PluginScope = PluginScope.USER
    installed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KnownMarketplace(BaseModel):
    """Known marketplace configuration."""

    source: MarketplaceSource
    install_location: str
    last_updated: Optional[str] = None
    auto_update: bool = True


class PluginInstallation(BaseModel):
    """Installation record for a plugin."""

    plugin_id: str  # name@marketplace
    scope: PluginScope
    install_path: Path
    version: str
    installed_at: datetime
    project_path: Optional[str] = None  # For project/local scope


class PluginLoadResult(BaseModel):
    """Result of loading plugins."""

    enabled: list[LoadedPlugin] = Field(default_factory=list)
    disabled: list[LoadedPlugin] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
