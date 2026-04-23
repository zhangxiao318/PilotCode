"""Async command runner with streaming output and inactivity detection.

Provides non-blocking subprocess execution for REPL/TUI/Web environments.
Handles both newline (\n) and carriage-return (\r) progress bars correctly.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Optional

from rich.console import Console

console = Console()


async def run_command_streaming(
    cmd: list[str],
    cwd: Optional[str] = None,
    total_timeout: float = 300.0,
    inactivity_timeout: float = 30.0,
    env: Optional[dict[str, str]] = None,
    print_output: bool = True,
    prefix_stdout: str = "",
    prefix_stderr: str = "[red]",
) -> tuple[int, str, str]:
    """Run a command asynchronously with real-time output streaming.

    Features:
    - Does NOT block the asyncio event loop
    - Prints stdout/stderr in real time (handles \r progress bars)
    - Warns if the command produces no output for ``inactivity_timeout`` seconds
    - Enforces an overall ``total_timeout``
    - Kills the subprocess on ``asyncio.CancelledError`` (e.g. user Ctrl+C)

    Args:
        cmd: Command and arguments as a list.
        cwd: Working directory.
        total_timeout: Maximum total execution time in seconds.
        inactivity_timeout: If no output arrives for this many seconds,
            a warning is printed so the user knows they can press Ctrl+C.
        env: Optional environment variables to merge with os.environ.
        print_output: Whether to print lines as they arrive.
        prefix_stdout: Optional rich prefix for stdout lines.
        prefix_stderr: Optional rich prefix for stderr lines.

    Returns:
        (returncode, stdout, stderr)
    """
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=merged_env,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    last_activity = time.monotonic()
    activity_lock = asyncio.Lock()
    done_event = asyncio.Event()

    async def _update_activity() -> None:
        nonlocal last_activity
        async with activity_lock:
            last_activity = time.monotonic()

    def _print_line(text: str, is_progress: bool, active_progress: list[bool]) -> None:
        """Print a line, handling progress bars that use \r."""
        if not print_output:
            return
        if is_progress:
            # Use raw stdout write for \r support
            sys.stdout.write(f"\r{text}")
            sys.stdout.flush()
            active_progress[0] = True
        else:
            if active_progress[0]:
                # Previous line was a progress bar; move to new line first
                sys.stdout.write("\n")
                active_progress[0] = False
            console.print(text)

    async def _read_stream(
        stream: asyncio.StreamReader,
        name: str,
        collector: list[str],
        prefix: str,
    ) -> None:
        buffer = b""
        active_progress = [False]  # mutable flag to track progress state
        try:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                buffer += chunk
                await _update_activity()

                while True:
                    nl = buffer.find(b"\n")
                    cr = buffer.find(b"\r")

                    if nl == -1 and cr == -1:
                        break

                    if nl == -1:
                        pos, delim = cr, b"\r"
                    elif cr == -1:
                        pos, delim = nl, b"\n"
                    else:
                        if cr < nl:
                            pos, delim = cr, b"\r"
                        else:
                            pos, delim = nl, b"\n"

                    line = buffer[:pos].decode("utf-8", errors="replace")
                    buffer = buffer[pos + len(delim) :]

                    if not line and delim == b"\r":
                        continue

                    collector.append(line)
                    text = f"{prefix}{line}" if prefix else line
                    _print_line(text, is_progress=(delim == b"\r"), active_progress=active_progress)

            # Flush remaining buffer
            if buffer:
                line = buffer.decode("utf-8", errors="replace")
                collector.append(line)
                text = f"{prefix}{line}" if prefix else line
                if active_progress[0]:
                    sys.stdout.write("\n")
                    active_progress[0] = False
                console.print(text)

        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _watchdog() -> None:
        warned = False
        while process.returncode is None:
            try:
                await asyncio.wait_for(done_event.wait(), timeout=1.0)
                break
            except asyncio.TimeoutError:
                pass

            async with activity_lock:
                idle = time.monotonic() - last_activity

            if idle >= inactivity_timeout and not warned:
                console.print(
                    f"[yellow]⚠️  命令已 {int(idle)} 秒无输出，可能已卡住。按 Ctrl+C 中断。[/yellow]"
                )
                warned = True
            elif idle < inactivity_timeout // 2 and warned:
                warned = False

    stdout_task = asyncio.create_task(
        _read_stream(process.stdout, "stdout", stdout_lines, prefix_stdout)
    )
    stderr_task = asyncio.create_task(
        _read_stream(process.stderr, "stderr", stderr_lines, prefix_stderr)
    )
    watchdog_task = asyncio.create_task(_watchdog())

    try:
        returncode = await asyncio.wait_for(process.wait(), timeout=total_timeout)
    except asyncio.TimeoutError:
        console.print(f"[red]✗ 命令总超时（>{total_timeout}s），正在终止进程…[/red]")
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        returncode = -1
    except asyncio.CancelledError:
        # User pressed Ctrl+C or task was cancelled externally
        try:
            process.kill()
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass
        raise
    finally:
        done_event.set()
        for t in (stdout_task, stderr_task, watchdog_task):
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    return (
        returncode,
        "\n".join(stdout_lines),
        "\n".join(stderr_lines),
    )
