"""Backend LLM capability assessment tests for PilotCode.

Three-Layer Diagnostic Framework
================================

These tests diagnose whether failures are caused by the LLM itself or by
the PilotCode framework, using a three-layer contrast approach:

Layer 1 (test_bare_llm/)
    Direct model_client calls, NO tools, NO QueryEngine.
    Tests: code understanding, code generation, instruction following.
    Failure -> llm_capability (the model itself is weak)

Layer 2 (test_tool_capability/)
    QueryEngine + ToolExecutor with FULL tool execution loop.
    Tests: tool selection, task planning, code editing.
    Failure -> llm_function_calling OR pilotcode_tool (see diagnostics.py)

Layer 3 (tests/e2e/websocket/)
    WebSocket end-to-end with the complete PilotCode system.
    Tests: real user experience, session management, multi-turn tasks.
    If L1/L2 pass but L3 fails -> pilotcode_framework

Attribution Cheat Sheet
-----------------------
| L1    | L2    | L3    | Root Cause                          |
|-------|-------|-------|-------------------------------------|
| FAIL  | -     | -     | LLM基础能力弱                        |
| PASS  | FAIL  | -     | LLM function calling弱 或 工具实现问题 |
| PASS  | PASS  | FAIL  | PilotCode框架问题 (LoopGuard/超时/压缩) |

Run all layers:
    pytest tests/e2e/ --run-llm-e2e -v

Run only Layer 1 (fastest, no tool execution):
    pytest tests/e2e/model_capability/test_bare_llm/ --run-llm-e2e -v

Run only Layer 2:
    pytest tests/e2e/model_capability/test_tool_capability/ --run-llm-e2e -v
"""
