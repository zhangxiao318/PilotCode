#!/usr/bin/env python3
"""E2E Test Result Analyzer.

Parses a pytest JUnit XML report and classifies failures by root cause.

Usage:
    # 1. Run tests with JUnit XML output
    pytest tests/e2e/model_capability/ --run-llm-e2e -v \
        --junitxml=/tmp/e2e_results.xml

    # 2. Analyze
    python tests/e2e/analyze_results.py /tmp/e2e_results.xml

    # Or pipe directly
    pytest tests/e2e/model_capability/ --run-llm-e2e -v \
        --junitxml=/tmp/e2e_results.xml && \
        python tests/e2e/analyze_results.py /tmp/e2e_results.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

CLASSIFIERS = [
    ("timeout", [
        "TimeoutError",
        "CancelledError",
        "asyncio.exceptions.TimeoutError",
    ]),
    ("thinking_pollution", [
        "<think>",
        "</think>",
        "Here's a thinking process:",
        "Thinking Process:",
        "Analyze User Input:",
    ]),
    ("context_retention", [
        "should NOT FileRead again",
        "should NOT Glob again",
    ]),
    ("file_edit_failed", [
        "File was not modified",
        "Method not added",
        "File was not created",
        "Should edit the file",
    ]),
    ("tool_param_mismatch", [
        "Param '",
    ]),
]


def classify_failure(message: str) -> str:
    """Classify a single failure message into a root-cause bucket."""
    msg = message
    # Check explicit classifiers in priority order
    for category, markers in CLASSIFIERS:
        for marker in markers:
            if marker in msg:
                return category
    # Fallback: generic assertion
    if "AssertionError" in msg:
        return "assertion_mismatch"
    return "other"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Failure:
    test_id: str
    file: str
    classname: str
    message: str
    category: str
    raw_traceback: str = ""


@dataclass
class Report:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    failures: List[Failure] = field(default_factory=list)
    by_category: Dict[str, List[Failure]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_junit(xml_path: str) -> Report:
    """Parse a JUnit XML file and produce a classified report."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    report = Report()

    # Collect all <testsuite> elements regardless of nesting depth
    suites: list[ET.Element] = list(root.iter("testsuite"))
    if not suites and root.tag == "testsuite":
        suites = [root]

    for suite in suites:
        report.total += int(suite.get("tests", 0))
        report.passed += int(suite.get("tests", 0)) - int(suite.get("failures", 0)) - int(suite.get("errors", 0)) - int(suite.get("skipped", 0))
        report.failed += int(suite.get("failures", 0))
        report.errors += int(suite.get("errors", 0))
        report.skipped += int(suite.get("skipped", 0))

        for case in suite.findall("testcase"):
            cls = case.get("classname", "")
            name = case.get("name", "")
            file_path = case.get("file", "")
            test_id = f"{cls}::{name}" if cls else name

            # Look for failure / error child
            failure_elems = list(case.iter("failure"))
            error_elems = list(case.iter("error"))
            elem = failure_elems[0] if failure_elems else (error_elems[0] if error_elems else None)
            if elem is None:
                continue

            msg = elem.get("message", "")
            traceback = elem.text or ""
            category = classify_failure(msg + "\n" + traceback)

            failure = Failure(
                test_id=test_id,
                file=file_path,
                classname=cls,
                message=msg,
                category=category,
                raw_traceback=traceback,
            )
            report.failures.append(failure)
            report.by_category.setdefault(category, []).append(failure)

    return report


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

CATEGORY_NAMES = {
    "timeout": "⏱  模型响应超时",
    "thinking_pollution": "🧠 Thinking 过程污染输出",
    "tool_param_mismatch": "🔧 工具参数不匹配",
    "file_edit_failed": "📝 文件编辑未生效",
    "context_retention": "🔄 上下文保持失败（重复调用工具）",
    "assertion_mismatch": "❌ 普通断言失败",
    "other": "❓ 其他",
}

CATEGORY_EMOJI = {
    "timeout": "⏱",
    "thinking_pollution": "🧠",
    "tool_param_mismatch": "🔧",
    "file_edit_failed": "📝",
    "context_retention": "🔄",
    "assertion_mismatch": "❌",
    "other": "❓",
}


