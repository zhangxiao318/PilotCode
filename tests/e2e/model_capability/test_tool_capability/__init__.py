"""Layer 2: LLM + Tool Calling capability tests.

These tests use QueryEngine with the full tool execution loop (via
engine_helper.run_with_tools()). They measure:
- Tool selection strategy (pick the right tool for the job)
- Task planning (multi-step decomposition)
- Code editing (read -> edit -> verify)

Failure attribution:
- Wrong tool / wrong params -> llm_function_calling
- Tool execution error despite correct params -> pilotcode_tool
- Tool success but LLM loops -> llm_function_calling or llm_capability
"""
