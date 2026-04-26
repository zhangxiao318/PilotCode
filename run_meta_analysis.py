#!/usr/bin/env python3
"""WebSocket client to run meta-analysis of PilotCode's orchestration system."""

import asyncio
import json
import websockets
import sys

WS_URL = "ws://127.0.0.1:28081"

# The meta-analysis prompt
ANALYSIS_PROMPT = """Refactor and improve the task orchestration system of the PilotCode project itself.

First, thoroughly analyze these files under src/pilotcode/orchestration/:
- adapter.py (MissionAdapter)
- orchestrator.py (Orchestrator)
- dag.py (DagExecutor)
- tracker.py (MissionTracker)
- state_machine.py (StateMachine)
- project_memory.py (ProjectMemory)
- context_strategy.py
- verifier/level2_tests.py

Also analyze src/pilotcode/agent/agent_orchestrator.py.

For each file, identify:
1. Design flaws and anti-patterns
2. Concurrency / race condition issues
3. Error handling gaps
4. Performance bottlenecks
5. Testing gaps

Then compare against the P-EVR (Plan-Execute-Verify-Reflect) architecture goals and identify gaps.

Finally, implement concrete improvements with line-number references.
"""


async def run_analysis():
    print(f"[*] Connecting to {WS_URL} ...")
    async with websockets.connect(WS_URL) as ws:
        print("[*] Connected. Creating session...")
        await ws.send(json.dumps({"type": "session_create"}))

        # Wait for session_created
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(msg)
            print(f"[→] {data.get('type')}: {json.dumps(data, ensure_ascii=False)[:200]}")
            if data.get("type") == "session_created":
                session_id = data.get("session_id")
                break

        print(f"[*] Session {session_id} ready. Sending analysis query...")
        print(f"[*] Query length: {len(ANALYSIS_PROMPT)} chars")
        await ws.send(
            json.dumps(
                {
                    "type": "query",
                    "message": ANALYSIS_PROMPT,
                    "session_id": session_id,
                    "mode": "PLAN",
                }
            )
        )

        print("[*] Waiting for streaming results (this may take a while)...\n")
        print("=" * 70)

        collected = []
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=300)
                data = json.loads(msg)
                msg_type = data.get("type", "")

                if msg_type == "streaming_start":
                    print(f"[STREAM START] {data.get('stream_id')}")

                elif msg_type == "streaming_chunk":
                    content = data.get("content", "") or data.get("chunk", "")
                    if content:
                        print(content, end="", flush=True)
                        collected.append(content)

                elif msg_type == "system":
                    content = data.get("content", "")
                    if content:
                        print(f"\n[SYSTEM] {content}\n")
                        collected.append(f"[SYSTEM] {content}\n")

                elif msg_type == "planning_progress":
                    content = data.get("content", "")
                    if content:
                        print(f"\n[PLAN] {content}\n")
                        collected.append(f"[PLAN] {content}\n")

                elif msg_type == "streaming_end":
                    print(f"\n[STREAM END] {data.get('stream_id')}")
                    break

                elif msg_type == "streaming_error":
                    print(f"\n[ERROR] {data.get('error')}")
                    break

                elif msg_type == "interrupted":
                    print(f"\n[INTERRUPTED] {data.get('message')}")
                    break

                elif msg_type in ("permission_request", "user_question"):
                    # Auto-approve permissions and answer questions
                    if msg_type == "permission_request":
                        request_id = data.get("request_id", "")
                        print(f"\n[PERMISSION] Auto-approving {request_id}")
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "permission_response",
                                    "request_id": request_id,
                                    "granted": True,
                                    "for_session": True,
                                }
                            )
                        )

        except asyncio.TimeoutError:
            print("\n[TIMEOUT] No message received for 300s")
        except websockets.exceptions.ConnectionClosed:
            print("\n[DISCONNECTED] WebSocket closed")

        print("=" * 70)
        print(f"\n[*] Total collected chars: {sum(len(c) for c in collected)}")

        # Save result
        result_text = "".join(collected)
        with open("/home/zx/mycc/PilotCode/meta_analysis_result.md", "w") as f:
            f.write("# PilotCode Orchestration Meta-Analysis\n\n")
            f.write(f"Session: {session_id}\n\n")
            f.write(result_text)
        print("[*] Result saved to meta_analysis_result.md")


if __name__ == "__main__":
    try:
        asyncio.run(run_analysis())
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user")
        sys.exit(0)