def print_report(report: Report) -> None:
    """Print a human-readable report."""
    print("=" * 70)
    print("  E2E 测试结果分析报告")
    print("=" * 70)
    print()
    print(f"  总用例数 : {report.total}")
    print(f"  ✅ 通过  : {report.passed}")
    print(f"  ❌ 失败  : {report.failed}")
    print(f"  ⚠️  错误  : {report.errors}")
    print(f"  ⏭️  跳过  : {report.skipped}")
    print()

    if not report.failures:
        print("  🎉 所有测试通过！")
        return

    print("-" * 70)
    print("  失败根因分类")
    print("-" * 70)
    print()

    # Sort categories by count descending
    sorted_categories = sorted(
        report.by_category.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )

    for category, failures in sorted_categories:
        emoji = CATEGORY_EMOJI.get(category, "❓")
        name = CATEGORY_NAMES.get(category, category)
        print(f"  {emoji} {name} — {len(failures)} 个")
        for f in failures:
            short_msg = f.message[:80].replace("\n", " ")
            print(f"      • {f.test_id}")
            print(f"        └─ {short_msg}{'...' if len(f.message) > 80 else ''}")
        print()

    print("-" * 70)
    print("  归因建议")
    print("-" * 70)
    print()

    advice_map = {
        "timeout": (
            "模型响应超时。建议：\n"
            "  • 增加 --e2e-timeout（当前默认值 120s）\n"
            "  • 检查模型后端负载或网络连通性\n"
            "  • 对慢模型标记为 @pytest.mark.flaky"
        ),
        "thinking_pollution": (
            "模型输出了 reasoning/thinking 过程。建议：\n"
            "  • 在测试 helper 中使用 strip_thinking() 过滤\n"
            "  • 或关闭模型的 thinking 模式（如 vLLM enable_thinking=False）\n"
            "  • 已在 test_bare_llm/helpers.py 提供过滤函数"
        ),
        "tool_param_mismatch": (
            "LLM 生成的工具参数不符合预期。建议：\n"
            "  • 优化 tool schema description，明确参数格式\n"
            "  • 放宽测试断言（如允许 **/*.py 代替 *.py）\n"
            "  • 这是 LLM 工具调用能力的真实反映"
        ),
        "file_edit_failed": (
            "FileEdit/FileWrite 未成功修改文件。建议：\n"
            "  • 检查 FileEdit 的 validation 逻辑（需先 FileRead）\n"
            "  • 检查 FileWrite 的 conflict detection 是否过严\n"
            "  • 查看工具返回的具体错误信息"
        ),
        "context_retention": (
            "多轮对话中 LLM 未能记住上下文，重复调用工具。建议：\n"
            "  • 检查 QueryEngine 的 message history 是否正确传递\n"
            "  • 检查 context compaction 是否过早丢弃了关键信息\n"
            "  • 增加 system prompt 中的上下文保持提示"
        ),
        "assertion_mismatch": (
            "输出内容不符合断言预期。建议：\n"
            "  • 检查 prompt 是否足够明确\n"
            "  • 放宽断言条件（如大小写不敏感匹配）\n"
            "  • 这是 LLM 指令遵循能力的直接反映"
        ),
        "other": (
            "未分类的失败。建议：\n"
            "  • 查看完整 traceback 确定根因\n"
            "  • 可能是 PilotCode 系统 bug，需人工分析"
        ),
    }

    for category, _ in sorted_categories:
        advice = advice_map.get(category, advice_map["other"])
        name = CATEGORY_NAMES.get(category, category)
        print(f"  {CATEGORY_EMOJI.get(category, '❓')} {name}")
        for line in advice.splitlines():
            print(f"     {line}")
        print()

    print("=" * 70)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <junit-xml-path>")
        print()
        print("Example:")
        print("  pytest tests/e2e/ --run-llm-e2e --junitxml=/tmp/e2e.xml")
        print(f"  {sys.argv[0]} /tmp/e2e.xml")
        return 1

    xml_path = sys.argv[1]
    if not Path(xml_path).exists():
        print(f"Error: file not found: {xml_path}")
        return 1

    report = parse_junit(xml_path)
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
