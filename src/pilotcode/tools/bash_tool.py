"""Bash tool for executing shell commands."""

import asyncio
import re
import os
import sys
from typing import Any
from dataclasses import replace
from pydantic import BaseModel, Field

from .base import ToolResult, ToolUseContext, build_tool, resolve_cwd
from .registry import register_tool

# ANSI escape sequence pattern (CSI, OSC, and other ESC sequences)
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_ESCAPE_RE.sub("", text)


# Platform detection cache: detected on first Bash tool call
_platform_info: dict[str, Any] = {"detected": False, "is_windows": False, "shell": None}


def _detect_platform() -> dict[str, Any]:
    """Detect the operating platform and preferred shell."""
    global _platform_info
    if _platform_info["detected"]:
        return _platform_info

    is_win = sys.platform == "win32"
    _platform_info = {
        "detected": True,
        "is_windows": is_win,
        "shell": "cmd" if is_win else "bash",
    }

    # On Windows, prefer PowerShell Core (pwsh) if available, else Windows PowerShell
    if is_win:
        for ps_name in ("pwsh.exe", "powershell.exe"):
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                ps_path = os.path.join(path_dir, ps_name)
                if os.path.isfile(ps_path):
                    _platform_info["shell"] = ps_name.replace(".exe", "")
                    break
            if _platform_info["shell"] != "cmd":
                break

    return _platform_info


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def _wrap_powershell(cmd: str) -> str:
    """Wrap a command to run via PowerShell on Windows."""
    ps = _detect_platform().get("shell", "powershell")

    # Guard: if the command contains Unix-only tools that have no PowerShell
    # equivalent, emit a clear warning instead of letting PowerShell fail
    # silently with an empty or confusing error.
    lowered = cmd.lower()
    unix_only = [
        "sed",
        "awk",
        "xargs",
        "chmod",
        "chown",
        "chgrp",
        "lsof",
        "strace",
        "traceroute",
        "top",
        "htop",
        "free",
        "iostat",
        "vmstat",
        "pgrep",
        "pkill",
        "killall",
        "nohup",
        "screen",
        "tmux",
        "crontab",
        "sudo",
        "su",
        "apt",
        "yum",
        "pacman",
        "brew",
        "dpkg",
        "rpm",
    ]
    # Use word-boundary regex so "stop-process" doesn't match "top"
    if any(re.search(rf"\b{re.escape(u)}\b", lowered) for u in unix_only):
        safe_cmd = cmd.replace('"', '`"').replace("'", "''")
        return (
            f'{ps} -NoProfile -Command "'
            f"$PSStyle.OutputRendering = 'PlainText'; "
            f"echo '[Windows提示] 当前运行在 Windows PowerShell 环境，"
            f"命令中包含不可用的 Unix 工具。原始命令: {safe_cmd}' ; "
            f"echo '请改用 PowerShell 等效命令，"
            f"或使用 FileWrite/FileEdit 等原生工具完成文件操作。'\""
        )

    # Build a minimal Unix-compat layer for common commands used in pipes.
    # Only inject functions that are actually referenced in the command.
    compat = []
    lowered = cmd.lower()
    if "grep" in lowered:
        compat.append(
            "function global:grep { "
            "param([string]$p, [string]$f); "
            "if ($f) { Select-String -Pattern $p -Path $f | Select-Object -ExpandProperty Line } "
            "else { $input | Select-String -Pattern $p | Select-Object -ExpandProperty Line } "
            "}"
        )
    if "head" in lowered:
        compat.append(
            "function global:head { "
            "param([string]$n); "
            "if ($n -match '^\\d+$') { $input | Select-Object -First ([int]$n) } "
            "else { $input | Select-Object -First 10 } "
            "}"
        )
    if "tail" in lowered:
        compat.append(
            "function global:tail { "
            "param([string]$n); "
            "if ($n -match '^\\d+$') { $input | Select-Object -Last ([int]$n) } "
            "else { $input | Select-Object -Last 10 } "
            "}"
        )
    if "wc" in lowered:
        compat.append(
            "function global:wc { "
            "param([switch]$l); "
            "if ($l) { ($input | Measure-Object -Line).Lines } "
            "else { $input | Measure-Object -Line -Word -Character } "
            "}"
        )

    # Escape double quotes for PowerShell -Command
    escaped = cmd.replace('"', '\\"')
    color_disable = "$PSStyle.OutputRendering = 'PlainText'; "
    if compat:
        prefix = "; ".join(compat) + "; "
        return f'{ps} -NoProfile -Command "{color_disable}{prefix}{escaped}"'
    return f'{ps} -NoProfile -Command "{color_disable}{escaped}"'


