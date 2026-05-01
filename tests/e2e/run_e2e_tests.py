#!/usr/bin/env python3
"""End-to-end code generation test runner for PilotCode.

Usage:
    python run_e2e_tests.py --category c_simple --mode cli
    python run_e2e_tests.py --category c_complex --mode websocket
    python run_e2e_tests.py --category all --mode cli
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
E2E_DIR = Path(__file__).parent.resolve()
TASKS_DIR = E2E_DIR / "tasks"
OUTPUT_BASE = Path.home() / "test" / "pilotcode_e2e_results"

# ---------------------------------------------------------------------------
# Cross-platform helpers
# ---------------------------------------------------------------------------
_NON_EXEC_EXTS = {
    ".c", ".h", ".o", ".obj", ".txt", ".md", ".log",
    ".yaml", ".yml", ".json", ".py", ".sh", ".pyc", ".pyo",
    ".html", ".css", ".js", ".xml", ".ini", ".cfg",
}


def _is_executable_file(path: Path) -> bool:
    """Check if a path is a likely executable binary, cross-platform."""
    if not path.is_file():
        return False
    name_lower = path.name.lower()
    if any(name_lower.endswith(ext) for ext in _NON_EXEC_EXTS):
        return False
    if sys.platform == "win32":
        # On Windows, .exe is the strongest indicator; os.access is unreliable
        return name_lower.endswith(".exe")
    return os.access(path, os.X_OK)


def _resolve_binary_path(task_dir: Path, cmd_part: str) -> Path | None:
    """Resolve a command string (e.g. './file_reader') to an actual file path."""
    name = cmd_part.lstrip("./").strip()
    candidates = [name]
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        candidates.append(name + ".exe")
    for cand in candidates:
        p = task_dir / cand
        if p.exists() and _is_executable_file(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class TaskDef:
    task_id: str
    category: str
    description: str
    prompt: str
    expected_files: list[str]
    compile_command: list[str]
    run_command: list[str]
    expected_output_contains: list[str]
    timeout_seconds: int = 600

    @classmethod
    def from_yaml(cls, path: Path) -> "TaskDef":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(**data)


@dataclass
class TaskResult:
    task_id: str
    category: str
    mode: str
    elapsed: float
    start_time: str
    end_time: str
    files_generated: int
    total_lines: int
    files_found: list[dict]
    compile_ok: bool
    compile_output: str
    run_ok: bool
    run_output: str
    output_check: bool
    error: str = ""


def _compile_and_run(task_dir: Path, task: TaskDef, files_found: list[dict]) -> tuple[bool, str, bool, str]:
    """Compile and run the generated code.

    Returns (compile_ok, compile_output, run_ok, run_output).
    """
    compile_ok = False
    compile_output = ""

    if (task_dir / "Makefile").exists():
        try:
            cproc = subprocess.run(
                ["make", "-C", str(task_dir)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
            )
            compile_ok = cproc.returncode == 0
            compile_output = ((cproc.stdout or "") + (cproc.stderr or ""))[:500]
            # Makefiles often bundle compile + run in the 'all' target.
            # On Windows, ./target fails even though compilation succeeded.
            # If an executable was produced, treat it as a successful compile.
            if not compile_ok:
                for f in task_dir.iterdir():
                    if _is_executable_file(f):
                        compile_ok = True
                        compile_output += "\n[make exit non-zero, but executable was produced — treating as compile success]"
                        break
        except subprocess.TimeoutExpired:
            compile_output = "[TIMEOUT] make exceeded 120s limit"
        except Exception as e:
            compile_output = str(e)[:500]
    elif any(ff["path"].endswith(".c") for ff in files_found):
        c_files = [str(task_dir / ff["path"]) for ff in files_found if ff["path"].endswith(".c")]
        try:
            cproc = subprocess.run(
                ["gcc", "-Wall", "-Wextra", "-std=c99", "-o", str(task_dir / "test_prog")] + c_files,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
            )
            compile_ok = cproc.returncode == 0
            compile_output = ((cproc.stdout or "") + (cproc.stderr or ""))[:500]
        except subprocess.TimeoutExpired:
            compile_output = "[TIMEOUT] gcc exceeded 120s limit"
        except Exception as e:
            compile_output = str(e)[:500]

    run_ok = False
    run_output = ""
    if compile_ok:
        binary: Path | None = None

        # 1. Default compiled name
        for cand in [task_dir / "test_prog", task_dir / "test_prog.exe"]:
            if cand.exists() and _is_executable_file(cand):
                binary = cand
                break

        # 2. Scan directory for any executable
        if binary is None:
            for f in task_dir.iterdir():
                if _is_executable_file(f):
                    binary = f
                    break

        # 3. Use run_command hints from YAML
        if binary is None:
            for cmd_part in task.run_command:
                resolved = _resolve_binary_path(task_dir, cmd_part)
                if resolved:
                    binary = resolved
                    break

        if binary:
            try:
                rproc = subprocess.run(
                    [str(binary)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30
                )
                run_ok = rproc.returncode == 0
                run_output = ((rproc.stdout or "") + (rproc.stderr or ""))[:1000]
            except subprocess.TimeoutExpired:
                run_output = "[TIMEOUT] program execution exceeded 30s limit"
            except Exception as e:
                run_output = str(e)[:500]

    return compile_ok, compile_output, run_ok, run_output


def _collect_files(task_dir: Path, log_file: Path) -> list[dict]:
    """Collect generated files from task_dir, excluding the log file."""
    files_found: list[dict] = []
    if not task_dir.exists():
        return files_found
    for f in sorted(task_dir.rglob("*")):
        if f.is_file() and f.name != log_file.name:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                files_found.append({
                    "path": str(f.relative_to(task_dir)),
                    "size": f.stat().st_size,
                    "lines": len(text.splitlines()),
                })
            except Exception:
                pass
    return files_found


# ---------------------------------------------------------------------------
# CLI mode runner
# ---------------------------------------------------------------------------
def run_task_cli(task: TaskDef, task_dir: Path, log_file: Path, timeout: int = 360) -> TaskResult:
    """Run a single task via CLI mode."""
    start_time_str = time.strftime("%H:%M:%S")
    task_dir.mkdir(parents=True, exist_ok=True)
    for f in task_dir.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except Exception:
                pass
        elif f.is_dir():
            try:
                shutil.rmtree(f)
            except Exception:
                pass

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["FORCE_COLOR"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    start = time.time()
    proc_stdout = ""
    proc_stderr = ""
    error_msg = ""
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pilotcode",
                "--simple", "--auto-allow", "--no-planning",
                "--prompt", task.prompt + "\n\n请使用中文输出所有测试结果和日志信息。",
                "--cwd", str(task_dir),
                "--max-iterations", "15",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(task_dir),
            timeout=timeout,
        )
        proc_stdout = proc.stdout
        proc_stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        # Defensive: on some Python versions/platforms stdout/stderr may be bytes
        _out = exc.stdout
        _err = exc.stderr
        if isinstance(_out, bytes):
            _out = _out.decode("utf-8", errors="replace")
        if isinstance(_err, bytes):
            _err = _err.decode("utf-8", errors="replace")
        proc_stdout = _out or ""
        proc_stderr = (_err or "") + f"\n[TIMEOUT] Task exceeded {timeout}s limit and was terminated."
        error_msg = f"Task exceeded {timeout}s limit and was terminated."

    elapsed = time.time() - start

    try:
        log_file.write_text(
            f"=== STDOUT ===\n{proc_stdout}\n\n=== STDERR ===\n{proc_stderr}\n",
            encoding="utf-8",
        )
    except Exception as log_exc:
        proc_stderr += f"\n[LOG WRITE ERROR] {log_exc}"

    files_found = _collect_files(task_dir, log_file)

    # Check expected files
    expected_found = all(
        any(ff["path"] == ef for ff in files_found)
        for ef in task.expected_files
    )

    compile_ok, compile_output, run_ok, run_output = _compile_and_run(task_dir, task, files_found)

    # Output check (OR logic: match any = pass; empty run_output = fail if expected exists)
    output_check = True
    if task.expected_output_contains:
        if not run_output:
            output_check = False
            run_output += "\n[OUTPUT CHECK FAILED: no program output (compile or run failed)]"
        else:
            matched = [kw for kw in task.expected_output_contains if kw in run_output]
            if not matched:
                output_check = False
                run_output += f"\n[OUTPUT CHECK FAILED: none of {task.expected_output_contains} found]"

    return TaskResult(
        task_id=task.task_id,
        category=task.category,
        mode="cli",
        elapsed=round(elapsed, 1),
        start_time=start_time_str,
        end_time=time.strftime("%H:%M:%S"),
        files_generated=len(files_found),
        total_lines=sum(f["lines"] for f in files_found),
        files_found=files_found,
        compile_ok=compile_ok,
        compile_output=compile_output,
        run_ok=run_ok,
        run_output=run_output,
        output_check=output_check,
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# WebSocket mode runner
# ---------------------------------------------------------------------------
async def run_task_websocket(task: TaskDef, task_dir: Path, log_file: Path, timeout: int = 360) -> TaskResult:
    """Run a single task via WebSocket mode."""
    import websockets

    start_time_str = time.strftime("%H:%M:%S")
    WS_URL = os.environ.get("PILOTCODE_WS_URL", "ws://127.0.0.1:8083")
    RECV_TIMEOUT = int(os.environ.get("PILOTCODE_WS_RECV_TIMEOUT", "300"))

    task_dir.mkdir(parents=True, exist_ok=True)
    for f in task_dir.iterdir():
        if f.is_file():
            try:
                f.unlink()
            except Exception:
                pass
        elif f.is_dir():
            try:
                shutil.rmtree(f)
            except Exception:
                pass

    ws = None
    start = time.time()
    error_msg = ""
    try:
        ws = await websockets.connect(WS_URL)
        # server_info
        await asyncio.wait_for(ws.recv(), timeout=5)
        # session_create
        await ws.send(json.dumps({"type": "session_create", "cwd": str(task_dir)}))
        await asyncio.wait_for(ws.recv(), timeout=5)
        # query
        await ws.send(json.dumps({"type": "query", "message": task.prompt + "\n\n请使用中文输出所有测试结果和日志信息。"}))

        while True:
            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                break
            msg_raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, RECV_TIMEOUT))
            msg = json.loads(msg_raw)
            mtype = msg.get("type")
            if mtype == "streaming_complete":
                break
            elif mtype == "streaming_error":
                break
            elif mtype == "permission_request":
                await ws.send(json.dumps({
                    "type": "permission_response",
                    "request_id": msg["request_id"],
                    "granted": True,
                    "for_session": True,
                }))
            elif mtype == "user_question_request":
                await ws.send(json.dumps({
                    "type": "user_question_response",
                    "request_id": msg["request_id"],
                    "response": "continue",
                }))
    except asyncio.TimeoutError:
        error_msg = f"Task exceeded {timeout}s limit and was terminated."
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        if ws:
            await ws.close()

    elapsed = time.time() - start

    # Same validation as CLI
    files_found = _collect_files(task_dir, log_file)

    compile_ok, compile_output, run_ok, run_output = _compile_and_run(task_dir, task, files_found)

    # Output check (OR logic: match any = pass; empty run_output = fail if expected exists)
    output_check = True
    if task.expected_output_contains:
        if not run_output:
            output_check = False
            run_output += "\n[OUTPUT CHECK FAILED: no program output (compile or run failed)]"
        else:
            matched = [kw for kw in task.expected_output_contains if kw in run_output]
            if not matched:
                output_check = False
                run_output += f"\n[OUTPUT CHECK FAILED: none of {task.expected_output_contains} found]"

    return TaskResult(
        task_id=task.task_id,
        category=task.category,
        mode="websocket",
        elapsed=round(elapsed, 1),
        start_time=start_time_str,
        end_time=time.strftime("%H:%M:%S"),
        files_generated=len(files_found),
        total_lines=sum(f["lines"] for f in files_found),
        files_found=files_found,
        compile_ok=compile_ok,
        compile_output=compile_output,
        run_ok=run_ok,
        run_output=run_output,
        output_check=output_check,
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def load_tasks(category: str) -> list[TaskDef]:
    """Load task definitions from YAML files."""
    tasks: list[TaskDef] = []
    if category == "all":
        for subdir in TASKS_DIR.iterdir():
            if subdir.is_dir():
                for f in sorted(subdir.glob("*.yaml")):
                    tasks.append(TaskDef.from_yaml(f))
    else:
        cat_dir = TASKS_DIR / category
        if not cat_dir.exists():
            print(f"Category not found: {category}")
            sys.exit(1)
        for f in sorted(cat_dir.glob("*.yaml")):
            tasks.append(TaskDef.from_yaml(f))
    return tasks


def run_all(tasks: list[TaskDef], mode: str, timeout: int = 360) -> list[TaskResult]:
    """Run all tasks and collect results."""
    results: list[TaskResult] = []
    run_id = time.strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_BASE / run_id
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    print(f"Run ID: {run_id}")
    print(f"Mode: {mode}")
    print(f"Tasks: {len(tasks)}")
    print(f"Output: {output_dir}\n")

    overall_start = time.time()
    for task in tasks:
        task_start = time.time()
        start_str = time.strftime("%H:%M:%S", time.localtime(task_start))
        print(f"\n{'='*60}")
        print(f"Task: {task.task_id}")
        print(f"      {task.description}")
        print(f"{'='*60}")

        task_dir = output_dir / "generated" / task.task_id
        log_file = log_dir / f"{task.task_id}.log"

        try:
            if mode == "cli":
                result = run_task_cli(task, task_dir, log_file, timeout=timeout)
            else:
                result = asyncio.run(run_task_websocket(task, task_dir, log_file, timeout=timeout))
        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - task_start
            print(f"  [TIMEOUT] Task exceeded {timeout}s limit (elapsed: {elapsed:.1f}s)")
            files_found = _collect_files(task_dir, log_file)
            # Persist whatever output we have
            try:
                _out = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", errors="replace") if e.stdout else "")
                _err = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
                log_file.write_text(
                    f"=== STDOUT ===\n{_out}\n\n=== STDERR ===\n{_err}\n[TIMEOUT] Task exceeded {timeout}s limit.\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            result = TaskResult(
                task_id=task.task_id,
                category=task.category,
                mode=mode,
                elapsed=round(elapsed, 1),
                start_time=start_str,
                end_time=time.strftime("%H:%M:%S"),
                files_generated=len(files_found),
                total_lines=sum(f["lines"] for f in files_found),
                files_found=files_found,
                compile_ok=False,
                compile_output="",
                run_ok=False,
                run_output="",
                output_check=False,
                error=f"Task timed out after {timeout}s",
            )
        except Exception as e:
            elapsed = time.time() - task_start
            exc_type = type(e).__name__
            # Gracefully handle TimeoutExpired even if it leaks from inner try/except
            if isinstance(e, subprocess.TimeoutExpired):
                print(f"  [TIMEOUT] Task exceeded {timeout}s limit (elapsed: {elapsed:.1f}s)")
                error_msg = f"Task timed out after {timeout}s"
            else:
                print(f"  [CRASH] {exc_type}: {e} (elapsed: {elapsed:.1f}s)")
                traceback.print_exc()
                error_msg = f"{exc_type}: {e}"
            files_found = _collect_files(task_dir, log_file)
            try:
                if isinstance(e, subprocess.TimeoutExpired):
                    _out = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", errors="replace") if e.stdout else "")
                    _err = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
                    log_file.write_text(
                        f"=== STDOUT ===\n{_out}\n\n=== STDERR ===\n{_err}\n[TIMEOUT] Task exceeded {timeout}s limit.\n",
                        encoding="utf-8",
                    )
                else:
                    tb_str = traceback.format_exc()
                    log_file.write_text(f"[CRASH] {exc_type}: {e}\n\n{tb_str}\n", encoding="utf-8")
            except Exception:
                pass
            result = TaskResult(
                task_id=task.task_id,
                category=task.category,
                mode=mode,
                elapsed=round(elapsed, 1),
                start_time=start_str,
                end_time=time.strftime("%H:%M:%S"),
                files_generated=len(files_found),
                total_lines=sum(f["lines"] for f in files_found),
                files_found=files_found,
                compile_ok=False,
                compile_output="",
                run_ok=False,
                run_output="",
                output_check=False,
                error=error_msg,
            )

        print(f"  Elapsed: {result.elapsed:.1f}s  Files: {result.files_generated} ({result.total_lines} lines)")
        print(f"  Compile: {'OK' if result.compile_ok else 'FAIL'}  Run: {'OK' if result.run_ok else 'FAIL'}  OutputCheck: {'OK' if result.output_check else 'FAIL'}")
        results.append(result)

    overall_elapsed = time.time() - overall_start
    print(f"\n{'='*60}")
    print(f"All tasks completed. Total time: {overall_elapsed:.1f}s")
    print(f"{'='*60}")

    # Save results
    summary = {
        "run_id": run_id,
        "mode": mode,
        "total_tasks": len(results),
        "compile_ok": sum(1 for r in results if r.compile_ok),
        "run_ok": sum(1 for r in results if r.run_ok),
        "output_check_ok": sum(1 for r in results if r.output_check),
        "total_files": sum(r.files_generated for r in results),
        "total_lines": sum(r.total_lines for r in results),
        "results": [r.__dict__ for r in results],
    }
    summary_file = output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary saved to: {summary_file}")

    return results


def print_summary(results: list[TaskResult]):
    """Print final summary table."""
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    compile_ok = sum(1 for r in results if r.compile_ok)
    run_ok = sum(1 for r in results if r.run_ok)
    output_ok = sum(1 for r in results if r.output_check)
    total_files = sum(r.files_generated for r in results)
    total_lines = sum(r.total_lines for r in results)

    print(f"Total tasks: {len(results)}")
    print(f"Compile OK: {compile_ok}/{len(results)}")
    print(f"Run OK: {run_ok}/{len(results)}")
    print(f"Output Check OK: {output_ok}/{len(results)}")
    print(f"Total files: {total_files}, Total lines: {total_lines}")
    print()
    for r in results:
        c = "OK" if r.compile_ok else "FAIL"
        ru = "OK" if r.run_ok else "FAIL"
        o = "OK" if r.output_check else "FAIL"
        err_info = f" [{r.error}]" if r.error else ""
        print(f"  {r.task_id:40s} C:{c:5s} R:{ru:5s} O:{o:5s} {r.elapsed:6.1f}s  {r.total_lines:5d}L{err_info}")


def main():
    parser = argparse.ArgumentParser(description="PilotCode E2E Code Generation Test Runner")
    parser.add_argument("--category", default="c_simple", help="Task category (c_simple, c_complex, all)")
    parser.add_argument("--mode", default="cli", choices=["cli", "websocket"], help="Execution mode")
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8083", help="WebSocket URL (for websocket mode)")
    parser.add_argument("--ws-recv-timeout", type=int, default=300, help="WebSocket recv timeout in seconds")
    parser.add_argument("--timeout", type=int, default=360, help="Task timeout in seconds (default: 360)")
    args = parser.parse_args()

    os.environ["PILOTCODE_WS_URL"] = args.ws_url
    os.environ["PILOTCODE_WS_RECV_TIMEOUT"] = str(args.ws_recv_timeout)

    tasks = load_tasks(args.category)
    if not tasks:
        print("No tasks found.")
        sys.exit(1)

    results = run_all(tasks, args.mode, timeout=args.timeout)
    print_summary(results)

    # Exit with non-zero if any task failed
    if any(not r.compile_ok or not r.run_ok for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
