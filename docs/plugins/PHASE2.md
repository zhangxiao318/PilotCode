# Phase 2 Implementation: Core Features

This document describes the Phase 2 implementation of the PilotCode plugin system.

## Overview

Phase 2 adds core functionality for production use:
- **Hook System** - Lifecycle event interception
- **Dependency Resolution** - Plugin dependency graphs
- **Version Management** - Semantic versioning and updates
- **Auto-Update** - Automatic update checking and installation

## Code Statistics

| Component | Lines | Files |
|-----------|-------|-------|
| Hook System | 1,233 | 5 |
| Dependency Resolution | 463 | 1 |
| Version Management | 447 | 1 |
| Auto-Update | 405 | 1 |
| **Phase 2 Total** | **2,548** | **8** |
| Phase 1 (MVP) | 2,158 | 12 |
| **Grand Total** | **~5,000** | **20** |

## 1. Hook System

### Architecture

```
pilotcode/plugins/hooks/
├── types.py         # Hook types and data structures
├── manager.py       # Hook registration and execution
├── executor.py      # Integration with tool execution
└── builtin.py       # Built-in hooks
```

### Supported Hook Types

| Hook Type | Trigger | Use Case |
|-----------|---------|----------|
| `PRE_TOOL_USE` | Before tool execution | Permission checks, input validation |
| `POST_TOOL_USE` | After tool success | Logging, result transformation |
| `POST_TOOL_USE_FAILURE` | After tool failure | Error handling, retries |
| `SESSION_START` | New session | Initialization, context setup |
| `USER_PROMPT_SUBMIT` | User sends prompt | Prompt transformation |
| `PERMISSION_REQUEST` | Permission needed | Auto-approval policies |
| `CWD_CHANGED` | Working directory change | Path updates |
| `FILE_CHANGED` | File modification | Auto-refresh, watches |

### Usage Example

```python
from pilotcode.plugins.hooks import HookManager, HookType, HookContext, HookResult

manager = HookManager()

@manager.register(HookType.PRE_TOOL_USE, priority=10)
async def log_tool_use(context: HookContext) -> HookResult:
    print(f"Tool: {context.tool_name}")
    return HookResult()

@manager.register(HookType.PRE_TOOL_USE, priority=100)
async def block_dangerous(context: HookContext) -> HookResult:
    if context.tool_name == "Bash":
        command = context.tool_input.get("command", "")
        if "rm -rf /" in command:
            return HookResult(
                allow_execution=False,
                stop_reason="Dangerous command blocked"
            )
    return HookResult()
```

### Hook Execution

```python
from pilotcode.plugins.hooks import HookExecutor

executor = HookExecutor()

# Before tool execution
result = await executor.before_tool("Read", {"path": "/etc/passwd"})
if not result.allow_execution:
    print(f"Blocked: {result.stop_reason}")
    return

# Use modified input if provided
tool_input = result.modified_input or tool_input

# Execute tool
output = await tool.execute(tool_input)

# After tool execution
output = await executor.after_tool("Read", tool_input, output)
```

### Permission Rules

```python
from pilotcode.plugins.hooks.builtin import PermissionRuleSet, PermissionRule

rules = PermissionRuleSet()

# Auto-allow read operations
rules.add_rule(PermissionRule("Read", "allow"))
rules.add_rule(PermissionRule("Glob", "allow"))

# Ask for sensitive paths
rules.add_rule(PermissionRule("*", "ask", path_pattern="*.ssh/*"))

# Deny system directories
rules.add_rule(PermissionRule("*", "deny", path_pattern="/etc/*"))
```

## 2. Dependency Resolution

### Features

- **Dependency Graph** - Directed graph of plugin dependencies
- **Cycle Detection** - Detect and report circular dependencies
- **Topological Sort** - Installation order calculation
- **Version Constraints** - Semantic versioning support (^, ~, >, <)

### Usage

```python
# Check dependencies
graph = await manager.check_dependencies("my-plugin")

# Report issues
errors = graph.validate()
for error in errors:
    print(f"Dependency issue: {error}")

# Get installation order
order = graph.get_installation_order()
print(f"Install in order: {' -> '.join(order)}")

# Check reverse dependencies (before uninstall)
dependents = manager.check_reverse_dependencies("my-plugin")
if dependents:
    print(f"Warning: These plugins depend on my-plugin: {dependents}")
```

