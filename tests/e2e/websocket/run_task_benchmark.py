#!/usr/bin/env python3
"""Run task1-4 through the WebSocket E2E client and verify results.

Usage:
    python tests/e2e/websocket/run_task_benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.e2e.websocket.client import PilotCodeWebSocketClient  # noqa: E402

WS_URL = "ws://127.0.0.1:8081"
WEB_PORT = 8080
TIMEOUT = 300.0  # 5 minutes per task

TASKS = [
    {
        "id": 1,
        "name": "Task 1: Code Analysis",
        "prompt": (
            "请分析 src/pilotcode/tui_v2/components/status/bar.py 文件：\n\n"
            "1. 说明 StatusBar 类的主要功能和职责\n"
            "2. 列出它有哪些 reactive 属性（reactive variables）\n"
            "3. 解释 _get_right_text 方法中 context usage 的计算逻辑\n"
            "4. 指出这个类使用了哪种 Textual 布局方式（Table/Grid/其他？）\n\n"
            "请给出清晰的分析结果，不需要修改任何代码。"
        ),
        "verify": False,
    },
    {
        "id": 2,
        "name": "Task 2: Simple Edit",
        "prompt": (
            "请修改 src/pilotcode/commands/status_cmd.py 文件：\n\n"
            '在 /status 命令的 "Conversation Context" 部分之后，添加一个 "Disk Usage" 部分，'
            "显示当前工作目录的磁盘使用情况。\n\n"
            "具体要求：\n"
            "1. 使用 shutil.disk_usage(context.cwd) 获取磁盘信息\n"
            "2. 显示：总空间、已用空间、可用空间（格式化为人类可读，如 GB/MB）\n"
            "3. 显示使用百分比进度条（和 token budget bar 类似的样式）\n\n"
            "注意：\n"
            "- 需要在文件顶部导入 shutil\n"
            "- 添加一个辅助函数 _fmt_bytes(n: int) -> str 来格式化字节数\n"
            "- 确保代码风格和现有代码一致\n"
            "- 修改要完整，不要遗漏导入"
        ),
        "verify": True,
    },
    {
        "id": 3,
        "name": "Task 3: Medium Edit",
        "prompt": (
            "请修改 src/pilotcode/tui_v2/components/status/bar.py 文件：\n\n"
            "在 StatusBar 的 _get_right_text 方法中，当 context usage 百分比（pct）超过 80% 时，"
            '在 "context: XX.X%" 文本前面添加一个红色警告符号 "⚠"。\n\n'
            "具体要求：\n"
            "1. 判断条件是 pct > 80.0\n"
            '2. 超过 80% 时显示为："⚠ context: 85.2% (50k/60k)"\n'
            '3. 不超过时保持原样："context: 45.0% (30k/60k)"\n'
            '4. 确保 _get_right_text 返回的字符串格式正确，不影响其他部分（session_id、/help）的分隔符 " | "\n\n'
            "注意：\n"
            "- 只需要修改 _get_right_text 方法\n"
            "- 不要修改其他方法或 CSS\n"
            "- 确保代码逻辑简单清晰"
        ),
        "verify": True,
    },
    {
        "id": 4,
        "name": "Task 4: Multi-File Edit",
        "prompt": (
            "请实现一个新的 `/timestamp` 命令，并在现有的 `/status` 命令中集成它。\n\n"
            "具体要求：\n\n"
            "1. 创建 `src/pilotcode/commands/timestamp_cmd.py` 文件，实现 `/timestamp` 命令：\n"
            "   - 显示当前时间（格式：YYYY-MM-DD HH:MM:SS）\n"
            "   - 显示项目根目录（context.cwd）\n"
            "   - 显示 Python 版本（sys.version.split()[0]）\n"
            '   - 命令名：timestamp，描述："Show current timestamp and environment info"，别名：ts\n'
            "   - 参考其他命令文件的结构（如 version_cmd.py）\n\n"
            "2. 修改 `src/pilotcode/commands/__init__.py`：\n"
            "   - 在导入列表中添加 `from . import timestamp_cmd`（放在 version_cmd 附近即可）\n\n"
            "3. 修改 `src/pilotcode/commands/status_cmd.py`：\n"
            '   - 在 status 命令输出的末尾（return 之前），添加一个 "Last Check" 行：\n'
            "   - 格式：`lines.append(f\"Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\")`\n"
            "   - 注意：datetime 已经导入，不需要重复导入\n"
            '   - 这行应该放在 "Disk Usage" 部分之后（如果存在），或放在 Token Budget 部分之后（如果不存在 Disk Usage）\n\n'
            "4. 确保所有修改后的文件能通过 `python -m py_compile` 语法检查。\n\n"
            "注意：\n"
            "- 不要修改其他无关文件\n"
            "- 保持代码风格与现有文件一致\n"
            "- 新增文件的 shebang、import 顺序、async def 格式参考 version_cmd.py"
        ),
        "verify": True,
    },
]


def start_server() -> subprocess.Popen:
    """Start the PilotCode web server in the background."""
    print("[Launcher] Starting PilotCode web server...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pilotcode",
            "--web",
            "--web-port",
            str(WEB_PORT),
            "--cwd",
            str(project_root),
            "--auto-allow",
            "--skip-config-check",
        ],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return proc


async def wait_for_server(timeout: float = 30.0) -> bool:
    """Wait until the WebSocket server is accepting connections."""
    import websockets

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ws = await websockets.connect(WS_URL, open_timeout=2)
            await ws.close()
            print("[Launcher] WebSocket server is ready, waiting extra 3s for full init...")
            await asyncio.sleep(3.0)
            return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


def stop_server(proc: subprocess.Popen) -> None:
    """Stop the web server."""
    print("[Launcher] Stopping web server...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_verify() -> dict:
    """Run verify_tasks.py and return parsed results."""
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "tests" / "e2e" / "verify_tasks.py"),
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[Verify] stdout: {result.stdout}")
        print(f"[Verify] stderr: {result.stderr}")
        return []


async def run_task(client: PilotCodeWebSocketClient, task: dict) -> dict:
    """Run a single task and return result summary."""
    print(f"\n{'='*60}")
    print(f"[Task {task['id']}] {task['name']}")
    print(f"{'='*60}")

    # Retry create_session once if it fails
    try:
        session_id = await asyncio.wait_for(client.create_session(), timeout=10.0)
    except asyncio.TimeoutError:
        print(f"[Task {task['id']}] create_session timeout, retrying...")
        await asyncio.sleep(1.0)
        session_id = await asyncio.wait_for(client.create_session(), timeout=10.0)
    print(f"[Task {task['id']}] Created session: {session_id}")

    start_time = time.time()
    result = await client.query(task["prompt"], timeout=TIMEOUT)
    elapsed = time.time() - start_time

    status = "SUCCESS" if result.success else "FAILED"
    print(f"[Task {task['id']}] Query {status} in {elapsed:.1f}s")
    print(f"[Task {task['id']}] Tool calls: {result.tool_calls}")

    if result.success:
        # Print first 500 chars of response
        preview = result.response[:500].replace("\n", " ")
        print(f"[Task {task['id']}] Response preview: {preview}...")
    else:
        print(f"[Task {task['id']}] Error: {result.error}")

    return {
        "id": task["id"],
        "name": task["name"],
        "success": result.success,
        "elapsed": elapsed,
        "tool_calls": result.tool_calls,
        "error": result.error,
        "response": result.response,
    }


async def main():
    server_proc = None
    try:
        server_proc = start_server()
        if not await wait_for_server(timeout=30.0):
            print("[Launcher] ERROR: Server failed to start within 30s")
            return 1

        client = PilotCodeWebSocketClient(WS_URL, default_timeout=TIMEOUT)
        await client.connect()
        print("[Client] Connected to WebSocket server")

        results = []
        for task in TASKS:
            task_result = await run_task(client, task)
            results.append(task_result)

        await client.close()

        # Verification
        print(f"\n{'='*60}")
        print("[Verify] Running verify_tasks.py")
        print(f"{'='*60}")
        verify_results = run_verify()

        # Summary
        print(f"\n{'='*60}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*60}")

        for r in results:
            status = "✅ PASS" if r["success"] else "❌ FAIL"
            print(f"  Task {r['id']}: {status} ({r['elapsed']:.1f}s) - {r['name']}")

        print(f"\n{'='*60}")
        print("CODE VERIFICATION RESULTS")
        print(f"{'='*60}")

        all_passed = True
        for vr in verify_results:
            status = "✅ PASS" if vr["passed"] else "❌ FAIL"
            print(f"  {vr['task']}: {status}")
            for check in vr["checks"]:
                icon = "  ✓" if check["passed"] else "  ✗"
                print(f"    {icon} {check['name']}: {check['message']}")
            if not vr["passed"]:
                all_passed = False

        # Overall score
        print(f"\n{'='*60}")
        task_success_count = sum(1 for r in results if r["success"])
        print(f"Query Success Rate: {task_success_count}/{len(results)}")
        if verify_results:
            verify_pass_count = sum(1 for vr in verify_results if vr["passed"])
            print(f"Code Verify Rate: {verify_pass_count}/{len(verify_results)}")
        print(f"{'='*60}")

        return 0 if all_passed else 1

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if server_proc:
            stop_server(server_proc)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
