"""Doctor command implementation."""

import subprocess
import sys
import os
from .base import CommandHandler, register_command, CommandContext


async def doctor_command(args: list[str], context: CommandContext) -> str:
    """Handle /doctor command."""
    checks = []
    
    # Check Python version
    py_version = sys.version_info
    checks.append(("Python version", f"{py_version.major}.{py_version.minor}.{py_version.micro}", py_version.major >= 3 and py_version.minor >= 10))
    
    # Check git
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        git_ok = result.returncode == 0
        git_version = result.stdout.strip() if git_ok else "Not found"
    except:
        git_ok = False
        git_version = "Not found"
    checks.append(("Git", git_version, git_ok))
    
    # Check dependencies
    deps = ["rich", "pydantic", "httpx", "prompt_toolkit"]
    for dep in deps:
        try:
            __import__(dep)
            checks.append((f"Package: {dep}", "Installed", True))
        except ImportError:
            checks.append((f"Package: {dep}", "Missing", False))
    
    # Check model connection
    from ..utils.config import get_global_config
    config = get_global_config()
    checks.append(("API base URL", config.base_url, True))
    checks.append(("API key", "Set" if config.api_key else "Not set", config.api_key is not None))
    
    # Check directories
    config_dir = os.path.expanduser("~/.config/pilotcode")
    checks.append(("Config directory", config_dir, os.path.exists(config_dir)))
    
    # Build output
    lines = ["PilotCode Health Check", "=" * 40, ""]
    
    for name, value, ok in checks:
        status = "✓" if ok else "✗"
        lines.append(f"{status} {name}: {value}")
    
    all_ok = all(ok for _, _, ok in checks)
    lines.append("")
    lines.append("All checks passed!" if all_ok else "Some checks failed. Please fix the issues above.")
    
    return "\n".join(lines)


register_command(CommandHandler(
    name="doctor",
    description="Run diagnostics",
    handler=doctor_command
))