### Version Constraints

| Constraint | Meaning | Example Matches |
|------------|---------|-----------------|
| `1.2.3` | Exact version | `1.2.3` |
| `^1.2.3` | Compatible with major | `1.2.3`, `1.3.0`, `1.9.9` |
| `~1.2.3` | Compatible with minor | `1.2.3`, `1.2.9` |
| `>1.2.3` | Greater than | `1.2.4`, `2.0.0` |
| `>=1.2.3` | Greater or equal | `1.2.3`, `1.3.0` |
| `*` | Any version | All versions |

## 3. Version Management

### Features

- **Version Detection** - Auto-detect from git, npm, manifest
- **Git Integration** - SHA, branch, tag detection
- **Version Comparison** - Semantic version comparison
- **Update Checking** - Check remote sources for updates

### Usage

```python
# Detect current version
info = manager.version_manager.detect_version(plugin_path)
print(f"Version: {info.version}")
print(f"Git SHA: {info.git_sha}")

# Check for updates
updates = await manager.check_for_updates()
for plugin_id, update in updates.items():
    print(f"{plugin_id}: {update['current']} → {update['latest']}")

# Update a plugin
success = await manager.update_plugin("docker@claude-plugins-official")
```

## 4. Auto-Update

### Features

- **Scheduled Checks** - Configurable check interval
- **Update Policy** - Control which plugins can auto-update
- **History Tracking** - Record of all update attempts
- **Background Mode** - Run checks without blocking

### Configuration

```python
from pilotcode.plugins.core.autoupdate import UpdatePolicy

policy = UpdatePolicy(
    enabled=True,
    auto_install=False,  # Only check, don't auto-install
    check_interval_hours=24,
    allowed_sources=["claude-plugins-official"],
    exclude_plugins=["custom-internal-plugin"],
)

manager.setup_auto_update(policy)
```

### CLI Commands

```bash
# Check for updates
/plugin update check

# Check for plugin updates
/plugin update plugins

# Update all plugins
/plugin update plugins --all

# Update specific plugin
/plugin update plugins docker
```

### Background Updates

```python
# Start background checks
await manager.start_auto_update()

# Later, stop them
await manager.stop_auto_update()
```

## Integration with Phase 1

Phase 2 components integrate seamlessly with Phase 1:

```python
from pilotcode.plugins import get_plugin_manager

manager = await get_plugin_manager()

# Phase 1: Install
await manager.install_plugin("docker@claude-plugins-official")

# Phase 2: Check dependencies
graph = await manager.check_dependencies("docker")

# Phase 2: Check for updates
updates = await manager.check_for_updates()

# Phase 2: Enable auto-update
manager.setup_auto_update()
await manager.start_auto_update()
```

## Testing

Run tests for Phase 2 components:

```bash
cd /home/zx/mycc/PilotCode
PYTHONPATH=src python3 tests/test_plugin_system.py
```

## Comparison with ClaudeCode

| Feature | ClaudeCode | PilotCode Phase 2 |
|---------|-----------|-------------------|
| Hook Types | 15+ | 8 (core hooks) |
| Async Hooks | ✅ | ✅ |
| Permission Rules | ✅ | ✅ (pattern-based) |
| Dependency Graph | ✅ | ✅ |
| Version Constraints | ✅ Full semver | ✅ Core patterns |
| Auto-Update | ✅ Enterprise | ✅ Basic |
| Update Policy | ✅ Advanced | ✅ Basic |

## Next Steps (Phase 3)

Planned for Phase 3:
- LSP Server support
- Plugin signing/verification
- Enterprise policy enforcement
- Advanced hook types (file watching, proactive)
- Plugin marketplace UI

## API Quick Reference

### Hook System
```python
# Register hook
@manager.register(HookType.PRE_TOOL_USE, priority=10)
async def my_hook(context: HookContext) -> HookResult: ...

# Execute hooks
result = await manager.execute_hooks(HookType.PRE_TOOL_USE, context)
```

### Dependencies
```python
# Check dependencies
graph = await manager.check_dependencies("plugin-id")

# Validate
errors = graph.validate()

# Get order
order = graph.get_installation_order()
```

### Updates
```python
# Check for updates
updates = await manager.check_for_updates()

# Update plugin
await manager.update_plugin("plugin-id")

# Auto-update
manager.setup_auto_update(policy)
```
