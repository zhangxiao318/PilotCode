"""Tokenizer accuracy verification.

Compares the current heuristic token estimation against tiktoken's cl100k_base
(which is the ground truth for OpenAI-compatible models).

Tests 5 groups of typical dialogue texts and analyzes error patterns.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tiktoken
from pilotcode.services.token_estimation import TokenEstimator
from pilotcode.services.precise_tokenizer import PreciseTokenizer

# ── Ground truth tokenizer ──────────────────────────────────────────────
GT_ENCODING = tiktoken.get_encoding("cl100k_base")


def ground_truth(text: str) -> int:
    """Official tiktoken token count (ground truth)."""
    return len(GT_ENCODING.encode(text))


def ground_truth_messages(messages: list[dict]) -> int:
    """Count tokens for messages using tiktoken with ChatML approximation.

    OpenAI uses cl100k_base with a specific chat template. This approximates
    the token count by rendering to a chat string and counting.
    """
    # Use tiktoken's model-based encoding if available
    try:
        enc = tiktoken.encoding_for_model("gpt-4")
    except Exception:
        enc = GT_ENCODING

    # Render messages as ChatML-like format (approximate)
    total = 0
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        if content is None:
            content = ""
        total += len(enc.encode(f"<|im_start|>{role}\n{content}<|im_end|>"))
    total += len(enc.encode("<|im_start|>assistant"))
    return total


# ── System under test ────────────────────────────────────────────────────


def heuristic_count(text: str, is_code: bool = False, provider: str = "") -> int:
    """Current heuristic estimation path."""
    estimator = TokenEstimator()
    # Force heuristic path (no backend)
    estimator._precise = False
    return estimator._heuristic_estimate(text, is_code, provider)


def precise_tiktoken_count(text: str) -> int | None:
    """PreciseTokenizer using tiktoken offline path."""
    p = PreciseTokenizer()
    return p._try_tiktoken(text)


def estimate_count(text: str, is_code: bool = False, provider: str = "") -> int:
    """Full TokenEstimator.estimate path (tries precise, falls back to heuristic)."""
    estimator = TokenEstimator()
    # With no base_url, it falls to offline paths then heuristic
    return estimator.estimate(text, is_code, provider)


# ── Test data: 5 groups ──────────────────────────────────────────────────

TEST_GROUPS = {
    "1. English Conversation": {
        "description": "Natural English dialogue with questions and answers",
        "texts": {
            "short": "Hello! How are you?",
            "medium": "I've been working on a Python project and ran into some issues with async/await. Could you help me understand how to properly handle exceptions in async functions?",
            "long": (
                "Thank you for your detailed explanation. I really appreciate the time you took "
                "to walk me through the solution. Let me summarize what I've learned: first, I need "
                "to use try/except blocks within each async function. Second, I should use "
                "asyncio.gather() with return_exceptions=True for concurrent tasks. Third, I need "
                "to be careful about cancellation handling. Is there anything else I should keep "
                "in mind when building production-grade async applications?"
            ),
        },
        "is_code": False,
        "provider": "openai",
    },
    "2. Code (Python + JSON)": {
        "description": "Code snippets with syntax-heavy content",
        "texts": {
            "python_func": (
                "async def fetch_data(url: str, timeout: float = 10.0) -> dict[str, Any]:\n"
                '    """Fetch JSON data from an API endpoint."""\n'
                "    async with aiohttp.ClientSession() as session:\n"
                "        async with session.get(url, timeout=timeout) as resp:\n"
                "            resp.raise_for_status()\n"
                "            return await resp.json()"
            ),
            "json_data": (
                '{"users": [{"id": 1, "name": "Alice", "roles": ["admin", "editor"]}, '
                '{"id": 2, "name": "Bob", "roles": ["viewer"]}], '
                '"pagination": {"page": 1, "per_page": 50, "total": 2}}'
            ),
            "shell_cmd": (
                "find /var/log -name '*.log' -mtime +7 -exec gzip {} \\; && "
                "docker compose -f docker-compose.prod.yml up -d --build --force-recreate"
            ),
        },
        "is_code": True,
        "provider": "",
    },
    "3. Chinese (CJK) Text": {
        "description": "Pure Chinese dialogue — tests CJK ratio handling",
        "texts": {
            "short": "你好，请问有什么可以帮助你的？",
            "medium": (
                "我需要开发一个Web应用程序，前端使用React框架，后端使用Python的FastAPI。"
                "数据库方面我打算使用PostgreSQL。你能帮我设计一下整体的架构吗？"
            ),
            "long": (
                "关于这个项目，我有以下需求：第一，系统需要支持多用户同时在线操作。"
                "第二，数据处理模块需要能够处理每天大约一百万条记录。"
                "第三，我们需要实时数据同步功能，当某个用户修改数据时，其他用户应该能够立即看到更新。"
                "第四，系统需要支持中英文双语界面。"
                "第五，所有API接口需要支持版本控制，以便未来升级时不影响现有客户端。"
                "你觉得这些需求合理吗？有什么建议吗？"
            ),
        },
        "is_code": False,
        "provider": "deepseek",
    },
    "4. Mixed Chinese + English + Code": {
        "description": "Realistic mixed content — the hardest case",
        "texts": {
            "tech_discussion": (
                "我最近在研究 transformer 模型的 attention mechanism。"
                "The key insight is that multi-head attention allows the model to "
                "jointly attend to information from different representation subspaces. "
                "具体来说，公式是：Attention(Q,K,V) = softmax(QK^T/√dk)V。"
                "在实现时需要注意以下几点：1) mask的维度要匹配 2) dropout要正确应用。"
            ),
            "bug_report": (
                "Bug Report #1234: 当用户输入包含emoji字符😀时，API返回500错误。\n"
                "Stack trace:\n"
                "  File 'encoder.py', line 42, in encode\n"
                "    encoded = text.encode('ascii')\n"
                "UnicodeEncodeError: 'ascii' codec can't encode character '\\U0001f600'\n"
                "修复方案：将 encode('ascii') 改为 encode('utf-8')。"
                "同时需要更新单元测试覆盖emoji边界情况。"
            ),
            "api_doc": (
                "## POST /api/v1/translate\n"
                "翻译文本接口。支持50+种语言互译。\n\n"
                "Request Body:\n"
                "```json\n"
                '{"source_lang": "zh", "target_lang": "en", '
                '"text": "人工智能正在改变世界"}\n'
                "```\n\n"
                "Response:\n"
                "```json\n"
                '{"translated": "Artificial intelligence is changing the world", '
                '"confidence": 0.98}\n'
                "```"
            ),
        },
        "is_code": False,
        "provider": "qwen",
    },
    "5. Special Characters & Markdown": {
        "description": "URLs, regex, markdown, emoji — edge cases",
        "texts": {
            "urls_and_paths": (
                "Check these URLs:\n"
                "- https://example.com/api/v1/users?page=1&limit=100\n"
                "- file:///home/user/projects/my-project/src/main.py\n"
                "- git@github.com:org/repo.git"
            ),
            "regex_and_patterns": (
                "Validation patterns:\n"
                r"Email: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                "\n"
                r"Phone: ^\+?[1-9]\d{1,14}$"
                "\n"
                r"Date: ^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
            ),
            "markdown_table": (
                "| Provider | Context Window | Max Output | Price/1M tokens |\n"
                "|----------|---------------|------------|------------------|\n"
                "| OpenAI   | 128K          | 4,096      | $2.50           |\n"
                "| Claude   | 200K          | 8,192      | $3.00           |\n"
                "| DeepSeek | 64K           | 8,192      | ¥1.00           |\n"
                "💡 Tip: Use DeepSeek for cost-sensitive workloads."
            ),
        },
        "is_code": False,
        "provider": "",
    },
}


# ── Analysis ──────────────────────────────────────────────────────────────


def analyze():
    print("=" * 80)
    print("TOKENIZER ACCURACY VERIFICATION REPORT")
    print("Ground Truth: tiktoken cl100k_base")
    print("=" * 80)

    all_results = []
    total_gt = 0
    total_heuristic = 0
    total_tiktoken_path = 0
    total_estimate = 0

    for group_name, group in TEST_GROUPS.items():
        print(f"\n{'─' * 60}")
        print(f"  {group_name}")
        print(f"  {group['description']}")
        print(f"{'─' * 60}")
        print(
            f"  {'Text':<20} {'GT':>6} {'Heuristic':>10} {'Err%':>8} {'TikToken':>10} {'Err%':>8} {'Estimate':>10} {'Err%':>8}"
        )
        print(f"  {'-'*20} {'-'*6} {'-'*10} {'-'*8} {'-'*10} {'-'*8} {'-'*10} {'-'*8}")

        group_results = []

        for text_name, text in group["texts"].items():
            gt = ground_truth(text)
            heu = heuristic_count(text, is_code=group["is_code"], provider=group["provider"])
            tik = precise_tiktoken_count(text)
            est = estimate_count(text, is_code=group["is_code"], provider=group["provider"])

            tik_val = tik if tik is not None else 0
            heu_err = (heu - gt) / gt * 100 if gt > 0 else 0
            tik_err = (tik_val - gt) / gt * 100 if gt > 0 and tik_val > 0 else 0
            est_err = (est - gt) / gt * 100 if gt > 0 else 0

            print(
                f"  {text_name:<20} {gt:>6} {heu:>10} {heu_err:>7.1f}% "
                f"{tik_val:>10} {tik_err:>7.1f}% {est:>10} {est_err:>7.1f}%"
            )

            group_results.append(
                {
                    "group": group_name,
                    "text": text_name,
                    "gt": gt,
                    "heuristic": heu,
                    "heuristic_err%": round(heu_err, 1),
                    "tiktoken_path": tik_val,
                    "tiktoken_err%": round(tik_err, 1),
                    "estimate": est,
                    "estimate_err%": round(est_err, 1),
                    "chars": len(text),
                    "chars_per_gt_token": round(len(text) / gt, 1) if gt > 0 else 0,
                }
            )

            total_gt += gt
            total_heuristic += heu
            total_tiktoken_path += tik_val
            total_estimate += est

        # Group summary
        gts = [r["gt"] for r in group_results]
        heu_errs = [abs(r["heuristic_err%"]) for r in group_results]
        if gts:
            avg_heu_err = sum(heu_errs) / len(heu_errs)
            print(f"  {'GROUP AVG':<20} {'':>6} {'':>10} {avg_heu_err:>7.1f}%")

        all_results.extend(group_results)

    # ── Overall Summary ──────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("OVERALL SUMMARY")
    print(f"{'=' * 80}")

    overall_heu_err = (total_heuristic - total_gt) / total_gt * 100 if total_gt > 0 else 0
    overall_tik_err = (
        (total_tiktoken_path - total_gt) / total_gt * 100
        if total_gt > 0 and total_tiktoken_path > 0
        else 0
    )
    overall_est_err = (total_estimate - total_gt) / total_gt * 100 if total_gt > 0 else 0

    print(f"  Total GT tokens:              {total_gt:>8}")
    print(f"  Total heuristic tokens:       {total_heuristic:>8}  ({overall_heu_err:+.1f}%)")
    print(f"  Total tiktoken-path tokens:   {total_tiktoken_path:>8}  ({overall_tik_err:+.1f}%)")
    print(f"  Total estimate() tokens:      {total_estimate:>8}  ({overall_est_err:+.1f}%)")

    # Per-group error analysis
    print(f"\n{'─' * 60}")
    print("PER-GROUP ERROR ANALYSIS")
    print(f"{'─' * 60}")

    groups_seen = {}
    for r in all_results:
        g = r["group"]
        if g not in groups_seen:
            groups_seen[g] = []
        groups_seen[g].append(r)

    for g, results in groups_seen.items():
        heu_errs = [r["heuristic_err%"] for r in results]
        avg_heu = sum(heu_errs) / len(heu_errs)
        max_heu = max(heu_errs)
        min_heu = min(heu_errs)
        avg_ratio = sum(r["chars_per_gt_token"] for r in results) / len(results)
        print(
            f"  {g[:50]:<50} "
            f"avg_err={avg_heu:>+6.1f}% "
            f"range=[{min_heu:>+5.0f}%, {max_heu:>+5.0f}%] "
            f"avg_chars/tok={avg_ratio:.1f}"
        )

    # ── Diagnostic findings ──────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print("DIAGNOSTIC FINDINGS")
    print(f"{'─' * 60}")

    # Find worst underestimates
    sorted_by_err = sorted(all_results, key=lambda r: r["heuristic_err%"])
    worst_under = [r for r in sorted_by_err if r["heuristic_err%"] < 0][:3]
    worst_over = [r for r in sorted_by_err if r["heuristic_err%"] > 0][-3:]

    if worst_under:
        print("\n  ⚠️  Worst UNDERESTIMATES (heuristic < ground truth):")
        for r in worst_under:
            print(
                f"    [{r['group']}] {r['text']}: "
                f"GT={r['gt']}, heuristic={r['heuristic']} "
                f"({r['heuristic_err%']:+.1f}%)"
            )

    if worst_over:
        print("\n  ⚠️  Worst OVERESTIMATES (heuristic > ground truth):")
        for r in worst_over:
            print(
                f"    [{r['group']}] {r['text']}: "
                f"GT={r['gt']}, heuristic={r['heuristic']} "
                f"({r['heuristic_err%']:+.1f}%)"
            )

    # CJK-specific analysis
    cjk_results = [r for r in all_results if "Chinese" in r["group"]]
    if cjk_results:
        cjk_avg_err = sum(r["heuristic_err%"] for r in cjk_results) / len(cjk_results)
        print(f"\n  🔍 CJK text average heuristic error: {cjk_avg_err:+.1f}%")
        print(f"     (Using provider_ratio={TokenEstimator.PROVIDER_CJK_RATIOS})")

    # Check if error is stable
    all_heu_errs = [abs(r["heuristic_err%"]) for r in all_results]
    avg_abs_err = sum(all_heu_errs) / len(all_heu_errs)
    max_abs_err = max(all_heu_errs)
    print("\n  📊 Absolute error stats:")
    print(f"     Average: {avg_abs_err:.1f}%")
    print(f"     Maximum: {max_abs_err:.1f}%")
    print(
        f"     Stability: {'STABLE ✅' if max_abs_err < 30 else 'UNSTABLE ⚠️' if max_abs_err < 60 else 'HIGHLY UNSTABLE ❌'}"
    )

    # Verdict
    print(f"\n{'=' * 80}")
    print("VERDICT")
    print(f"{'=' * 80}")

    if avg_abs_err < 10 and max_abs_err < 25:
        print("  ✅ Tokenizer accuracy is GOOD. Error rates are within acceptable range.")
    elif avg_abs_err < 20 and max_abs_err < 50:
        print("  ⚠️  Tokenizer accuracy is MODERATE. Some text types show significant deviation.")
        print("      Consider tuning CJK ratios or adding text-type detection.")
    else:
        print("  ❌ Tokenizer accuracy is POOR. Significant deviations detected.")
        print("      The heuristic estimator needs recalibration.")

    # Specific findings
    if cjk_results and abs(cjk_avg_err) > 15:
        print("\n  🔧 Recommendation: Adjust PROVIDER_CJK_RATIOS.")
        print(f"     Current ratios: {TokenEstimator.PROVIDER_CJK_RATIOS}")
        print("     Suggested: measure actual ratios and update.")

    return all_results


if __name__ == "__main__":
    analyze()
