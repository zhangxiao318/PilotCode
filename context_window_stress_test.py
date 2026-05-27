#!/usr/bin/env python3
"""
Context Window Stress Test
==========================
独立运行脚本，验证 token 估算是否准确。

工作流程：
1. 读取配置，获取 LLM 连接信息
2. 获取模型的最大上下文窗口大小
3. 多轮次发送消息，逐渐填满上下文
4. 对比「估算 token 数」与「API 实际报告 token 数」
5. 在接近上下文上限时触发 overflow 检测
6. 输出详细分析报告，帮助定位估算误差

使用方法：
    python context_window_stress_test.py
    python context_window_stress_test.py --model deepseek --rounds 10
    python context_window_stress_test.py --target-fill 0.8   # 填满 80%
"""

import argparse
import asyncio
import contextlib
import io
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# 确保项目 src 目录在路径上
# ──────────────────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ──────────────────────────────────────────────────────────────────────────────
# 终端颜色助手
# ──────────────────────────────────────────────────────────────────────────────
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"

    @staticmethod
    def ok(s):
        return f"{Color.GREEN}{s}{Color.RESET}"

    @staticmethod
    def warn(s):
        return f"{Color.YELLOW}{s}{Color.RESET}"

    @staticmethod
    def err(s):
        return f"{Color.RED}{s}{Color.RESET}"

    @staticmethod
    def info(s):
        return f"{Color.CYAN}{s}{Color.RESET}"

    @staticmethod
    def bold(s):
        return f"{Color.BOLD}{s}{Color.RESET}"

    @staticmethod
    def gray(s):
        return f"{Color.GRAY}{s}{Color.RESET}"

    @staticmethod
    def cyan(s):
        return f"{Color.CYAN}{s}{Color.RESET}"


def sep(char="─", width=72):
    print(Color.gray(char * width))


# ──────────────────────────────────────────────────────────────────────────────
# 数据结构：单轮结果
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class RoundResult:
    """单轮对话的 token 统计结果"""

    round_num: int
    msg_count: int  # 当前消息条数（含 system）

    # 估算结果
    tiktoken_estimate: int = 0  # token_utils.count_messages_tokens
    heuristic_estimate: int = 0  # TokenEstimator.estimate（对话拼接）
    precise_count: int | None = None  # PreciseTokenizer.count_messages（本地后端）

    # API 实际报告（最权威）
    api_prompt_tokens: int | None = None
    api_completion_tokens: int | None = None
    api_total_tokens: int | None = None

    # 偏差分析（相对 API 实际值）
    tiktoken_error_pct: float | None = None
    heuristic_error_pct: float | None = None
    precise_error_pct: float | None = None

    # 其他
    prompt_text: str = ""
    response_text: str = ""
    elapsed_s: float = 0.0
    context_window: int = 0
    fill_pct: float = 0.0  # 当前占用上下文百分比（基于 API 实际值）
    overflow: bool = False


@dataclass
class TestSummary:
    """全局测试汇总"""

    model_name: str = ""
    context_window: int = 0
    max_tokens: int = 0
    rounds_completed: int = 0
    final_fill_pct: float = 0.0
    overflow_detected: bool = False
    overflow_at_round: int | None = None
    rounds: list[RoundResult] = field(default_factory=list)

    avg_tiktoken_error_pct: float | None = None
    avg_heuristic_error_pct: float | None = None
    avg_precise_error_pct: float | None = None


# ──────────────────────────────────────────────────────────────────────────────
# 内容生成器：每轮产生不同长度的用户消息
# ──────────────────────────────────────────────────────────────────────────────
_LOREM_SENTENCES = [
    "Explain the time complexity of quicksort in detail.",
    "Describe how transformer attention mechanisms work, covering multi-head attention, positional encoding, and layer normalization.",
    "Write a Python function that calculates the Fibonacci sequence using dynamic programming and explain each step.",
    "What are the key differences between TCP and UDP protocols? Discuss reliability, ordering, and use cases.",
    "Explain the CAP theorem in distributed systems and give a real-world example of each trade-off.",
    "How does garbage collection work in Java? Compare generational GC with G1GC.",
    "Describe the SOLID principles of object-oriented design with a code example for each.",
    "What is the difference between a mutex and a semaphore? When would you use each?",
    "Explain how consistent hashing works and why it is useful for distributed caches.",
    "Describe the event loop in Node.js and how async/await interacts with it.",
]

