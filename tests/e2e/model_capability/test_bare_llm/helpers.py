"""Shared helpers for bare-LLM capability tests.

Provides noise-filtering utilities for reasoning-model outputs.
"""

from __future__ import annotations



def strip_thinking(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from model output.

    Handles three common patterns seen in reasoning models:
    1. Full <think>...</think> blocks
    2. Standalone </think> with thinking preamble before it
    3. Missing <think> but present </think> (some vLLM deployments)

    Also strips common thinking preamble markers like
    "Here's a thinking process:" or "Thinking Process:".
    """
    if not text:
        return text

    # Case A: </think> markers — some models emit multiple closing tags.
    # Take everything after the LAST </think> (the actual response).
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]

    # Case B: full <think>...</think> blocks
    while "<think>" in text and "</think>" in text:
        start = text.find("<think>")
        end = text.find("</think>", start) + len("</think>")
        text = text[:start] + text[end:]

    text = text.strip()

    # Case C: heuristic — some models emit "Here's a thinking process:"
    # without any XML tags at all.  We can't reliably strip these, but
    # we can detect the most common trailing-answer pattern: if the text
    # ends with a clean short answer after a long preamble, keep only
    # the last paragraph if it's significantly shorter.
    lines = text.splitlines()
    if len(lines) > 5:
        # Check if last non-empty line is very short (likely the real answer)
        non_empty = [ln for ln in lines if ln.strip()]
        if len(non_empty) >= 2:
            last = non_empty[-1].strip()
            second_last = non_empty[-2].strip()
            # If last line is short and second-to-last looks like analysis...
            if len(last) < 30 and len(second_last) > 50:
                # Check if there's a dramatic length drop — heuristic for
                # "long analysis followed by short answer"
                return last

    return text
