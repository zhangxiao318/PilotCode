"""Cron command implementation."""

from .base import CommandHandler, register_command, CommandContext
from ..tools.cron_tools import load_cron_jobs, save_cron_jobs


async def cron_command(args: list[str], context: CommandContext) -> str:
    """Handle /cron command."""
    if not args:
        # List jobs
        jobs = load_cron_jobs()
        
        if not jobs:
            return "No cron jobs scheduled"
        
        lines = ["Scheduled jobs:", ""]
        for job_id, job in jobs.items():
            status = "✓" if job.get("enabled", True) else "✗"
            lines.append(f"  {status} {job_id}: {job['name']}")
            lines.append(f"     Schedule: {job['schedule']}")
            lines.append(f"     Command: {job['command'][:50]}...")
            if job.get('last_run'):
                lines.append(f"     Last run: {job['last_run']}")
            lines.append("")
        
        return "\n".join(lines)
    
    action = args[0]
    
    if action == "create":
        if len(args) < 4:
            return "Usage: /cron create <name> <schedule> <command>"
        
        name = args[1]
        schedule = args[2]
        command = " ".join(args[3:])
        
        jobs = load_cron_jobs()
        job_id = f"cron_{len(jobs) + 1}"
        
        from datetime import datetime
        jobs[job_id] = {
            "name": name,
            "command": command,
            "schedule": schedule,
            "created_at": datetime.now().isoformat(),
            "enabled": True,
            "run_count": 0
        }
        
        save_cron_jobs(jobs)
        return f"Created job {job_id}: {name}"
    
    elif action == "delete":
        if len(args) < 2:
            return "Usage: /cron delete <job_id>"
        
        job_id = args[1]
        jobs = load_cron_jobs()
        
        if job_id not in jobs:
            return f"Job not found: {job_id}"
        
        del jobs[job_id]
        save_cron_jobs(jobs)
        return f"Deleted job: {job_id}"
    
    elif action == "enable":
        if len(args) < 2:
            return "Usage: /cron enable <job_id>"
        
        job_id = args[1]
        jobs = load_cron_jobs()
        
        if job_id not in jobs:
            return f"Job not found: {job_id}"
        
        jobs[job_id]["enabled"] = True
        save_cron_jobs(jobs)
        return f"Enabled job: {job_id}"
    
    elif action == "disable":
        if len(args) < 2:
            return "Usage: /cron disable <job_id>"
        
        job_id = args[1]
        jobs = load_cron_jobs()
        
        if job_id not in jobs:
            return f"Job not found: {job_id}"
        
        jobs[job_id]["enabled"] = False
        save_cron_jobs(jobs)
        return f"Disabled job: {job_id}"
    
    else:
        return f"Unknown action: {action}. Use: create, delete, enable, disable"


register_command(CommandHandler(
    name="cron",
    description="Manage scheduled tasks",
    handler=cron_command
))
