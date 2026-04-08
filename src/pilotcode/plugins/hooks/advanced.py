"""Advanced hook types and utilities.

Additional hooks beyond the core set:
- File watching hooks
- Proactive hooks
- Notification hooks
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .types import HookType, HookContext, HookResult
from .manager import HookManager, get_hook_manager


@dataclass
class FileWatchConfig:
    """Configuration for file watching."""
    paths: list[str]
    recursive: bool = True
    ignore_patterns: list[str] = None
    
    def __post_init__(self):
        if self.ignore_patterns is None:
            self.ignore_patterns = [".git", "node_modules", "__pycache__"]


class FileWatcher:
    """File system watcher that triggers hooks.
    
    Watches specified paths and triggers FILE_CHANGED hooks
    when files are modified.
    """
    
    def __init__(self, hook_manager: Optional[HookManager] = None):
        self.hook_manager = hook_manager or get_hook_manager()
        self._watching = False
        self._task: Optional[asyncio.Task] = None
        self._watched_paths: set[str] = set()
        self._file_mtimes: dict[str, float] = {}
    
    def add_watch(self, path: str) -> None:
        """Add a path to watch."""
        self._watched_paths.add(path)
        # Initialize mtimes
        self._scan_path(path)
    
    def remove_watch(self, path: str) -> None:
        """Remove a watched path."""
        self._watched_paths.discard(path)
    
    def _scan_path(self, path: str) -> list[str]:
        """Scan path and record file mtimes."""
        changed = []
        p = Path(path)
        
        if not p.exists():
            return changed
        
        for file_path in p.rglob("*"):
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    key = str(file_path)
                    
                    if key in self._file_mtimes:
                        if self._file_mtimes[key] != mtime:
                            changed.append(key)
                    
                    self._file_mtimes[key] = mtime
                except OSError:
                    pass
        
        return changed
    
    async def start(self) -> None:
        """Start watching."""
        if self._watching:
            return
        
        self._watching = True
        self._task = asyncio.create_task(self._watch_loop())
    
    async def stop(self) -> None:
        """Stop watching."""
        self._watching = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _watch_loop(self) -> None:
        """Main watch loop."""
        while self._watching:
            try:
                for path in list(self._watched_paths):
                    changed = self._scan_path(path)
                    
                    for file_path in changed:
                        # Trigger hook
                        context = HookContext(
                            hook_type=HookType.FILE_CHANGED,
                            file_path=file_path,
                            metadata={"change_type": "modified"},
                        )
                        await self.hook_manager.execute_hooks(
                            HookType.FILE_CHANGED, context
                        )
                
                # Check every 2 seconds
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(2)


class ProactiveHookManager:
    """Manages proactive (background) hooks.
    
    Proactive hooks run periodically in the background
to perform maintenance tasks.
    """
    
    def __init__(self, hook_manager: Optional[HookManager] = None):
        self.hook_manager = hook_manager or get_hook_manager()
        self._tasks: list[asyncio.Task] = []
        self._running = False
    
    def schedule(
        self,
        callback: Callable,
        interval_seconds: float,
    ) -> None:
        """Schedule a periodic hook."""
        task = asyncio.create_task(
            self._periodic(callback, interval_seconds)
        )
        self._tasks.append(task)
    
    async def _periodic(
        self,
        callback: Callable,
        interval: float,
    ) -> None:
        """Run callback periodically."""
        while True:
            try:
                await callback()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(interval)
    
    async def stop_all(self) -> None:
        """Stop all periodic hooks."""
        for task in self._tasks:
            task.cancel()
        
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks.clear()


class NotificationManager:
    """Manages notifications to users via hooks."""
    
    def __init__(self, hook_manager: Optional[HookManager] = None):
        self.hook_manager = hook_manager or get_hook_manager()
    
    async def notify(
        self,
        message: str,
        level: str = "info",  # info, warning, error
        data: Optional[dict] = None,
    ) -> None:
        """Send a notification via hooks."""
        context = HookContext(
            hook_type=HookType.NOTIFICATION,
            metadata={
                "message": message,
                "level": level,
                "data": data or {},
            },
        )
        await self.hook_manager.execute_hooks(HookType.NOTIFICATION, context)
    
    async def notify_update_available(
        self,
        plugin_id: str,
        current_version: str,
        new_version: str,
    ) -> None:
        """Notify about available update."""
        await self.notify(
            f"Update available for {plugin_id}: {current_version} → {new_version}",
            level="info",
            data={
                "type": "update_available",
                "plugin_id": plugin_id,
                "current": current_version,
                "new": new_version,
            },
        )
    
    async def notify_policy_violation(
        self,
        plugin_id: str,
        reason: str,
    ) -> None:
        """Notify about policy violation."""
        await self.notify(
            f"Policy violation for {plugin_id}: {reason}",
            level="error",
            data={
                "type": "policy_violation",
                "plugin_id": plugin_id,
                "reason": reason,
            },
        )


# Advanced hook decorators
def on_file_change(
    pattern: Optional[str] = None,
    priority: int = 0,
):
    """Decorator for file change hooks.
    
    Args:
        pattern: Optional glob pattern to filter files
        priority: Hook priority
    """
    def decorator(func):
        manager = get_hook_manager()
        
        async def wrapper(context: HookContext) -> HookResult:
            if pattern and context.file_path:
                import fnmatch
                if not fnmatch.fnmatch(context.file_path, pattern):
                    return HookResult()
            return await func(context)
        
        manager.register(HookType.FILE_CHANGED, wrapper, priority=priority)
        return func
    return decorator


def on_notification(
    notification_type: Optional[str] = None,
    priority: int = 0,
):
    """Decorator for notification hooks."""
    def decorator(func):
        manager = get_hook_manager()
        
        async def wrapper(context: HookContext) -> HookResult:
            if notification_type:
                actual_type = context.metadata.get("data", {}).get("type")
                if actual_type != notification_type:
                    return HookResult()
            return await func(context)
        
        manager.register(HookType.NOTIFICATION, wrapper, priority=priority)
        return func
    return decorator


# Convenience exports
__all__ = [
    "FileWatcher",
    "FileWatchConfig",
    "ProactiveHookManager",
    "NotificationManager",
    "on_file_change",
    "on_notification",
]
