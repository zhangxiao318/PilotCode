# PilotCode Plugin System

A simplified but compatible implementation of the ClaudeCode plugin system.

## Overview

The plugin system allows extending PilotCode with:
- **Skills** - Reusable AI prompts with Markdown + frontmatter
- **Commands** - Custom slash commands
- **MCP Servers** - Model Context Protocol integrations
- **Hooks** - Lifecycle event interception (planned)

## Quick Start

### Install a Plugin

```bash
# Install from official marketplace
/plugin install docker@claude-plugins-official

# Install from any marketplace
/plugin install my-plugin@my-marketplace

# Force reinstall
/plugin install docker --force
```

### Manage Plugins

```bash
# List installed plugins
/plugin list

# Enable/disable plugins
/plugin enable docker
/plugin disable docker

# Uninstall
/plugin uninstall docker

# Search for plugins
/plugin search git

# Update marketplaces
/plugin update
```

### Manage Marketplaces

```bash
# List configured marketplaces
/plugin marketplaces
```

## Creating a Plugin

### Directory Structure

```
my-plugin/
├── plugin.json          # Plugin manifest
├── commands/            # Slash commands
│   ├── build.md
│   └── deploy.md
├── skills/              # Reusable skills
│   ├── analyze.md
│   └── fix.md
└── hooks/               # Hooks (optional)
    └── hooks.json
```

### plugin.json

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My awesome plugin",
  "author": {
    "name": "Your Name",
    "email": "you@example.com"
  },
  "license": "MIT",
  "keywords": ["devops", "automation"],
  "commands": "./commands",
  "skills": "./skills",
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-example"],
      "enabled": true
    }
  }
}
```

### Creating Skills

Skills are Markdown files with YAML frontmatter:

```markdown
---
name: code-review
description: Review code for issues
aliases: [review, cr]
allowedTools: [Read, Grep, Bash]
whenToUse: When reviewing code changes
---

Please review the code at {path} for:

1. Code quality issues
2. Security vulnerabilities
3. Performance problems
4. Style violations

Path: {path}
```

## Marketplace Configuration

Marketplaces are JSON files listing available plugins:

```json
{
  "name": "my-marketplace",
  "description": "My company's internal plugins",
  "version": "1.0.0",
  "owner": {
    "name": "My Company"
  },
  "plugins": [
    {
      "name": "internal-tool",
      "description": "Internal automation tool",
      "version": "1.0.0",
      "author": {
        "name": "DevOps Team"
      },
      "source": "github:mycompany/internal-plugin"
    }
  ]
}
```

### Supported Marketplace Sources

- **GitHub**: `{"source": "github", "repo": "owner/repo"}`
- **Git**: `{"source": "git", "url": "https://git.example.com/plugins.git"}`
- **URL**: `{"source": "url", "url": "https://example.com/marketplace.json"}`
- **Local File**: `{"source": "file", "path": "/path/to/marketplace.json"}`
- **Local Directory**: `{"source": "directory", "path": "/path/to/plugins"}`

## Architecture

```
pilotcode/plugins/
├── core/
│   ├── types.py         # Pydantic models
│   ├── config.py        # Configuration management
│   ├── manager.py       # Main plugin manager
│   └── marketplace.py   # Marketplace management
├── sources/
│   ├── base.py          # Source interface
│   └── github.py        # GitHub/Git source
├── loader/
│   ├── skills.py        # Skill loader
│   └── commands.py      # Command loader
├── commands/
│   └── plugin_cmd.py    # /plugin command
└── integration.py       # Integration with PilotCode
```

## Configuration Files

Located at `~/.config/pilotcode/`:

```
~/.config/pilotcode/
├── settings.json
│   ├── enabledPlugins
│   └── extraKnownMarketplaces
└── plugins/
    ├── known_marketplaces.json
    ├── installed_plugins.json
    └── cache/
        ├── marketplaces/
        └── <plugin-cache-dirs>
```

## API Usage

```python
import asyncio
from pilotcode.plugins import get_plugin_manager

async def main():
    # Get plugin manager
    manager = await get_plugin_manager()
    
    # Install a plugin
    plugin = await manager.install_plugin("docker@claude-plugins-official")
    
    # Load all enabled plugins
    result = await manager.load_plugins()
    
    for plugin in result.enabled:
        print(f"Loaded: {plugin.manifest.name}")
        
        # Access skills
        if plugin.skills_path:
            from pilotcode.plugins.loader.skills import SkillLoader
            loader = SkillLoader(plugin.skills_path)
            skills = loader.load_all()
            for skill in skills:
                print(f"  Skill: {skill.name}")

asyncio.run(main())
```

## Comparison with ClaudeCode

| Feature | ClaudeCode | PilotCode Plugin System |
|---------|-----------|------------------------|
| Marketplace Sources | 8 types | 5 types (core) |
| Installation Scope | user/project/local/managed | user/project/local |
| Skill Format | Markdown + frontmatter | ✅ Same |
| Hooks | 15+ events | Basic support |
| MCP Servers | ✅ Full | ✅ Full |
| LSP Servers | ✅ Full | ❌ Not implemented |
| Auto-update | ✅ Yes | ⚠️ Basic |
| Dependency Resolution | ✅ Full | ❌ Not implemented |

## Roadmap

### Phase 1 (MVP) ✅ - COMPLETE
- [x] Core type definitions
- [x] Marketplace management
- [x] GitHub/Git source
- [x] Plugin install/uninstall
- [x] Skill loading (Markdown)
- [x] MCP server integration
- [x] CLI commands

### Phase 2 (Core) ✅ - COMPLETE
- [x] Full hook system (8 hook types)
- [x] Plugin dependency resolution
- [x] Version management (semver)
- [x] Auto-updates with policies

See [Phase 2 Documentation](PHASE2.md) for details.

### Phase 3 (Advanced)
- [ ] LSP server support
- [ ] Plugin signing/verification
- [ ] Enterprise policy support
- [ ] Plugin marketplace UI
- [ ] Advanced hook types

## Implementation Status

| Phase | Lines | Status | Compatibility |
|-------|-------|--------|---------------|
| Phase 1 (MVP) | ~2,200 | ✅ Complete | ~60% ClaudeCode |
| Phase 2 (Core) | ~2,500 | ✅ Complete | ~80% ClaudeCode |
| Phase 3 (Advanced) | - | Planned | ~95% ClaudeCode |

## License

MIT