def translate_command_for_windows(command: str) -> str:
    """Translate common Unix commands to Windows equivalents.

    On Windows we try two strategies:
    1. Direct cmd.exe translation for very simple, common commands.
    2. PowerShell translation for everything else (especially pipes,
       head/tail/wc/grep/find, and multi-arg commands).
    """
    if not is_windows():
        return command

    # Detect & cache platform on first call
    _detect_platform()

    cmd_stripped = command.strip()
    if not cmd_stripped:
        return command

    # If the command already starts with a Windows shell invocation,
    # leave it alone.
    if cmd_stripped.lower().startswith(("powershell ", "pwsh ", "cmd /c ", "cmd /k ")):
        return command

    # ------------------------------------------------------------------
    # 1. Pure cmd.exe translations (fast, no PowerShell overhead)
    # ------------------------------------------------------------------
    if cmd_stripped == "pwd":
        return "cd"

    # cat FILE1 [FILE2...] -> type FILE1 [FILE2...]
    cat_match = re.match(r"^cat\s+(.+)$", cmd_stripped)
    if cat_match:
        args = cat_match.group(1)
        return f"type {args}"

    # If the command contains a pipe, run the *whole* command through
    # PowerShell.  PowerShell pipes are far more capable than cmd.exe.
    # We do this early so that "ls -la | head -20" isn't mis-parsed as
    # a plain ls command.
    if "|" in cmd_stripped and "tr" not in cmd_stripped:
        return _wrap_powershell(cmd_stripped)

    # ------------------------------------------------------------------
    # 2. PowerShell translations (richer semantics)
    # ------------------------------------------------------------------

    # date
    if cmd_stripped == "date":
        return _wrap_powershell("Get-Date -Format 'ddd MMM dd HH:mm:ss yyyy'")

    # seq N
    m = re.match(r"^seq\s+(\d+)$", cmd_stripped)
    if m:
        n = m.group(1)
        return _wrap_powershell(f"for ($i = 1; $i -le {n}; $i++) {{ Write-Output $i }}")

    # seq START END
    m = re.match(r"^seq\s+(\d+)\s+(\d+)$", cmd_stripped)
    if m:
        start, end = m.group(1), m.group(2)
        return _wrap_powershell(f"for ($i = {start}; $i -le {end}; $i++) {{ Write-Output $i }}")

    # sleep N
    m = re.match(r"^sleep\s+(\d+(?:\.\d+)?)$", cmd_stripped)
    if m:
        return _wrap_powershell(f"Start-Sleep -Seconds {m.group(1)}")

    # ls variants  -> Get-ChildItem
    m = re.match(r"^ls\s*(.*)$", cmd_stripped)
    if m:
        args = m.group(1).strip()
        # ls -la, ls -l, ls -a, ls -lah …
        if re.search(r"-[\w]*l", args) or re.search(r"-[\w]*a", args):
            path = re.sub(r"-\w+", "", args).strip()
            path_part = f" -Path '{path}'" if path else ""
            return _wrap_powershell(
                f"Get-ChildItem -Force{path_part} | Select-Object Mode, LastWriteTime, Length, Name | Format-Table -AutoSize"
            )
        # plain ls [path]
        path = args if args else "."
        return _wrap_powershell(
            f"Get-ChildItem -Path '{path}' | Select-Object -ExpandProperty Name"
        )

    # wc -l FILE
    m = re.match(r"^wc\s+-l\s+(.+)$", cmd_stripped)
    if m:
        filepath = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"(Get-Content -Path '{filepath}').Count")

    # head -n N FILE / head -N FILE (e.g. head -20 file.txt)
    m = re.match(r"^head\s+(?:-n\s+)?-?(\d+)\s+(.+)$", cmd_stripped)
    if m:
        n, filepath = m.group(1), m.group(2).strip().strip('"').strip("'")
        return _wrap_powershell(f"Get-Content -Path '{filepath}' | Select-Object -First {n}")

    # tail -n N FILE / tail -N FILE (e.g. tail -10 file.txt)
    m = re.match(r"^tail\s+(?:-n\s+)?-?(\d+)\s+(.+)$", cmd_stripped)
    if m:
        n, filepath = m.group(1), m.group(2).strip().strip('"').strip("'")
        return _wrap_powershell(f"Get-Content -Path '{filepath}' | Select-Object -Last {n}")

    # grep PATTERN FILE / grep -i PATTERN FILE / grep -r PATTERN DIR
    m = re.match(r"^grep\s+(-i\s+)?(-r\s+)?(.+?)\s+(.+)$", cmd_stripped)
    if m:
        case_flag = " -CaseSensitive" if not m.group(1) else ""
        recursive = " -Recurse" if m.group(2) else ""
        pattern = m.group(3).strip().strip('"').strip("'")
        target = m.group(4).strip().strip('"').strip("'")
        # If target is a directory and -r, use Get-ChildItem; else Select-String on file
        if m.group(2):
            return _wrap_powershell(
                f"Get-ChildItem -Path '{target}'{recursive} -File | Select-String -Pattern '{pattern}'{case_flag} | Select-Object -ExpandProperty Line"
            )
        return _wrap_powershell(
            f"Select-String -Path '{target}' -Pattern '{pattern}'{case_flag} | Select-Object -ExpandProperty Line"
        )

    # find DIR -name PATTERN
    m = re.match(r"^find\s+(\S+)\s+-name\s+(.+)$", cmd_stripped)
    if m:
        directory, pattern = m.group(1), m.group(2).strip().strip('"').strip("'")
        return _wrap_powershell(
            f"Get-ChildItem -Path '{directory}' -Recurse -Filter '{pattern}' | Select-Object -ExpandProperty FullName"
        )

    # touch FILE
    m = re.match(r"^touch\s+(.+)$", cmd_stripped)
    if m:
        filepath = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"New-Item -Path '{filepath}' -ItemType File -Force | Out-Null")

    # mkdir -p DIR / mkdir DIR
    m = re.match(r"^mkdir\s+(?:-p\s+)?(.+)$", cmd_stripped)
    if m:
        dirpath = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"New-Item -Path '{dirpath}' -ItemType Directory -Force | Out-Null")

    # rm FILE
    m = re.match(r"^rm\s+([^\s-].*)$", cmd_stripped)
    if m:
        target = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"Remove-Item -Path '{target}' -Force")

    # rm -rf DIR / rm -r DIR
    m = re.match(r"^rm\s+-rf?\s+(.+)$", cmd_stripped)
    if m:
        target = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"Remove-Item -Path '{target}' -Recurse -Force")

    # rmdir DIR / rmdir -p DIR / rmdir -r DIR
    m = re.match(r"^rmdir\s+(?:/s\s+|/q\s+)?(?:-r\s+|-p\s+)?(.+)$", cmd_stripped)
    if m:
        target = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"Remove-Item -Path '{target}' -Recurse -Force")

    # cp SRC DST / cp -r SRC DST
    m = re.match(r"^cp\s+(?:-r\s+)?(.+?)\s+(.+)$", cmd_stripped)
    if m:
        src, dst = m.group(1).strip().strip('"').strip("'"), m.group(2).strip().strip('"').strip(
            "'"
        )
        recurse = " -Recurse" if "-r" in cmd_stripped.split()[:2] else ""
        return _wrap_powershell(f"Copy-Item -Path '{src}' -Destination '{dst}'{recurse} -Force")

    # mv SRC DST
    m = re.match(r"^mv\s+(.+?)\s+(.+)$", cmd_stripped)
    if m:
        src, dst = m.group(1).strip().strip('"').strip("'"), m.group(2).strip().strip('"').strip(
            "'"
        )
        return _wrap_powershell(f"Move-Item -Path '{src}' -Destination '{dst}' -Force")

    # which CMD
    m = re.match(r"^which\s+(.+)$", cmd_stripped)
    if m:
        cmd_name = m.group(1).strip()
        return _wrap_powershell(f"(Get-Command {cmd_name} -ErrorAction SilentlyContinue).Source")

    # echo text | tr OLD NEW  (simple pipe with tr)
    # Supports: echo 'hello' | tr ' ' '-', echo hello | tr " " "-", echo hello | tr ' ' '-'
    if "|" in cmd_stripped and "tr" in cmd_stripped:
        match = re.match(
            r"echo\s+(['\"]?)(.+?)\1\s*\|\s*tr\s+(['\"]?)(.)\3\s+(['\"]?)(.)\5", cmd_stripped
        )
        if match:
            text = match.group(2)
            old_char = match.group(4)
            new_char = match.group(6)
            return _wrap_powershell(
                f"echo '{text}' | ForEach-Object {{ $_ -replace '{old_char}', '{new_char}' }}"
            )

    # ------------------------------------------------------------------
    # 3. Extended PowerShell translations (common Unix utilities)
    # ------------------------------------------------------------------

    # sort FILE / sort -r FILE
    m = re.match(r"^sort\s+(-r\s+)?(.+)$", cmd_stripped)
    if m:
        reverse = " -Descending" if m.group(1) else ""
        filepath = m.group(2).strip().strip('"').strip("'")
        return _wrap_powershell(f"Get-Content -Path '{filepath}' | Sort-Object{reverse}")

    # uniq FILE
    m = re.match(r"^uniq\s+(.+)$", cmd_stripped)
    if m:
        filepath = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"Get-Content -Path '{filepath}' | Get-Unique")

    # diff FILE1 FILE2
    m = re.match(r"^diff\s+(.+?)\s+(.+)$", cmd_stripped)
    if m:
        f1 = m.group(1).strip().strip('"').strip("'")
        f2 = m.group(2).strip().strip('"').strip("'")
        return _wrap_powershell(
            f"Compare-Object (Get-Content '{f1}') (Get-Content '{f2}') | Format-List"
        )

    # cut -d DELIM -f FIELD FILE
    m = re.match(r"^cut\s+-d\s+(['\"]?)(.+?)\1\s+-f\s+(\d+(?:,\d+)?)\s+(.+)$", cmd_stripped)
    if m:
        delim = m.group(2)
        fields = m.group(3)
        filepath = m.group(4).strip().strip('"').strip("'")
        if "," not in fields:
            idx = int(fields) - 1
            return _wrap_powershell(
                f"Get-Content -Path '{filepath}' | ForEach-Object {{ $_.Split('{delim}')[{idx}] }}"
            )

    # tee FILE
    m = re.match(r"^tee\s+(.+)$", cmd_stripped)
    if m:
        filepath = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(f"Tee-Object -FilePath '{filepath}'")

    # env
    if cmd_stripped == "env":
        return _wrap_powershell(
            "Get-ChildItem Env: | ForEach-Object { '{0}={1}' -f $_.Name, $_.Value }"
        )

    # whoami
    if cmd_stripped == "whoami":
        return _wrap_powershell("echo $env:USERNAME")

    # uname
    if cmd_stripped == "uname":
        return _wrap_powershell("echo $env:OS")

    # id
    if cmd_stripped == "id":
        return _wrap_powershell("whoami; echo 'Groups:'; whoami /groups")

    # ps aux / ps -ef
    if re.match(r"^ps\s+(aux|-ef)\s*$", cmd_stripped):
        return _wrap_powershell("Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet")

    # plain ps
    if cmd_stripped == "ps":
        return _wrap_powershell("Get-Process | Select-Object -First 20")

    # kill PID
    m = re.match(r"^kill\s+(\d+)$", cmd_stripped)
    if m:
        return _wrap_powershell(f"Stop-Process -Id {m.group(1)} -Force")

    # killall NAME
    m = re.match(r"^killall\s+(.+)$", cmd_stripped)
    if m:
        name = m.group(1).strip()
        return _wrap_powershell(f"Stop-Process -Name '{name}' -Force")

    # df -h / df
    m = re.match(r"^df(\s+-h)?\s*$", cmd_stripped)
    if m:
        return _wrap_powershell(
            "Get-Volume | Select-Object DriveLetter, FileSystemLabel, FileSystem, "
            "@{N='SizeGB';E={[math]::Round($_.Size/1GB,2)}}, "
            "@{N='FreeGB';E={[math]::Round($_.SizeRemaining/1GB,2)}}"
        )

    # du -sh PATH / du -s PATH
    m = re.match(r"^du\s+-sh?\s+(.+)$", cmd_stripped)
    if m:
        path = m.group(1).strip().strip('"').strip("'")
        return _wrap_powershell(
            f"(Get-ChildItem -Path '{path}' -Recurse -ErrorAction SilentlyContinue "
            f"| Measure-Object -Property Length -Sum).Sum / 1MB"
        )

    # ping -c N HOST
    m = re.match(r"^ping\s+-c\s+(\d+)\s+(.+)$", cmd_stripped)
    if m:
        count, host = m.group(1), m.group(2).strip()
        return _wrap_powershell(f"ping -n {count} {host}")

    # curl -O URL
    m = re.match(r"^curl\s+-O\s+(.+)$", cmd_stripped)
    if m:
        url = m.group(1).strip()
        return _wrap_powershell(
            f"Invoke-WebRequest -Uri '{url}' -OutFile (Split-Path -Leaf '{url}')"
        )

    # curl URL
    m = re.match(r"^curl\s+(.+)$", cmd_stripped)
    if m:
        url = m.group(1).strip()
        return _wrap_powershell(
            f"Invoke-WebRequest -Uri '{url}' | Select-Object -ExpandProperty Content"
        )

    # wget URL
    m = re.match(r"^wget\s+(.+)$", cmd_stripped)
    if m:
        url = m.group(1).strip()
        return _wrap_powershell(
            f"Invoke-WebRequest -Uri '{url}' -OutFile (Split-Path -Leaf '{url}')"
        )

    # tar ...  (Windows 10+ has built-in tar; run via cmd to ensure availability)
    m = re.match(r"^tar\s+(.*)$", cmd_stripped)
    if m:
        args = m.group(1).strip()
        return f"cmd /c tar {args}"

    # unzip FILE -d DIR
    m = re.match(r"^unzip\s+(.+?)(?:\s+-d\s+(.+))?$", cmd_stripped)
    if m:
        file = m.group(1).strip().strip('"').strip("'")
        dest = m.group(2)
        if dest:
            dest = dest.strip().strip('"').strip("'")
            return _wrap_powershell(
                f"Expand-Archive -Path '{file}' -DestinationPath '{dest}' -Force"
            )
        return _wrap_powershell(f"Expand-Archive -Path '{file}' -Force")

    # xargs -I{} CMD  (very basic)
    m = re.match(r"^xargs\s+-I\s*(\{\}|\{\w+})\s+(.+)$", cmd_stripped)
    if m:
        placeholder, cmd_template = m.group(1), m.group(2)
        ps_cmd = cmd_template.replace(placeholder, "$_")
        return _wrap_powershell(f"$input | ForEach-Object {{ {ps_cmd} }}")

    # sed 's/old/new/g' FILE  (basic substitution only)
    m = re.match(r"^sed\s+(['\"])s/(.+?)/(.+?)/g\1\s+(.+)$", cmd_stripped)
    if m:
        old_str, new_str, filepath = (
            m.group(2),
            m.group(3),
            m.group(4).strip().strip('"').strip("'"),
        )
        return _wrap_powershell(
            f"(Get-Content -Path '{filepath}') -replace '{old_str}', '{new_str}'"
        )

    # ifconfig / ip addr
    if cmd_stripped in ("ifconfig", "ip addr", "ip a"):
        return _wrap_powershell(
            "Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress, PrefixLength"
        )

    # netstat
    m = re.match(r"^netstat\s+.*$", cmd_stripped)
    if m:
        return _wrap_powershell(
            "Get-NetTCPConnection | Select-Object LocalAddress, LocalPort, "
            "RemoteAddress, RemotePort, State"
        )

    # ------------------------------------------------------------------
    # 4. Final guard: catch any remaining Unix-only commands that would
    #    otherwise fail silently on Windows.
    # ------------------------------------------------------------------
    UNIX_ONLY_COMMANDS = [
        r"\bsed\b",
        r"\bawk\b",
        r"\bxargs\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bchgrp\b",
        r"\blsof\b",
        r"\bstrace\b",
        r"\btraceroute\b",
        r"\btop\b",
        r"\bhtop\b",
        r"\bfree\b",
        r"\biostat\b",
        r"\bvmstat\b",
        r"\bpgrep\b",
        r"\bpkill\b",
        r"\bkillall\b",
        r"\bnohup\b",
        r"\bscreen\b",
        r"\btmux\b",
        r"\bcrontab\b",
        r"\bsudo\b",
        r"\bsu\b",
        r"\bapt\b",
        r"\byum\b",
        r"\bpacman\b",
        r"\bbrew\b",
        r"\bdpkg\b",
        r"\brpm\b",
    ]
    for pattern in UNIX_ONLY_COMMANDS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            safe_cmd = cmd_stripped.replace('"', '`"').replace("'", "''")
            return _wrap_powershell(
                f"echo '[Windows提示] 当前运行在 Windows PowerShell 环境，"
                f"命令中包含不可用的 Unix 工具。原始命令: {safe_cmd}'; "
                f"echo '请改用 PowerShell 等效命令，"
                f"或使用 FileWrite/FileEdit 等原生工具完成文件操作。'"
            )

    return command


