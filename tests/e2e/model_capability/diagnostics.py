"""Diagnostic attribution engine for the three-layer evaluation framework.

Given a test result from Layer 1, 2, or 3, produces a structured diagnosis
that identifies whether the root cause is:
- llm_capability       (Layer 1 failure -- code understanding/generation)
- llm_function_calling (Layer 2 failure -- tool selection/parameter filling)
- pilotcode_tool       (Layer 2 failure -- tool execution error)
- pilotcode_framework  (Layer 3 failure -- LoopGuard, timeout, compression, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine_helper import ToolRunResult


@dataclass
class DiagnosisReport:
    """Structured diagnosis report for a failed test."""

    primary_cause: (
        str  # "llm_capability" | "llm_function_calling" | "pilotcode_tool" | "pilotcode_framework"
    )
    confidence: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    layer: int = 0


def diagnose_layer1_failure(
    response: str,
    expected_contains: list[str] | None = None,
) -> DiagnosisReport:
    """Diagnose a Layer 1 (bare LLM) test failure.

    Layer 1 tests directly call the model with no tools. Any failure here
    means the LLM itself lacks the required capability.
    """
    evidence = ["Layer 1 (bare LLM) test failed"]
    recommendations = [
        "Consider upgrading the backend LLM to a stronger coding model",
        "For local models, verify quantization level is not too aggressive",
    ]

    if not response or len(response.strip()) < 10:
        evidence.append("Model returned an empty or extremely short response")
        recommendations.append("Check if model context window is sufficient")

    if expected_contains:
        missing = [kw for kw in expected_contains if kw.lower() not in response.lower()]
        if missing:
            evidence.append(f"Response missing expected content: {missing}")

    return DiagnosisReport(
        primary_cause="llm_capability",
        confidence=0.9,
        evidence=evidence,
        recommendations=recommendations,
        layer=1,
    )


def diagnose_layer2_failure(result: ToolRunResult) -> DiagnosisReport:
    """Diagnose a Layer 2 (LLM + Tools) test failure.

    Sub-diagnoses based on:
    - No tools called -> LLM function calling weak
    - Wrong tool / wrong params -> LLM function calling weak
    - Right tool + params, but execution error -> PilotCode tool bug
    - Tool success, but LLM keeps looping -> LLM planning weak
    """
    evidence = [f"Layer 2 test failed after {result.turn_count} turns"]
    recommendations: list[str] = []

    # Case A: No tools were called at all
    if not result.tool_calls:
        evidence.append("LLM did not call any tools")
        evidence.append(
            "This indicates weak function-calling capability or the model "
            "ignoring tool availability"
        )
        recommendations.extend(
            [
                "Verify the model supports native function calling / tool use",
                "Check if system prompt incorrectly discourages tool usage",
                "Consider tool-choice='required' for critical operations",
            ]
        )
        return DiagnosisReport(
            primary_cause="llm_function_calling",
            confidence=0.9,
            evidence=evidence,
            recommendations=recommendations,
            layer=2,
        )

    # Case B: Some tools failed to execute
    failed_tools = [tc for tc in result.tool_calls if not tc.execution_success]
    if failed_tools:
        for tc in failed_tools:
            evidence.append(
                f"Tool '{tc.name}' failed (turn {tc.turn}): {tc.execution_error or 'unknown error'}"
            )

        # Determine if failure is due to wrong params or tool bug
        param_errors = [
            tc
            for tc in failed_tools
            if tc.execution_error and "not found" in tc.execution_error.lower()
        ]
        validation_errors = [
            tc
            for tc in failed_tools
            if tc.execution_error
            and (
                "validation" in tc.execution_error.lower()
                or "invalid" in tc.execution_error.lower()
            )
        ]

        if param_errors or validation_errors:
            evidence.append("Tool failures appear related to incorrect parameters")
            recommendations.extend(
                [
                    "Improve tool descriptions in system prompt to clarify parameter formats",
                    "Add more examples of correct parameter usage",
                ]
            )
            return DiagnosisReport(
                primary_cause="llm_function_calling",
                confidence=0.75,
                evidence=evidence,
                recommendations=recommendations,
                layer=2,
            )

        # Tool executed with correct params but still failed -> tool implementation issue
        evidence.append("Tools were called with seemingly correct parameters but execution failed")
        recommendations.extend(
            [
                "Investigate the tool implementation for the failing operations",
                "Check if workspace restrictions or file permissions are blocking tool execution",
            ]
        )
        return DiagnosisReport(
            primary_cause="pilotcode_tool",
            confidence=0.8,
            evidence=evidence,
            recommendations=recommendations,
            layer=2,
        )

    # Case C: Tools executed successfully, but LLM behavior is wrong
    # e.g. keeps calling the same tool, goes into exploration loop
    if result.diagnostics.get("max_turns_reached"):
        evidence.append("LLM reached max turns limit, suggesting a loop or inability to complete")
        recommendations.extend(
            [
                "Review LoopGuard / exploration detection settings",
                "Check if tool results are being properly summarized for the LLM",
                "Consider adding explicit step-counting in the system prompt",
            ]
        )

        # Try to determine if it's LLM loop vs framework loop
        tool_names = [tc.name for tc in result.tool_calls]
        # If same tool repeated many times -> likely LLM planning issue
        from collections import Counter

        counts = Counter(tool_names)
        most_common = counts.most_common(1)[0] if counts else (None, 0)
        if most_common[1] > 5:
            evidence.append(
                f"Tool '{most_common[0]}' was called {most_common[1]} times, "
                "suggesting LLM is stuck in a loop"
            )
            return DiagnosisReport(
                primary_cause="llm_function_calling",
                confidence=0.7,
                evidence=evidence,
                recommendations=recommendations,
                layer=2,
            )

        return DiagnosisReport(
            primary_cause="pilotcode_framework",
            confidence=0.6,
            evidence=evidence,
            recommendations=recommendations,
            layer=2,
        )

    # Fallback
    evidence.append("Unable to determine precise cause from available data")
    return DiagnosisReport(
        primary_cause="llm_function_calling",
        confidence=0.5,
        evidence=evidence,
        recommendations=recommendations,
        layer=2,
    )


def diagnose_layer3_failure(
    layer2_passed: bool,
    error_message: str = "",
) -> DiagnosisReport:
    """Diagnose a Layer 3 (E2E / WebSocket) test failure.

    If Layer 2 passed but Layer 3 failed, the issue is in PilotCode framework:
    - LoopGuard false positives
    - Timeout / heartbeat issues
    - Context compression losing information
    - System prompt differences between QueryEngine and WebSocketManager
    - Permission system blocking operations
    """
    evidence = ["Layer 3 (E2E WebSocket) test failed"]
    recommendations: list[str] = []

    if layer2_passed:
        evidence.append("Layer 2 (QueryEngine + direct tool execution) PASSED")
        evidence.append(
            "This isolates the problem to the PilotCode framework layer, "
            "not the LLM or tool implementations"
        )
        confidence = 0.85
    else:
        evidence.append("Layer 2 also failed -- issue may be deeper than framework")
        confidence = 0.5

    # Heuristic: classify by error message patterns
    err_lower = error_message.lower()

    if "timeout" in err_lower:
        evidence.append("Failure pattern: timeout")
        recommendations.extend(
            [
                "Increase recv timeout or total step timeout",
                "Verify server heartbeat (tool_progress) is working during long operations",
                "Check if LLM is silently stalling (no streaming chunks)",
            ]
        )

    if "loop" in err_lower or "guard" in err_lower:
        evidence.append("Failure pattern: LoopGuard intervention")
        recommendations.extend(
            [
                "Review LoopGuard thresholds for false positives",
                "Check if the task legitimately requires many exploration steps",
                "Consider whitelist for known-safe repetitive tool sequences",
            ]
        )

    if "permission" in err_lower or "denied" in err_lower:
        evidence.append("Failure pattern: permission denied")
        recommendations.extend(
            [
                "Check permission auto-allow settings for the test environment",
                "Verify tool risk analyzer is not over-classifying safe operations",
            ]
        )

    if "compress" in err_lower or "compact" in err_lower:
        evidence.append("Failure pattern: context compression")
        recommendations.extend(
            [
                "Increase context window threshold for compaction",
                "Verify critical tool results are preserved during compaction",
            ]
        )

    if not recommendations:
        recommendations.extend(
            [
                "Compare system prompts between QueryEngine and WebSocketManager",
                "Check for differences in tool reinforcement / retry logic",
                "Verify session state is correctly maintained across WebSocket reconnects",
            ]
        )

    return DiagnosisReport(
        primary_cause="pilotcode_framework",
        confidence=confidence,
        evidence=evidence,
        recommendations=recommendations,
        layer=3,
    )


def diagnose_failure(
    layer: int,
    result: Any | None = None,
    layer2_passed: bool = False,
    error_message: str = "",
    expected_contains: list[str] | None = None,
) -> DiagnosisReport:
    """Unified entry point for diagnosis across all three layers.

    Args:
        layer: 1, 2, or 3
        result: For Layer 2, a ToolRunResult. For Layer 1, the response string.
        layer2_passed: For Layer 3 diagnosis, whether Layer 2 passed.
        error_message: Error string for additional context.
        expected_contains: For Layer 1, expected content keywords.

    Returns:
        DiagnosisReport with primary cause, confidence, evidence, and recommendations.
    """
    if layer == 1:
        response = result if isinstance(result, str) else ""
        return diagnose_layer1_failure(response, expected_contains)

    if layer == 2:
        if isinstance(result, ToolRunResult):
            return diagnose_layer2_failure(result)
        return DiagnosisReport(
            primary_cause="unknown",
            confidence=0.0,
            evidence=["No ToolRunResult provided for Layer 2 diagnosis"],
            layer=2,
        )

    if layer == 3:
        return diagnose_layer3_failure(layer2_passed, error_message)

    return DiagnosisReport(
        primary_cause="unknown",
        confidence=0.0,
        evidence=[f"Invalid layer: {layer}"],
        layer=layer,
    )
