#!/usr/bin/env python3
"""WebSocket client for PilotCode end-to-end test.

Usage:
    python websocket_client.py "Your task description"

The client auto-approves permissions and answers simple questions so that
the backend model can work autonomously.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

WS_URL = "ws://127.0.0.1:8081"
TIMEOUT_SECONDS = 600  # 10 minutes max


async def run_task(task_description: str) -> dict:
    """Connect to PilotCode WebSocket and run a task autonomously."""
    logs: list[str] = []
    final_content_parts: list[str] = []
    pending_permissions: list[dict] = []
    pending_questions: list[dict] = []
    stream_ended = asyncio.Event()

    def log(msg: str):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        logs.append(line)

    async with websockets.connect(WS_URL) as ws:
        log(f"Connected to {WS_URL}")

        # Create session
        await ws.send(json.dumps({"type": "session_create"}))
        resp = await ws.recv()
        data = json.loads(resp)
        session_id = data.get("session_id", "")
        log(f"Session created: {session_id}")

        # Send query with PLAN mode to force structured mission execution
        await ws.send(
            json.dumps(
                {
                    "type": "query",
                    "session_id": session_id,
                    "message": task_description,
                    "mode": "PLAN",
                }
            )
        )
        log(f"Query sent: {task_description[:80]}...")

        # Message loop
        deadline = asyncio.get_event_loop().time() + TIMEOUT_SECONDS

        while asyncio.get_event_loop().time() < deadline:
            try:
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError:
                # Check if stream ended
                if stream_ended.is_set() and not pending_permissions and not pending_questions:
                    log("Stream ended and no pending interactions.")
                    break
                continue

            msg = json.loads(msg_raw)
            msg_type = msg.get("type", "")

            if msg_type == "streaming_start":
                log(f"Stream started: {msg.get('stream_id','')}")

            elif msg_type == "streaming_chunk":
                chunk = msg.get("chunk", "")
                final_content_parts.append(chunk)
                # Print progress indicator every ~500 chars
                if len(final_content_parts) % 10 == 0:
                    log(f"  ... received {sum(len(p) for p in final_content_parts)} chars")

            elif msg_type == "tool_call":
                tool_name = msg.get("tool_name", "")
                tool_input = msg.get("tool_input", {})
                log(f"Tool call: {tool_name}({json.dumps(tool_input)[:100]}...)")

            elif msg_type == "tool_progress":
                log(f"Tool progress: {msg.get('tool_name','')} - {msg.get('line','')}")

            elif msg_type == "permission_request":
                req_id = msg.get("request_id", "")
                tool_name = msg.get("tool_name", "")
                log(f"Permission request: {tool_name} (req={req_id})")
                pending_permissions.append(msg)
                # Auto-approve for session
                await ws.send(
                    json.dumps(
                        {
                            "type": "permission_response",
                            "request_id": req_id,
                            "granted": True,
                            "for_session": True,
                        }
                    )
                )
                log(f"Auto-approved permission: {tool_name}")

            elif msg_type == "user_question_request":
                req_id = msg.get("request_id", "")
                question = msg.get("question", "")
                options = msg.get("options")
                log(f"User question: {question[:100]}")
                pending_questions.append(msg)
                # Auto-answer with simple confirmation
                if options:
                    answer = options[0]
                else:
                    answer = "Yes, proceed."
                await ws.send(
                    json.dumps(
                        {
                            "type": "user_question_response",
                            "request_id": req_id,
                            "response": answer,
                        }
                    )
                )
                log(f"Auto-answered: {answer}")

            elif msg_type == "system":
                content = msg.get("content", "")
                log(f"System: {content[:200]}")

            elif msg_type == "planning_progress":
                content = msg.get("content", "")
                log(f"Plan progress:\n{content[:500]}")

            elif msg_type == "streaming_complete":
                content = msg.get("content", "")
                if content:
                    final_content_parts.append(content)
                log("Stream complete.")
                stream_ended.set()

            elif msg_type == "streaming_error":
                error = msg.get("error", "Unknown error")
                log(f"ERROR: {error}")
                stream_ended.set()

            elif msg_type == "interrupted":
                log("Interrupted.")
                stream_ended.set()

            elif msg_type == "thinking":
                content = msg.get("content", "")
                log(f"Thinking: {content[:150]}...")

            else:
                log(f"Unknown msg type: {msg_type}")

        # Close gracefully
        await ws.close()
        log("WebSocket closed.")

    final_content = "".join(final_content_parts)
    return {
        "logs": "\n".join(logs),
        "content": final_content,
        "success": "error" not in final_content.lower() or len(final_content) > 200,
    }


async def main():
    if len(sys.argv) < 2:
        task = (
            "请帮我实现两个功能修改：\n"
            "1. 目前探测模型能力后输出的 model_capability.json 位置和模型配置 settings.json 的位置不一样。"
            "settings.json 在 ~/.config/pilotcode/settings.json，而 model_capability.json 在 ~/.pilotcode/model_capability.json。"
            "请将 model_capability.json 的默认保存和读取位置也统一到 ~/.config/pilotcode/ 目录下。\n"
            "2. 运行 `config --list` 时，如果当前使用的是本地模型（model_provider 为 custom 或 ollama，或者 base_url 是本地地址），"
            "检查 ~/.config/pilotcode/model_capability.json 是否存在。如果不存在，或者里面的 model_name 和 settings.json 中的 default_model 不一致，"
            "提示用户运行 `config --test capability` 评估本地模型的性能。\n"
            "请仔细修改相关文件，确保修改完整且正确。"
        )
    else:
        task = sys.argv[1]

    result = await run_task(task)

    # Save results
    out_dir = Path("/home/zx/mycc/PilotCode/logs")
    out_dir.mkdir(exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = out_dir / f"e2e_test_{ts}.log"
    content_path = out_dir / f"e2e_test_{ts}.content.txt"

    log_path.write_text(result["logs"], encoding="utf-8")
    content_path.write_text(result["content"], encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Logs saved to: {log_path}")
    print(f"Content saved to: {content_path}")
    print(f"Success: {result['success']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