_PADDING_BLOCK = "The quick brown fox jumps over the lazy dog. " * 20


def build_user_message(round_num: int, target_tokens: int, base_text: str) -> str:
    """
    构造用户消息，通过重复填充使其接近 target_tokens 字符数
    （token ≈ char / 4，粗略估算后用真实计数器校验）。
    """
    topic = _LOREM_SENTENCES[round_num % len(_LOREM_SENTENCES)]
    padding_needed = max(0, target_tokens * 4 - len(topic) - len(base_text))
    padding = (_PADDING_BLOCK * ((padding_needed // len(_PADDING_BLOCK)) + 1))[:padding_needed]
    return f"{topic}\n\n{base_text}\n\n{padding}".strip()


# ──────────────────────────────────────────────────────────────────────────────
# 核心测试器
# ──────────────────────────────────────────────────────────────────────────────
class ContextWindowTester:
    def __init__(
        self,
        model_key: str | None = None,
        target_fill: float = 0.90,
        max_rounds: int = 30,
        tokens_per_round: int = 2000,
        verbose: bool = False,
    ):
        self.model_key = model_key
        self.target_fill = target_fill  # 停止阈值：达到上下文的 x%
        self.max_rounds = max_rounds
        self.tokens_per_round = tokens_per_round  # 每轮目标新增 token 数
        self.verbose = verbose

        # 运行时填充
        self.config = None
        self.model_client = None
        self.context_window = 0
        self.max_output_tokens = 0
        self.precise_tokenizer = None
        self.token_estimator = None
        self.messages: list[dict[str, Any]] = []
        self.summary = TestSummary()

    # ── 初始化 ─────────────────────────────────────────────────────────────────

    def setup(self):
        """加载配置、创建客户端、获取上下文窗口大小"""
        print(Color.bold("\n═══ 1. 配置加载 ═══"))

        # 1-a. ConfigManager
        from pilotcode.utils.config import ConfigManager

        mgr = ConfigManager()
        self.config = mgr.load_global_config()
        eff = mgr.get_effective_config()

        model_key = self.model_key or self.config.default_model or "deepseek"
        print(f"  模型 key   : {Color.info(model_key)}")
        print(f"  base_url   : {Color.info(self.config.base_url or '(from model config)')}")
        print(
            f"  api_key    : {Color.info('***' + (self.config.api_key or '')[-4:] if self.config.api_key else '(none)')}"
        )

        # 1-b. 上下文窗口
        from pilotcode.utils.models_config import get_model_context_window, get_model_max_tokens

        self.context_window = get_model_context_window(model_key)
        self.max_output_tokens = get_model_max_tokens(model_key)

        print(f"  context_window : {Color.ok(f'{self.context_window:,}')}")
        print(f"  max_output_tokens : {Color.ok(f'{self.max_output_tokens:,}')}")

        # 1-c. ModelClient
        from pilotcode.utils.model_client import ModelClient

        self.model_client = ModelClient(
            api_key=self.config.api_key or None,
            base_url=self.config.base_url or None,
            model=model_key,
        )
        print(f"  实际模型名  : {Color.info(self.model_client.model)}")

        # 1-d. PreciseTokenizer（本地后端专用，云 API 会静默失败）
        from pilotcode.services.precise_tokenizer import get_precise_tokenizer

        self.precise_tokenizer = get_precise_tokenizer(
            base_url=self.config.base_url or "",
            model_name=model_key,
        )

        # 1-e. TokenEstimator（启发式）
        from pilotcode.services.token_estimation import get_token_estimator

        self.token_estimator = get_token_estimator(
            base_url=self.config.base_url or "",
            model_name=model_key,
        )

        self.summary.model_name = f"{model_key} ({self.model_client.model})"
        self.summary.context_window = self.context_window
        self.summary.max_tokens = self.max_output_tokens

        sep()

    # ── 估算方法 ───────────────────────────────────────────────────────────────

    def _estimate_tiktoken(self, messages: list[dict]) -> int:
        """用 token_utils.count_messages_tokens 估算（tiktoken 后端）。
        token_utils 内部有 DEBUG print，用 contextlib.redirect_stdout 抑制。
        """
        try:
            from pilotcode.utils.token_utils import count_messages_tokens

            with contextlib.redirect_stdout(io.StringIO()):
                result = count_messages_tokens(messages, model_name=self.model_client.model)
            return result
        except Exception as e:
            if self.verbose:
                print(Color.warn(f"  [tiktoken] 失败: {e}"))
            return 0

    def _estimate_heuristic(self, messages: list[dict]) -> int:
        """用 TokenEstimator.estimate 对拼接文本估算（启发式）"""
        try:
            text = "\n".join(f"{m.get('role','')}: {m.get('content','')}" for m in messages)
            return self.token_estimator.estimate(text)
        except Exception as e:
            if self.verbose:
                print(Color.warn(f"  [heuristic] 失败: {e}"))
            return 0

    def _count_precise(self, messages: list[dict]) -> int | None:
        """用 PreciseTokenizer.count_messages 精确计数（本地后端）"""
        try:
            result = self.precise_tokenizer.count_messages(messages)
            return result
        except Exception as e:
            if self.verbose:
                print(Color.warn(f"  [precise] 失败: {e}"))
            return None

    # ── 单轮对话 ───────────────────────────────────────────────────────────────

    async def run_round(self, round_num: int) -> RoundResult:
        """执行一轮对话并收集 token 统计"""
        from pilotcode.utils.model_client import Message

        # 构造用户消息（每轮逐渐增大，模拟真实使用）
        accumulated_context = "\n".join(
            f"[Round {i} summary]: {m['content'][:80]}..."
            for i, m in enumerate(self.messages)
            if m["role"] == "assistant"
        )
        user_text = build_user_message(round_num, self.tokens_per_round, accumulated_context)

        self.messages.append({"role": "user", "content": user_text})

        # ── 事前估算（发送 API 之前）──────────────────────────────────────────
        tiktoken_est = self._estimate_tiktoken(self.messages)
        heuristic_est = self._estimate_heuristic(self.messages)
        precise_count = self._count_precise(self.messages)

        print(
            f"\n  [Round {round_num:02d}] msgs={len(self.messages)}  "
            f"tiktoken≈{tiktoken_est:,}  heuristic≈{heuristic_est:,}"
            + (f"  precise={precise_count:,}" if precise_count else "  precise=N/A")
        )

        # ── 调用 LLM API ──────────────────────────────────────────────────────
        api_msgs = [Message(role=m["role"], content=m["content"]) for m in self.messages]

        t0 = time.monotonic()
        response_text = ""
        api_usage: dict[str, Any] = {}

        try:
            async for chunk in self.model_client.chat_completion(
                api_msgs,
                max_tokens=min(256, self.max_output_tokens),
                stream=True,
                temperature=0.3,
            ):
                # 收集文本
                if "choices" in chunk and chunk["choices"]:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        response_text += content

                # 收集 usage（通常在最后一个 chunk）
                if chunk.get("usage"):
                    api_usage = chunk["usage"]

        except Exception as e:
            err_str = str(e)
            # 检测上下文溢出错误
            overflow_keywords = ["context", "token", "length", "exceeded", "too long", "maximum"]
            if any(k in err_str.lower() for k in overflow_keywords):
                print(Color.warn(f"    ⚠ API 返回上下文溢出错误: {err_str[:120]}"))
                result = RoundResult(
                    round_num=round_num,
                    msg_count=len(self.messages),
                    tiktoken_estimate=tiktoken_est,
                    heuristic_estimate=heuristic_est,
                    precise_count=precise_count,
                    context_window=self.context_window,
                    overflow=True,
                )
                return result
            else:
                print(Color.err(f"    ✗ API 调用失败: {err_str[:160]}"))
                raise

        elapsed = time.monotonic() - t0

        # 追加 assistant 回复
        self.messages.append({"role": "assistant", "content": response_text})

        # ── API 报告的 token 数 ────────────────────────────────────────────────
        api_prompt = api_usage.get("prompt_tokens")
        api_compl = api_usage.get("completion_tokens")
        api_total = api_usage.get("total_tokens")

        fill_pct = (
            (api_prompt / self.context_window * 100)
            if (api_prompt and self.context_window)
            else 0.0
        )

        # ── 误差计算 ──────────────────────────────────────────────────────────
        def pct_error(est, actual):
            if actual and actual > 0:
                return round((est - actual) / actual * 100, 2)
            return None

        tt_err = pct_error(tiktoken_est, api_prompt)
        heur_err = pct_error(heuristic_est, api_prompt)
        prec_err = pct_error(precise_count, api_prompt) if precise_count is not None else None

        # ── 打印本轮结果 ──────────────────────────────────────────────────────
        if api_prompt is not None:
            fill_bar = self._fill_bar(fill_pct)
            print(
                f"    API prompt_tokens = {Color.bold(f'{api_prompt:,}')}   "
                f"fill = {fill_bar} {fill_pct:.1f}%"
            )

            def fmt_err(err):
                if err is None:
                    return Color.gray("N/A")
                s = f"{err:+.1f}%"
                if abs(err) <= 5:
                    return Color.ok(s)
                if abs(err) <= 15:
                    return Color.warn(s)
                return Color.err(s)

            print(
                f"    误差  tiktoken={fmt_err(tt_err)}  "
                f"heuristic={fmt_err(heur_err)}  "
                f"precise={fmt_err(prec_err)}"
            )
        else:
            print(Color.gray("    API 未返回 usage 信息（某些服务商不提供）"))

        overflow = api_prompt is not None and api_prompt >= self.context_window * 0.97

        return RoundResult(
            round_num=round_num,
            msg_count=len(self.messages),
            tiktoken_estimate=tiktoken_est,
            heuristic_estimate=heuristic_est,
            precise_count=precise_count,
            api_prompt_tokens=api_prompt,
            api_completion_tokens=api_compl,
            api_total_tokens=api_total,
            tiktoken_error_pct=tt_err,
            heuristic_error_pct=heur_err,
            precise_error_pct=prec_err,
            prompt_text=user_text[:200],
            response_text=response_text[:200],
            elapsed_s=elapsed,
            context_window=self.context_window,
            fill_pct=fill_pct,
            overflow=overflow,
        )

    @staticmethod
    def _fill_bar(pct: float, width: int = 20) -> str:
        filled = int(pct / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        if pct < 50:
            color = Color.GREEN
        elif pct < 80:
            color = Color.YELLOW
        else:
            color = Color.RED
        return f"{color}[{bar}]{Color.RESET}"

    # ── 主测试循环 ─────────────────────────────────────────────────────────────

    async def run(self):
        """主测试入口"""
        self.setup()

        print(Color.bold("═══ 2. 开始多轮对话压力测试 ═══"))
        print(f"  目标填充率: {Color.info(f'{self.target_fill*100:.0f}%')}")
        print(f"  最大轮次  : {Color.info(str(self.max_rounds))}")
        print(f"  每轮目标tokens: {Color.info(str(self.tokens_per_round))}")
        sep()

        # system prompt 模拟
        system_content = (
            "You are a helpful assistant. "
            "Answer questions concisely and accurately. "
            "When context grows large, summarize previous points briefly."
        )
        self.messages = [{"role": "system", "content": system_content}]

        rounds: list[RoundResult] = []
        overflow_round = None

        for rnd in range(1, self.max_rounds + 1):
            result = await self.run_round(rnd)
            rounds.append(result)

            if result.overflow:
                overflow_round = rnd
                print(Color.warn(f"\n  ⚡ 上下文溢出检测于第 {rnd} 轮！停止测试。"))
                break

            if result.fill_pct >= self.target_fill * 100:
                print(
                    Color.warn(
                        f"\n  ✓ 已达目标填充率 {result.fill_pct:.1f}% >= {self.target_fill*100:.0f}%，停止测试。"
                    )
                )
                break

        # ── 汇总 ──────────────────────────────────────────────────────────────
        self.summary.rounds = rounds
        self.summary.rounds_completed = len(rounds)
        self.summary.overflow_detected = overflow_round is not None
        self.summary.overflow_at_round = overflow_round
        if rounds:
            self.summary.final_fill_pct = rounds[-1].fill_pct

        # 计算平均误差（只统计有 API 实际值的轮次）
        def avg_err(attr):
            vals = [getattr(r, attr) for r in rounds if getattr(r, attr) is not None]
            return round(sum(vals) / len(vals), 2) if vals else None

        self.summary.avg_tiktoken_error_pct = avg_err("tiktoken_error_pct")
        self.summary.avg_heuristic_error_pct = avg_err("heuristic_error_pct")
        self.summary.avg_precise_error_pct = avg_err("precise_error_pct")

        self._print_report()
        self._save_report()

    # ── 报告输出 ───────────────────────────────────────────────────────────────

    def _print_report(self):
        print(Color.bold("\n\n═══ 3. 测试报告 ═══"))
        sep("═")

        s = self.summary
        print(f"  模型         : {Color.bold(s.model_name)}")
        print(f"  上下文窗口   : {Color.bold(f'{s.context_window:,}')} tokens")
        print(f"  最大输出     : {Color.bold(f'{s.max_tokens:,}')} tokens")
        print(f"  完成轮次     : {s.rounds_completed}")
        print(f"  最终填充率   : {Color.ok(f'{s.final_fill_pct:.1f}%')}")
        print(
            f"  溢出检测     : {Color.warn('✓ 是') if s.overflow_detected else Color.ok('✗ 未触发')}"
            + (f"  (第 {s.overflow_at_round} 轮)" if s.overflow_at_round else "")
        )

        sep()
        print(Color.bold("  Token 估算准确度分析 (误差 = (估算-实际)/实际 × 100%)"))
        print()

        def fmt_avg(val, name):
            if val is None:
                return f"  {name:20s}: {Color.gray('N/A (API 未提供实际 token 数)')}"
            abs_v = abs(val)
            if abs_v <= 5:
                grade = Color.ok("优秀 (≤5%)")
            elif abs_v <= 15:
                grade = Color.warn("一般 (5-15%)")
            else:
                grade = Color.err("较差 (>15%)")
            sign = "+" if val >= 0 else ""
            return f"  {name:20s}: {sign}{val:.2f}%  → {grade}"

        print(fmt_avg(s.avg_tiktoken_error_pct, "tiktoken (token_utils)"))
        print(fmt_avg(s.avg_heuristic_error_pct, "heuristic (estimator)"))
        print(fmt_avg(s.avg_precise_error_pct, "precise (PreciseTokenizer)"))

        sep()
        print(Color.bold("  逐轮明细"))
        print(
            f"  {'轮次':>4}  {'msgs':>5}  {'tiktoken':>10}  {'heuristic':>10}  {'precise':>10}  {'API实际':>10}  {'填充%':>7}  {'误差tt':>8}  {'误差h':>8}"
        )
        sep("-", 72)
        for r in self.summary.rounds:
            api_s = f"{r.api_prompt_tokens:,}" if r.api_prompt_tokens else "N/A"
            prec_s = f"{r.precise_count:,}" if r.precise_count else "N/A"
            err_tt = f"{r.tiktoken_error_pct:+.1f}%" if r.tiktoken_error_pct is not None else "N/A"
            err_h = f"{r.heuristic_error_pct:+.1f}%" if r.heuristic_error_pct is not None else "N/A"
            fill_s = f"{r.fill_pct:.1f}%" if r.fill_pct else "N/A"

            # 着色误差
            def color_err(val, s):
                if val is None:
                    return Color.gray(s)
                if abs(val) <= 5:
                    return Color.ok(s)
                if abs(val) <= 15:
                    return Color.warn(s)
                return Color.err(s)

            line = (
                f"  {r.round_num:>4}  {r.msg_count:>5}  "
                f"{r.tiktoken_estimate:>10,}  {r.heuristic_estimate:>10,}  "
                f"{prec_s:>10}  {api_s:>10}  {fill_s:>7}  "
                f"{color_err(r.tiktoken_error_pct, err_tt):>8}  "
                f"{color_err(r.heuristic_error_pct, err_h):>8}"
            )
            print(line)

        sep()

        # 结论
        print(Color.bold("  结论与建议"))
        print()
        issues = []

        if s.avg_tiktoken_error_pct is not None and abs(s.avg_tiktoken_error_pct) > 15:
            issues.append(
                f"⚠ tiktoken 估算偏差较大 ({s.avg_tiktoken_error_pct:+.1f}%)，"
                "可能因为使用了错误的 tokenizer 或未考虑消息格式 overhead。"
                "\n    建议：检查 token_utils.count_messages_tokens 中的模型名映射。"
            )
        if s.avg_heuristic_error_pct is not None and abs(s.avg_heuristic_error_pct) > 20:
            issues.append(
                f"⚠ 启发式估算偏差较大 ({s.avg_heuristic_error_pct:+.1f}%)，"
                "字符/token 比率可能不适合当前模型（尤其是中文/混合内容）。"
                "\n    建议：检查 TokenEstimator.CHARS_PER_TOKEN 和 CJK 比率配置。"
            )
        if s.avg_precise_error_pct is not None and abs(s.avg_precise_error_pct) > 5:
            issues.append(
                f"⚠ PreciseTokenizer 偏差超出预期 ({s.avg_precise_error_pct:+.1f}%)，"
                "本地 /tokenize 端点应与 API 实际计数非常接近。"
                "\n    建议：检查 PreciseTokenizer 是否正确使用了 chat template。"
            )
        if not issues:
            print(Color.ok("  ✓ 所有估算方法偏差均在可接受范围内。"))
        else:
            for issue in issues:
                print(Color.warn(f"  {issue}"))
                print()

        sep("═")

    def _save_report(self):
        """将详细结果保存为 JSON 文件"""
        report_path = _PROJECT_ROOT / "context_window_test_report.json"
        data = {
            "model": self.summary.model_name,
            "context_window": self.summary.context_window,
            "max_output_tokens": self.summary.max_tokens,
            "rounds_completed": self.summary.rounds_completed,
            "final_fill_pct": self.summary.final_fill_pct,
            "overflow_detected": self.summary.overflow_detected,
            "overflow_at_round": self.summary.overflow_at_round,
            "avg_tiktoken_error_pct": self.summary.avg_tiktoken_error_pct,
            "avg_heuristic_error_pct": self.summary.avg_heuristic_error_pct,
            "avg_precise_error_pct": self.summary.avg_precise_error_pct,
            "rounds": [
                {
                    "round": r.round_num,
                    "msg_count": r.msg_count,
                    "tiktoken_estimate": r.tiktoken_estimate,
                    "heuristic_estimate": r.heuristic_estimate,
                    "precise_count": r.precise_count,
                    "api_prompt_tokens": r.api_prompt_tokens,
                    "api_completion_tokens": r.api_completion_tokens,
                    "api_total_tokens": r.api_total_tokens,
                    "tiktoken_error_pct": r.tiktoken_error_pct,
                    "heuristic_error_pct": r.heuristic_error_pct,
                    "precise_error_pct": r.precise_error_pct,
                    "fill_pct": r.fill_pct,
                    "overflow": r.overflow,
                    "elapsed_s": round(r.elapsed_s, 2),
                }
                for r in self.summary.rounds
            ],
        }
        report_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  📄 详细报告已保存至: {Color.info(str(report_path))}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(
        description="Context Window Stress Test — 验证 PilotCode token 估算准确性",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--model",
        "-m",
        default=None,
        help="模型 key（如 deepseek、openai、qwen），默认从 settings.json 读取",
    )
    p.add_argument(
        "--target-fill",
        "-f",
        type=float,
        default=0.85,
        metavar="0.0-1.0",
        help="停止测试的上下文填充率阈值（默认 0.85 = 85%%）",
    )
    p.add_argument(
        "--rounds",
        "-r",
        type=int,
        default=20,
        help="最大轮次（默认 20）",
    )
    p.add_argument(
        "--tokens-per-round",
        "-t",
        type=int,
        default=3000,
        help="每轮目标新增 token 数（默认 3000）",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示调试信息",
    )
    return p.parse_args()


async def main():
    args = parse_args()

    print(Color.bold(Color.cyan("\n╔══════════════════════════════════════════════╗")))
    print(Color.bold(Color.cyan("║   Context Window Stress Test                 ║")))
    print(Color.bold(Color.cyan("║   PilotCode Token 估算准确性验证工具         ║")))
    print(Color.bold(Color.cyan("╚══════════════════════════════════════════════╝")))

    tester = ContextWindowTester(
        model_key=args.model,
        target_fill=args.target_fill,
        max_rounds=args.rounds,
        tokens_per_round=args.tokens_per_round,
        verbose=args.verbose,
    )

    try:
        await tester.run()
    except KeyboardInterrupt:
        print(Color.warn("\n\n  ⚡ 用户中断，输出当前已收集的数据..."))
        if tester.summary.rounds:
            tester._print_report()
            tester._save_report()
    finally:
        if tester.model_client:
            try:
                await tester.model_client.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