# Dangerous command patterns (inspired by NanoCoder)
# These patterns could wreck the filesystem or leak secrets
DANGEROUS_PATTERNS = [
    # rm -rf on root directory specifically (not /tmp, /home, etc.)
    # Use negative lookahead to exclude /tmp, /home, etc. - only match root /
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+~/", "recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+~(?:\s|#|\||;|$)", "recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-r\w*\s+\$HOME", "recursive delete on home directory"),
    # rm -rf / with various suffixes (must be followed by space, comment, pipe, semicolon, or end)
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+/(?:\s|#|\||;|$)", "force recursive delete on system directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+/\*", "recursive delete all files in root"),
    # Handle -- argument separator: rm -rf -- / (common bypass technique)
    (r"\brm\s+(-[a-zA-Z\s]*)--\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    # Handle case where arguments after -- include root: rm -r -- -rf /
    (r"\brm\s+(-[a-zA-Z\s]*)--\s+\S+\s+/(?![a-zA-Z])", "recursive delete on root directory"),
    # Filesystem formatting
    (r"\bmkfs\b", "format filesystem"),
    # Raw disk writes
    (r"\bdd\s+.*of=/dev/", "raw disk write"),
    (r">\s*/dev/sd[a-z]", "overwrite block device"),
    (r">\s*/dev/nvme", "overwrite block device"),
    (r">\s*/dev/hd[a-z]", "overwrite block device"),
    (r">\s*/dev/null\s+of=/dev/", "overwrite block device via /dev/null"),
    # Dangerous chmod - only match root directory, not subdirectories like /tmp
    (r"\bchmod\s+(-R\s+)?777\s+/(?![a-zA-Z0-9])", "chmod 777 on root"),
    (r"\bchmod\s+(-R\s+)?777\s*/(?:\s|#|\||;|$)", "chmod 777 on root"),
    # Fork bomb
    (r":\(\)\s*\{.*:\|:.*\}", "fork bomb"),
    (r":\s*\(\)\s*\{.*:\s*\|\s*:", "fork bomb"),
    # Piping downloads to interpreters (variations)
    (r"\bcurl\b.*\|\s*(sudo\s+)?(bash|sh|zsh|python|perl|ruby)", "pipe download to interpreter"),
    (r"\bwget\b.*\|\s*(sudo\s+)?(bash|sh|zsh|python|perl|ruby)", "pipe download to interpreter"),
    (r"\bcurl\b.*-\s*(sudo\s+)?(bash|sh|zsh|python)", "pipe curl to interpreter via -"),
    # Home directory deletion variations
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+~/", "force recursive delete on home directory"),
    (r"\brm\s+(-[a-zA-Z]*)?-rf\s+~\b", "force recursive delete on home directory"),
    # System config overwrite
    (
        r">\s*/etc/(?:passwd|shadow|fstab|hosts|sudoers|ssh/sshd_config)\b",
        "overwrite critical system file",
    ),
    # Format device
    (r"\bformat\s+/dev/", "format device"),
    # mv to root or overwrite critical files
    (r"\bmv\s+.*\s+/etc/(?:passwd|shadow)\b", "move file to critical system location"),
    # cp to overwrite critical files
    (r"\bcp\s+.*\s+/etc/(?:passwd|shadow)\b", "copy file to critical system location"),
    # Indirect execution via eval
    (r"\beval\s+.*\brm\b", "indirect rm via eval"),
    (r"\beval\s+.*\bdd\b", "indirect dd via eval"),
    # Systemctl dangerous operations
    (
        r"\bsystemctl\s+(stop|restart|disable)\s+(sshd|ssh|network|systemd|dbus)\b",
        "stop critical system service",
    ),
    # Kill system processes
    (r"\bkillall\s+(systemd|dbus|sshd|ssh)\b", "kill critical system process"),
    (r"\bpkill\s+(systemd|dbus|sshd|ssh)\b", "kill critical system process"),
    # Windows-specific dangerous commands
    (r"\bformat\s+[A-Za-z]:", "format Windows drive"),
    (r"\bdel\s+/f\s+/s\s+/q\s+[A-Za-z]:\\", "mass delete on Windows drive"),
    (r"\brmdir\s+/s\s+/q\s+['\"]?C:\\Windows", "delete Windows system directory"),
    (r"\breg\s+delete\s+.*HKLM", "delete registry hive"),
    (r"\bbcdedit\s+/delete", "delete boot configuration"),
    (r"\bdiskpart\s+/s", "automated disk partitioning"),
    (r"\bvssadmin\s+delete\s+shadows", "delete volume shadow copies"),
]


def _normalize_command(command: str) -> str:
    """Normalize command for safer pattern matching.

    Removes common obfuscation techniques:
    - Multiple spaces -> single space
    - Leading/trailing whitespace
    - Common comment patterns
    """
    import re

    # Replace multiple spaces with single space
    normalized = re.sub(r"\s+", " ", command)
    # Remove shell comments (but be careful with # in strings)
    # This is a simplified version - removes # and everything after it
    # A more robust solution would need proper shell parsing
    lines = []
    for line in normalized.split("\n"):
        # Simple comment removal - not perfect but catches common cases
        if "#" in line:
            # Keep # if it's in quotes (simplified check)
            parts = line.split("#")
            if len(parts) > 1:
                # Check if # is likely in a string (preceded by quotes)
                before = parts[0]
                if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                    line = before
        lines.append(line)
    normalized = "\n".join(lines)
    return normalized.strip()


def check_dangerous_command(command: str) -> str | None:
    """Check if a command is dangerous.

    Args:
        command: The command to check

    Returns:
        Warning message if dangerous, None if safe
    """
    # Normalize command to catch obfuscated attempts
    normalized = _normalize_command(command)

    # Check both original and normalized command
    commands_to_check = [command, normalized]

    for cmd in commands_to_check:
        for pattern, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return f"Dangerous command blocked: {reason}"

    return None


class BashProgress(BaseModel):
    """Progress for bash command execution."""

    stdout: str = ""
    stderr: str = ""


class BashInput(BaseModel):
    """Input for Bash tool."""

    command: str = Field(description="The bash command to execute")
    timeout: int = Field(default=600, description="Timeout in seconds")
    description: str | None = Field(
        default=None, description="Description of what the command does (for clarity)"
    )
    working_dir: str | None = Field(default=None, description="Working directory for the command")
    run_in_background: bool = Field(default=False, description="Run command in background")
    force: bool = Field(
        default=False,
        description="Force execution even if command appears dangerous (use with caution)",
    )


class BashOutput(BaseModel):
    """Output from Bash tool."""

    stdout: str
    stderr: str
    exit_code: int
    command: str


async def _read_stream(
    stream: asyncio.StreamReader,
    lines: list[str],
    on_progress: Any,
    stream_name: str,
) -> None:
    """Read a stream line-by-line, handling both \n and \r."""
    buffer = b""
    try:
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            buffer += chunk
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
                    pos, delim = (cr, b"\r") if cr < nl else (nl, b"\n")
                line = buffer[:pos].decode("utf-8", errors="replace")
                buffer = buffer[pos + len(delim) :]
                if not line and delim == b"\r":
                    continue
                lines.append(line)
                if on_progress:
                    on_progress(
                        {
                            "type": "bash_output",
                            "stream": stream_name,
                            "line": line,
                            "is_progress": delim == b"\r",
                        }
                    )
        if buffer:
            line = buffer.decode("utf-8", errors="replace")
            lines.append(line)
            if on_progress:
                on_progress(
                    {
                        "type": "bash_output",
                        "stream": stream_name,
                        "line": line,
                        "is_progress": False,
                    }
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def execute_bash(
    command: str,
    cwd: str | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
    on_progress: Any = None,
) -> BashOutput:
    """Execute a bash command with optional real-time progress streaming."""
    command = translate_command_for_windows(command)
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    # Disable color output from common CLI tools
    process_env.setdefault("NO_COLOR", "1")
    process_env.setdefault("FORCE_COLOR", "0")

    try:
        import subprocess

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            # Set UTF-8 code page for cmd.exe to avoid GBK encoding issues
            command = f"chcp 65001 >nul 2>&1 && {command}"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
            startupinfo=startupinfo,
        )

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        stdout_task = asyncio.create_task(
            _read_stream(process.stdout, stdout_lines, on_progress, "stdout")
        )
        stderr_task = asyncio.create_task(
            _read_stream(process.stderr, stderr_lines, on_progress, "stderr")
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            # Drain pipes instead of hard-cancelling to avoid Windows
            # ProactorEventLoop transport-cleanup warnings.
            for t in (stdout_task, stderr_task):
                if not t.done():
                    try:
                        await asyncio.wait_for(t, timeout=3.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            return BashOutput(
                stdout="\n".join(stdout_lines),
                stderr=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                command=command,
            )
        except asyncio.CancelledError:
            # Handle task cancellation - kill the subprocess
            try:
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            for t in (stdout_task, stderr_task):
                if not t.done():
                    try:
                        await asyncio.wait_for(t, timeout=3.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass
            raise  # Re-raise to propagate cancellation

        await asyncio.gather(stdout_task, stderr_task)

        def decode_lines(lines: list[str]) -> str:
            return "\n".join(lines)

        stdout_text = strip_ansi(decode_lines(stdout_lines))
        stderr_text = strip_ansi(decode_lines(stderr_lines))

        # Hard safety cap: prevent a single command from exhausting system memory.
        # Context-window-aware truncation is handled by QueryEngine.add_tool_result().
        MAX_STDOUT_LINES = 1_000
        MAX_STDERR_LINES = 500
        MEMORY_CAP_CHARS = 100_000

        if len(stdout_lines) > MAX_STDOUT_LINES:
            truncated_line_count = len(stdout_lines) - MAX_STDOUT_LINES
            stdout_lines = stdout_lines[:MAX_STDOUT_LINES]
            stdout_text = "\n".join(stdout_lines)
            stdout_text += (
                f"\n\n[...truncated {truncated_line_count} lines; total output was too large]"
            )
        elif len(stdout_text) > MEMORY_CAP_CHARS:
            truncated_char_count = len(stdout_text) - MEMORY_CAP_CHARS
            stdout_text = stdout_text[:MEMORY_CAP_CHARS]
            stdout_text += (
                f"\n\n[...truncated {truncated_char_count} chars; total output was too large]"
            )

        if len(stderr_lines) > MAX_STDERR_LINES:
            truncated_line_count = len(stderr_lines) - MAX_STDERR_LINES
            stderr_lines = stderr_lines[:MAX_STDERR_LINES]
            stderr_text = "\n".join(stderr_lines)
            stderr_text += (
                f"\n\n[...truncated {truncated_line_count} lines; total stderr was too large]"
            )
        elif len(stderr_text) > MEMORY_CAP_CHARS:
            truncated_char_count = len(stderr_text) - MEMORY_CAP_CHARS
            stderr_text = stderr_text[:MEMORY_CAP_CHARS]
            stderr_text += (
                f"\n\n[...truncated {truncated_char_count} chars; total stderr was too large]"
            )

        return BashOutput(
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=process.returncode or 0,
            command=command,
        )
    except Exception as e:
        return BashOutput(stdout="", stderr=str(e), exit_code=-1, command=command)


def _update_cwd_from_cd(command: str, current_cwd: str | None, set_app_state) -> None:
    """Parse cd/Set-Location/chdir and update app_state.cwd if valid.

    Handles compound commands separated by &&, ;, or ||.
    """
    cmd = command.strip()
    if not cmd:
        return

    base = current_cwd or os.getcwd()
    new_cwd = base
    changed = False

    # Split compound commands: cd .. && cd test  ->  ["cd ..", "cd test"]
    # Also handles: cd ..; cd test; ls
    subcommands = [s.strip() for s in re.split(r"&&|;|\|\|", cmd)]

    for sub in subcommands:
        if not sub:
            continue
        lower = sub.lower()

        # Match cd / chdir / Set-Location with optional /d flag (Windows)
        m = re.match(r'^(?:cd|chdir|set-location)(?:\s+/d)?\s+["\']?(.+?)["\']?\s*$', lower)
        if not m:
            # "cd" alone (no args) -> home directory
            if re.match(r"^(?:cd|chdir|set-location)\s*$", lower):
                target = os.path.expanduser("~")
            else:
                continue
        else:
            target = m.group(1).strip()

        if os.path.isabs(target):
            new_cwd = os.path.normpath(target)
        else:
            new_cwd = os.path.normpath(os.path.join(new_cwd, target))
        changed = True

    if changed and os.path.isdir(new_cwd):
        set_app_state(lambda s: replace(s, cwd=new_cwd))


async def bash_call(
    input_data: BashInput,
    context: ToolUseContext,
    can_use_tool: Any,
    parent_message: Any,
    on_progress: Any,
) -> ToolResult[BashOutput]:
    """Execute bash command."""
    # Check for dangerous commands (unless force flag is set)
    if not input_data.force:
        danger_warning = check_dangerous_command(input_data.command)
        if danger_warning:
            return ToolResult(
                data=BashOutput(
                    stdout="",
                    stderr=f"⚠️  Blocked: {danger_warning}\n\nCommand: {input_data.command}\n\nIf you are certain this is intentional, you can modify the command to be more specific, or use the force parameter (not recommended).",
                    exit_code=-1,
                    command=input_data.command,
                ),
                error=f"Dangerous command blocked: {danger_warning}",
            )

    # Check permissions
    permission = await can_use_tool("BashTool", input_data)
    if isinstance(permission, dict):
        if permission.get("behavior") == "deny":
            return ToolResult(
                data=BashOutput(
                    stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command
                ),
                error="Permission denied",
            )
    elif hasattr(permission, "behavior") and permission.behavior == "deny":
        return ToolResult(
            data=BashOutput(
                stdout="", stderr="Permission denied", exit_code=-1, command=input_data.command
            ),
            error="Permission denied",
        )

    # Determine working directory
    # Bash prefers app_state.cwd so that `cd` tracking persists across turns.
    # File tools prefer context.cwd for session isolation.
    cwd = input_data.working_dir
    if cwd is None:
        if context.get_app_state:
            app_state = context.get_app_state()
            cwd = getattr(app_state, "cwd", None)
        if not cwd:
            cwd = resolve_cwd(context)

    # Execute command
    result = await execute_bash(
        input_data.command, cwd=cwd, timeout=input_data.timeout, on_progress=on_progress
    )

    # Track directory changes from cd commands
    if context.set_app_state and result.exit_code == 0:
        _update_cwd_from_cd(input_data.command, cwd, context.set_app_state)

    # Append persistent CWD info so the LLM knows the actual working directory
    if context.get_app_state:
        app_state = context.get_app_state()
        persistent_cwd = getattr(app_state, "cwd", cwd or os.getcwd())
        if persistent_cwd != cwd:
            result.stderr += f"\n[NOTE: Persistent working directory is now: {persistent_cwd}]"
        else:
            result.stderr += f"\n[NOTE: Working directory: {persistent_cwd}]"

    # Merge stdout + stderr so the LLM sees errors and cwd notes
    output_for_assistant = result.stdout
    if result.stderr:
        if output_for_assistant:
            output_for_assistant += "\n"
        output_for_assistant += result.stderr

    return ToolResult(data=result, output_for_assistant=output_for_assistant)


async def bash_description(input_data: BashInput, options: dict[str, Any]) -> str:
    """Get description for bash tool use."""
    prefix = "PowerShell>" if is_windows() else "$"
    return f"{prefix} {input_data.command[:100]}"


def bash_user_facing_name(input_data: BashInput) -> str:
    """Get user facing name for bash tool."""
    prefix = "PowerShell" if is_windows() else "Bash"
    return f"{prefix}({input_data.command[:50]})"


def is_read_only_command(command: str) -> bool:
    """Check if command is read-only (doesn't modify files)."""
    cmd_lower = command.strip().lower()

    # Destructive substrings that override safe command prefixes
    destructive_markers = [
        # find destructive actions
        " -delete",
        " -exec",
        " -ok",
        # git branch destructive actions
        "git branch -d",
        "git branch -m",
        "git branch -c",
        "git branch --delete",
        "git branch --move",
        "git branch --copy",
        # output redirection (overwrite / append)
        " > ",
        " >> ",
        " 1> ",
        " 2> ",
        " &> ",
        " >| ",
        # piped to destructive commands
        "| xargs rm",
        "| xargs mv",
        "| xargs cp",
        "| sh",
        "| bash",
        # command chaining with destructive commands
        "; rm ",
        "; mv ",
        "; cp ",
        "; chmod ",
        "; chown ",
        "&& rm ",
        "&& mv ",
        "&& cp ",
        "&& chmod ",
        "&& chown ",
    ]
    for marker in destructive_markers:
        if marker in cmd_lower:
            return False

    # List of read-only commands/patterns
    read_only_patterns = [
        "ls",
        "cat",
        "echo",
        "pwd",
        "whoami",
        "id",
        "uname",
        "date",
        "head",
        "tail",
        "less",
        "more",
        "grep",
        "find",
        "wc",
        "which",
        "ps",
        "top",
        "htop",
        "df",
        "du",
        "free",
        "uptime",
        "env",
        "git status",
        "git log",
        "git diff",
        "git show",
        "git branch",
        "python --version",
        "node --version",
        "npm --version",
        "curl -I",
        "curl --head",
        "wget --spider",
    ]

    for pattern in read_only_patterns:
        if cmd_lower.startswith(pattern.lower()):
            return True
    return False


# Create the Bash tool
BashTool = build_tool(
    name="Bash",
    description=bash_description,
    input_schema=BashInput,
    output_schema=BashOutput,
    call=bash_call,
    aliases=["bash", "shell"],
    search_hint="Execute bash shell commands",
    max_result_size_chars=50000,
    is_read_only=lambda x: is_read_only_command(x.command) if x else False,
    is_concurrency_safe=lambda x: is_read_only_command(x.command) if x else False,
    user_facing_name=bash_user_facing_name,
)

# Register the tool
register_tool(BashTool)
