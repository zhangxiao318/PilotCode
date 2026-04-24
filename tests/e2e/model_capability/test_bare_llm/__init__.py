"""Layer 1: Bare LLM capability tests.

These tests bypass PilotCode entirely (no QueryEngine, no tools, no system prompt).
They measure the LLM's intrinsic coding abilities:
- Code understanding (comprehension, bug detection)
- Code generation (HumanEval/MBPP-style function synthesis)
- Instruction following (format constraints, negations)

If a test fails here, the root cause is the LLM itself, not PilotCode.
"""
