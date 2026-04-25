#!/usr/bin/env python3
"""WebSocket client to test PilotCode Web UI with automated permission handling.

Usage:
    python test_websocket_client.py
"""

import asyncio
import json
import sys
import time
import websockets

WS_URL = "ws://127.0.0.1:8081"
QUERY = (
    "请分析 /home/zx 下的 Python 项目，统计功能和代码量。"
    "重要：排除以下大目录（它们包含第三方/缓存代码，不是用户项目）："
    "swe-env、.local、.cache、.npm、.nvm、.openclaw、.kimi、.config、.claude\n"
    "步骤：\n"
    "1) 用 Bash 写一个 Python 分析脚本并保存到 /home/zx/python_analysis.py，"
    "   脚本功能：遍历 /home/zx 下所有目录，排除隐藏目录和上述大目录，"
    "   递归统计每个目录的 .py 文件数、代码行数、注释行数、空行数、函数数、类数，"
    "   输出 Markdown 表格到 /home/zx/python_analysis_report.md\n"
    "2) 运行 python3 /home/zx/python_analysis.py\n"
    "3) 用 FileRead 读取 /home/zx/python_analysis_report.md\n"
    "4) 把报告内容展示给我"
)


async def run_test():
    """Connect to PilotCode WebSocket, send query, handle permissions automatically."""
    print(f"[Client] Connecting to {WS_URL} ...")
    try:
        async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10) as ws:
            print("[Client] Connected")

            # 1. Create session
            session_id = f"test_sess_{int(time.time())}"
            await ws.send(json.dumps({
                "type": "session_create",
                "session_id": session_id,
            }))
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"[Client] Session response: {resp}")

            # 2. Send query
            print(f"[Client] Sending query: {QUERY[:80]}...")
            await ws.send(json.dumps({
                "type": "query",
                "message": QUERY,
                "session_id": session_id,
            }))

            # 3. Collect responses and auto-approve permissions
            start_time = time.time()
            timeout = 300  # 5 minutes max
            chunks = []
            tool_calls = []
            permissions_granted = 0
            errors = []
            is_complete = False

            while time.time() - start_time < timeout:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    print("[Client] No message for 30s, waiting...")
                    continue

                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print(f"[Client] Raw: {msg[:200]}")
                    continue

                msg_type = data.get("type", "")

                if msg_type == "streaming_start":
                    print(f"[Client] Stream started: {data.get('stream_id', '')}")

                elif msg_type == "streaming_chunk":
                    chunk = data.get("chunk", "")
                    chunks.append(chunk)
                    # Print progress indicator
                    if len(chunks) % 10 == 0:
                        print(f"[Client] Received {len(chunks)} chunks, {sum(len(c) for c in chunks)} chars")

                elif msg_type == "tool_call":
                    tool_name = data.get("tool_name", "")
                    tool_input = data.get("tool_input", {})
                    tool_calls.append({"name": tool_name, "input": tool_input})
                    print(f"[Client] Tool call: {tool_name} -> {json.dumps(tool_input, ensure_ascii=False)[:120]}")

                elif msg_type == "tool_progress":
                    print(f"[Client] Tool progress: {data.get('tool_name', '')} - {data.get('line', '')}")

                elif msg_type == "permission_request":
                    req_id = data.get("request_id", "")
                    tool_name = data.get("tool_name", "")
                    print(f"[Client] Permission request: {tool_name} ({req_id}) -> AUTO-GRANT")
                    await ws.send(json.dumps({
                        "type": "permission_response",
                        "request_id": req_id,
                        "granted": True,
                        "for_session": True,
                    }))
                    permissions_granted += 1

                elif msg_type == "user_question_request":
                    req_id = data.get("request_id", "")
                    question = data.get("question", "")
                    print(f"[Client] User question: {question[:100]}...")
                    # Auto-respond with a helpful answer
                    await ws.send(json.dumps({
                        "type": "user_question_response",
                        "request_id": req_id,
                        "response": "请继续分析，尽量全面地统计所有项目。",
                    }))

                elif msg_type == "system":
                    content = data.get("content", "")
                    print(f"[Client] System: {content[:150]}")

                elif msg_type == "thinking":
                    content = data.get("content", "")
                    print(f"[Client] Thinking: {content[:150]}...")

                elif msg_type == "streaming_complete":
                    content = data.get("content", "")
                    print(f"[Client] COMPLETE: {content[:300] if content else '(no content field)'}")
                    is_complete = True
                    break

                elif msg_type == "streaming_end":
                    print("[Client] Streaming ended (legacy signal)")
                    # Don't break here, wait for streaming_complete

                elif msg_type == "streaming_error":
                    error = data.get("error", "Unknown error")
                    print(f"[Client] ERROR: {error[:300]}")
                    errors.append(error)

                elif msg_type == "planning_progress":
                    content = data.get("content", "")
                    print(f"[Client] Plan: {content[:200]}")

                elif msg_type == "interrupted":
                    print("[Client] Interrupted")
                    break

                else:
                    print(f"[Client] [{msg_type}]: {json.dumps(data, ensure_ascii=False)[:200]}")

            # 4. Summary
            elapsed = time.time() - start_time
            full_response = "".join(chunks)

            print("\n" + "=" * 80)
            print("EXECUTION SUMMARY")
            print("=" * 80)
            print(f"Session:        {session_id}")
            print(f"Elapsed:        {elapsed:.1f}s")
            print(f"Chunks:         {len(chunks)}")
            print(f"Response chars: {len(full_response)}")
            print(f"Tool calls:     {len(tool_calls)}")
            print(f"Permissions:    {permissions_granted}")
            print(f"Errors:         {len(errors)}")
            print(f"Completed:      {is_complete}")
            print("-" * 80)

            if tool_calls:
                print("\nTools used:")
                for i, tc in enumerate(tool_calls, 1):
                    print(f"  {i}. {tc['name']}: {json.dumps(tc['input'], ensure_ascii=False)[:100]}")

            if errors:
                print("\nErrors encountered:")
                for e in errors:
                    print(f"  - {e[:200]}")

            print("\n" + "=" * 80)
            print("FULL RESPONSE")
            print("=" * 80)
            print(full_response[-5000:] if len(full_response) > 5000 else full_response)
            print("=" * 80)

            # Save to file
            result_file = "/tmp/pilotcode_websocket_result.json"
            with open(result_file, "w") as f:
                json.dump({
                    "session_id": session_id,
                    "elapsed": elapsed,
                    "query": QUERY,
                    "response": full_response,
                    "tool_calls": tool_calls,
                    "errors": errors,
                    "completed": is_complete,
                }, f, ensure_ascii=False, indent=2)
            print(f"\nResult saved to: {result_file}")

            return 0 if is_complete and not errors else 1

    except ConnectionRefusedError:
        print(f"[Client] ERROR: Cannot connect to {WS_URL}. Is the server running?")
        return 1
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[Client] ERROR: Connection closed unexpectedly: {e}")
        print(f"[Client] This may indicate the server blocked during a long-running operation.")
        return 1
    except Exception as e:
        print(f"[Client] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_test()))
