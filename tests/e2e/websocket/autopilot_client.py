#!/usr/bin/env python3
"""Autopilot WebSocket E2E test client for PilotCode.

Usage:
    # Default task (model capability path alignment)
    python autopilot_client.py

    # Custom prompt from command line
    python autopilot_client.py -p "请帮我添加一个hello world功能"

    # Prompt from file
    python autopilot_client.py -f /path/to/task.txt

    # Custom output directory and timeout
    python autopilot_client.py -f task.txt -o /tmp/e2e_results --timeout 300

    # PLAN mode with custom WebSocket URL
    python autopilot_client.py -p "..." --mode PLAN --ws-url ws://127.0.0.1:8081
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import PilotCodeWebSocketClient, QueryResult

DEFAULT_PROMPT = (
    "请帮我实现两个功能修改：\n"
    "1. 目前探测模型能力后输出的 model_capability.json 位置和模型配置 settings.json 的位置不一样。"
    "settings.json 在 ~/.config/pilotcode/settings.json，而 model_capability.json 在 ~/.pilotcode/model_capability.json。"
    "请将 model_capability.json 的默认保存和读取位置也统一到 ~/.config/pilotcode/ 目录下。\n"
    "2. 运行 `config --list` 时，如果当前使用的是本地模型（model_provider 为 custom 或 ollama，或者 base_url 是本地地址），"
    "检查 ~/.config/pilotcode/model_capability.json 是否存在。如果不存在，或者里面的 model_name 和 settings.json 中的 default_model 不一致，"
    "提示用户运行 `config --test capability` 评估本地模型的性能。\n"
    "请仔细修改相关文件，确保修改完整且正确。"
)

WS_URL = "ws://127.0.0.1:8081"
DEFAULT_TIMEOUT = 600  # 10 minutes max


@dataclass
class AutopilotResult:
    """Result of an autopilot E2E test run."""

    success: bool
    logs: str = ""
    content: str = ""
    task_description: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""


class AutopilotClient(PilotCodeWebSocketClient):
    """WebSocket client with autopilot capabilities.

    Automatically approves permissions, answers simple questions,
    and saves detailed logs for post-run analysis.
    """

    def __init__(self, ws_url: str, default_timeout: float = DEFAULT_TIMEOUT):
        super().__init__(ws_url, default_timeout)
        self._logs: list[str] = []
        self._content_parts: list[str] = []
        self._stream_ended = asyncio.Event()

    def _log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        self._logs.append(line)

    async def run_task(
        self,
        task_description: str,
        mode: str = "",
        timeout: float | None = None,
    ) -> AutopilotResult:
        """Connect and run a task autonomously.

        Args:
            task_description: The task to send.
            mode: Optional mode override (e.g. "PLAN").
            timeout: Max seconds to wait.

        Returns:
            AutopilotResult with logs, content, and success flag.
        """
        start_time = time.time()
        self._logs.clear()
        self._content_parts.clear()
        self._stream_ended.clear()

        try:
            await self.connect()
            self._log(f"Connected to {self.ws_url}")

            session_id = await self.create_session()
            self._log(f"Session created: {session_id}")

            payload: dict[str, Any] = {
                "type": "query",
                "session_id": session_id,
                "message": task_description,
            }
            if mode:
                payload["mode"] = mode

            await self._send(payload)
            self._log(f"Query sent: {task_description[:80]}...")

            result = await self._message_loop(timeout)

            await self.close()
            self._log("WebSocket closed.")

            elapsed = time.time() - start_time
            return AutopilotResult(
                success=result.success,
                logs="\n".join(self._logs),
                content=result.response,
                task_description=task_description,
                elapsed_seconds=elapsed,
                error=result.error,
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            self._log(f"ERROR: {exc}")
            return AutopilotResult(
                success=False,
                logs="\n".join(self._logs),
                task_description=task_description,
                elapsed_seconds=elapsed,
                error=str(exc),
            )

    async def _message_loop(self, timeout: float | None = None) -> QueryResult:
        """Inner message loop with autopilot interactions."""
        timeout = timeout or self.default_timeout
        deadline = asyncio.get_event_loop().time() + timeout
        result = QueryResult(success=True)
        chunks: list[str] = []

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                result.success = False
                result.error = f"Timeout after {timeout}s"
                break

            try:
                recv_timeout = min(remaining, 300.0)
                msg = await asyncio.wait_for(self._recv_any(), timeout=recv_timeout)
            except asyncio.TimeoutError:
                if self._stream_ended.is_set():
                    break
                result.success = False
                result.error = "Timeout waiting for server response"
                break

            msg_type = msg.get("type", "")

            if msg_type == "streaming_start":
                self._log(f"Stream started: {msg.get('stream_id', '')}")

            elif msg_type == "streaming_chunk":
                chunk = msg.get("chunk", "")
                chunks.append(chunk)
                if len(self._content_parts) % 10 == 0:
                    total = sum(len(p) for p in self._content_parts) + sum(len(c) for c in chunks)
                    self._log(f"  ... received {total} chars")

            elif msg_type == "tool_call":
                tool_name = msg.get("tool_name", "")
                tool_input = msg.get("tool_input", {})
                self._log(f"Tool call: {tool_name}({json.dumps(tool_input)[:100]}...)")

            elif msg_type == "tool_progress":
                self._log(f"Tool progress: {msg.get('tool_name', '')} - {msg.get('line', '')}")

            elif msg_type == "permission_request":
                req_id = msg.get("request_id", "")
                tool_name = msg.get("tool_name", "")
                self._log(f"Permission request: {tool_name} (req={req_id})")
                await self._send(
                    {
                        "type": "permission_response",
                        "request_id": req_id,
                        "granted": True,
                        "for_session": True,
                    }
                )
                self._log(f"Auto-approved permission: {tool_name}")

            elif msg_type == "user_question_request":
                req_id = msg.get("request_id", "")
                question = msg.get("question", "")
                options = msg.get("options")
                self._log(f"User question: {question[:100]}")
                if options:
                    answer = options[0]
                else:
                    answer = "Yes, proceed."
                await self._send(
                    {
                        "type": "user_question_response",
                        "request_id": req_id,
                        "response": answer,
                    }
                )
                self._log(f"Auto-answered: {answer}")

            elif msg_type == "system":
                content = msg.get("content", "")
                self._log(f"System: {content[:200]}")

            elif msg_type == "planning_progress":
                content = msg.get("content", "")
                self._log(f"Plan progress:\n{content[:500]}")

            elif msg_type == "streaming_complete":
                content = msg.get("content", "")
                if content:
                    self._content_parts.append(content)
                result.response = "".join(chunks) + "".join(self._content_parts)
                result.success = True
                self._log("Stream complete.")
                self._stream_ended.set()
                break

            elif msg_type == "streaming_error":
                error = msg.get("error", "Unknown error")
                self._log(f"ERROR: {error}")
                result.success = False
                result.error = error
                self._stream_ended.set()

            elif msg_type == "interrupted":
                self._log("Interrupted.")
                result.success = False
                result.error = "Interrupted"
                self._stream_ended.set()

            elif msg_type == "thinking":
                content = msg.get("content", "")
                self._log(f"Thinking: {content[:150]}...")

            elif msg_type in ("streaming_end",):
                result.response = "".join(chunks) + "".join(self._content_parts)
                result.success = True
                self._stream_ended.set()

            else:
                # Unknown or session-level messages — ignore
                pass

        return result


def _load_prompt(source: str) -> str:
    """Load prompt from file or return as-is."""
    path = Path(source)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return source.strip()


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autopilot WebSocket E2E test client for PilotCode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run default task
  %(prog)s -p "Add a hello world"   # Custom prompt
  %(prog)s -f task.txt              # Prompt from file
  %(prog)s -f task.txt -o results   # Custom output dir
        """,
    )
    parser.add_argument(
        "-p",
        "--prompt",
        default="",
        help="Task prompt string (default: built-in path-alignment task)",
    )
    parser.add_argument(
        "-f",
        "--file",
        default="",
        help="Path to a file containing the task prompt",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./logs",
        help="Output directory for logs and results (default: ./logs)",
    )
    parser.add_argument(
        "--ws-url",
        default=WS_URL,
        help=f"WebSocket URL (default: {WS_URL})",
    )
    parser.add_argument(
        "--mode",
        default="",
        help="Query mode, e.g. PLAN (default: auto)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Max seconds to wait (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--save-logs",
        action="store_true",
        default=True,
        help="Save logs and content to files (default: True)",
    )
    parser.add_argument(
        "--no-save-logs",
        action="store_true",
        help="Do not save logs to files",
    )

    args = parser.parse_args()

    # Determine prompt
    if args.file:
        task = _load_prompt(args.file)
    elif args.prompt:
        task = args.prompt
    else:
        task = DEFAULT_PROMPT

    save_logs = args.save_logs and not args.no_save_logs

    client = AutopilotClient(args.ws_url, args.timeout)
    result = await client.run_task(task, mode=args.mode, timeout=args.timeout)

    print(f"\n{'=' * 60}")
    print(f"Task: {result.task_description[:60]}...")
    print(f"Elapsed: {result.elapsed_seconds:.1f}s")
    print(f"Success: {result.success}")
    if result.error:
        print(f"Error: {result.error}")
    print(f"{'=' * 60}")

    if save_logs:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")

        log_path = out_dir / f"e2e_autopilot_{ts}.log"
        content_path = out_dir / f"e2e_autopilot_{ts}.content.txt"
        meta_path = out_dir / f"e2e_autopilot_{ts}.json"

        log_path.write_text(result.logs, encoding="utf-8")
        content_path.write_text(result.content, encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "success": result.success,
                    "elapsed_seconds": result.elapsed_seconds,
                    "error": result.error,
                    "task": result.task_description,
                    "ws_url": args.ws_url,
                    "mode": args.mode,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Logs saved to: {log_path}")
        print(f"Content saved to: {content_path}")
        print(f"Meta saved to: {meta_path}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
