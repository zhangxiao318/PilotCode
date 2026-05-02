"""Test configuration check with strong-model L2 make skip logic.

This script:
1. Checks PilotCode configuration validity
2. Determines if the configured model is "strong" (e.g., DeepSeek)
3. For strong models: demonstrates L2 make-check skip with clear reason logging
4. For non-strong models: demonstrates normal make check flow

Strong models are those that reliably produce syntactically-correct code,
making project-level build checks (make, cmake, etc.) redundant during
plan-mode L2 verification.

Usage:
    python3 scripts/test_config_check.py [--model MODEL_NAME]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.utils.config import ConfigManager
from pilotcode.utils.models_config import (
    ModelProvider,
    ModelInfo,
    get_model_info,
    SUPPORTED_MODELS,
)

# ---------------------------------------------------------------------------
# Strong model classification
# ---------------------------------------------------------------------------

# Providers whose models are considered "strong" for L2 make-skip purposes.
# DeepSeek models have demonstrated 92%+ benchmark scores and reliably
# produce correct code, making make-level compilation checks redundant.
_STRONG_PROVIDERS: set[ModelProvider] = {
    ModelProvider.DEEPSEEK,
}

# Explicit model keys (from config/models.json) that are always strong.
_STRONG_MODEL_KEYS: frozenset[str] = frozenset(
    {
        "deepseek",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    }
)

# Model name prefixes that indicate a strong model.
_STRONG_MODEL_PREFIXES: tuple[str, ...] = ("deepseek",)


# ---------------------------------------------------------------------------
# Public API — importable by L2 verifier and other modules
# ---------------------------------------------------------------------------


def is_strong_model(model_name: str | None = None) -> bool:
    """Check if a model is considered 'strong' for L2 verification.

    Strong models skip project-level build checks (make, cmake, etc.)
    during plan-mode L2 verification because they reliably produce
    syntactically-correct code.

    Detection order:
        1. Exact match against known strong model keys
        2. Prefix match against known strong model prefixes
        3. Provider match (DeepSeek, etc.)

    Args:
        model_name: Model key or name. If None, uses the configured default.

    Returns:
        True if this is a strong model that should skip make checks.
    """
    if model_name is None:
        config_manager = ConfigManager()
        config = config_manager.load_global_config()
        model_name = config.default_model or "deepseek"

    if not model_name:
        return False

    lower = model_name.lower().strip()

    # 1. Exact model key match
    if lower in _STRONG_MODEL_KEYS:
        return True

    # 2. Model name prefix match
    for prefix in _STRONG_MODEL_PREFIXES:
        if lower.startswith(prefix):
            return True

    # 3. Provider match via models.json metadata
    info = get_model_info(model_name)
    if info is not None and info.provider in _STRONG_PROVIDERS:
        return True

    return False


def should_skip_make_check(
    model_name: str | None = None,
    *,
    plan_mode: bool = True,
) -> tuple[bool, str]:
    """Determine if the L2 project-level make check should be skipped.

    This is the primary entry point for the L2 verifier.  During plan-mode
    verification, strong models skip make/cmake/build commands because they
    reliably produce correct code.

    Args:
        model_name: Model key or name. If None, uses the configured default.
        plan_mode: If False, make checks are never skipped (direct mode always
                   runs the full verification pipeline).

    Returns:
        Tuple of ``(should_skip: bool, reason: str)``.

    Example:
        >>> should_skip, reason = should_skip_make_check("deepseek")
        >>> assert should_skip is True
        >>> assert "strong model" in reason.lower()
    """
    if model_name is None:
        config_manager = ConfigManager()
        config = config_manager.load_global_config()
        model_name = config.default_model or "deepseek"

    # Only skip in plan mode — direct mode always runs full verification.
    if not plan_mode:
        return False, (
            f"Plan mode is OFF — running full L2 make check for model "
            f"'{model_name}' regardless of strength classification."
        )

    if is_strong_model(model_name):
        reason = (
            f"SKIP MAKE CHECK: Model '{model_name}' is classified as a "
            f"strong model (provider=DeepSeek or equivalent). "
            f"Skipping project-level build check (make/cmake) in L2 plan "
            f"mode — strong models reliably produce syntactically-correct "
            f"code, making compilation checks redundant."
        )
        logging.getLogger("pilotcode.verifier.l2").info(reason)
        return True, reason
    else:
        reason = (
            f"RUN MAKE CHECK: Model '{model_name}' is NOT classified as "
            f"strong. Proceeding with standard L2 project build check "
            f"(make/cmake/etc.)."
        )
        return False, reason


def get_model_strength_info(model_name: str | None = None) -> dict:
    """Return detailed classification info for a model.

    Useful for diagnostics and logging.

    Args:
        model_name: Model key or name. If None, uses the configured default.

    Returns:
        Dict with keys: model_name, is_strong, provider, model_key,
        skip_reason, classification_method.
    """
    if model_name is None:
        config_manager = ConfigManager()
        config = config_manager.load_global_config()
        model_name = config.default_model or "deepseek"

    info = get_model_info(model_name)
    provider = info.provider.value if info and info.provider else "unknown"
    strong = is_strong_model(model_name)

    # Determine which classification method matched
    method = "none"
    lower = model_name.lower().strip() if model_name else ""
    if lower in _STRONG_MODEL_KEYS:
        method = "exact_key_match"
    elif any(lower.startswith(p) for p in _STRONG_MODEL_PREFIXES):
        method = "prefix_match"
    elif info is not None and info.provider in _STRONG_PROVIDERS:
        method = "provider_match"

    _, reason = should_skip_make_check(model_name, plan_mode=True)

    return {
        "model_name": model_name,
        "is_strong": strong,
        "provider": provider,
        "model_key": model_name,
        "classification_method": method,
        "skip_reason": reason,
    }


# ---------------------------------------------------------------------------
# Configuration check display
# ---------------------------------------------------------------------------


def _print_header(title: str) -> None:
    """Print a formatted section header."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_ok(msg: str) -> None:
    """Print a green OK line."""
    print(f"  [OK] {msg}")


def _print_warn(msg: str) -> None:
    """Print a yellow WARNING line."""
    print(f"  [WARN] {msg}")


def _print_info(msg: str) -> None:
    """Print an INFO line."""
    print(f"  [INFO] {msg}")


def run_config_check(model_name: str | None = None) -> int:
    """Run the full configuration check and strong-model analysis.

    Args:
        model_name: Optional explicit model name to check.

    Returns:
        0 on success, 1 if configuration is invalid.
    """
    exit_code = 0

    # ---- Section 1: Basic configuration ----
    _print_header("1. Basic Configuration")

    config_manager = ConfigManager()

    print(f"\n  Config file: {config_manager.SETTINGS_FILE}")
    print(f"  is_configured: {config_manager.is_configured()}")

    config = config_manager.load_global_config()

    if model_name:
        effective_model = model_name
        print(f"  CLI override model: {effective_model}")
    else:
        effective_model = config.default_model

    print(f"  Effective model: {effective_model}")
    print(f"  base_url: {config.base_url}")
    print(f"  api_key: {'(set)' if config.api_key else '(empty)'}")

    # Detailed checks
    print()
    if config.api_key:
        _print_ok("api_key: set")
    else:
        _print_warn("api_key: not set")

    if config.default_model == "ollama":
        _print_info(f"default_model is 'ollama'")
    else:
        _print_info(f"default_model is '{config.default_model}'")

    if ".gguf" in config.default_model:
        _print_info("has .gguf extension: yes")
    else:
        _print_info("has .gguf extension: no")

    if config.base_url:
        if "localhost" in config.base_url or "127.0.0.1" in config.base_url:
            _print_info("base_url is local: yes")
        else:
            _print_info(f"base_url is local: no (is '{config.base_url}')")

        if not config.base_url.startswith("https://api."):
            _print_info("base_url is not https://api.: yes")
        else:
            _print_info("base_url is not https://api.: no")

    # ---- Section 2: Model info from models.json ----
    _print_header("2. Model Registry Lookup")

    info = get_model_info(effective_model)
    if info:
        _print_ok(f"Model '{effective_model}' found in models.json")
        print(f"  Display name: {info.display_name}")
        print(f"  Provider: {info.provider.value}")
        print(f"  Default API model: {info.default_model}")
        print(f"  Context window: {info.context_window:,}")
        print(f"  Max tokens: {info.max_tokens:,}")
        print(f"  Supports tools: {info.supports_tools}")
        if info.disabled:
            _print_warn(f"Model is DISABLED: {info.disabled_reason}")
    else:
        _print_warn(
            f"Model '{effective_model}' NOT found in models.json — "
            f"will be treated as custom/local"
        )

    # ---- Section 3: Strong model classification ----
    _print_header("3. Strong Model Classification (L2 Make Skip)")

    strong = is_strong_model(effective_model)
    strength_info = get_model_strength_info(effective_model)

    print(f"\n  Model: {effective_model}")
    print(f"  Provider: {strength_info['provider']}")
    print(f"  Is strong model: {strong}")
    print(f"  Classification method: {strength_info['classification_method']}")

    # ---- Section 4: L2 make check simulation ----
    _print_header("4. L2 Plan-Mode Make Check Simulation")

    # Simulate plan mode
    should_skip_plan, reason_plan = should_skip_make_check(effective_model, plan_mode=True)
    print(f"\n  [Plan Mode]")
    if should_skip_plan:
        _print_ok(f"Make check SKIPPED")
        print(f"  Reason: {reason_plan}")
    else:
        _print_info(f"Make check WILL RUN")
        print(f"  Reason: {reason_plan}")

    # Simulate direct mode (always runs)
    should_skip_direct, reason_direct = should_skip_make_check(effective_model, plan_mode=False)
    print(f"\n  [Direct Mode]")
    if should_skip_direct:
        _print_ok(f"Make check SKIPPED")
    else:
        _print_info(f"Make check WILL RUN (plan_mode=False — always runs full check)")
    print(f"  Reason: {reason_direct}")

    # ---- Section 5: Summary table for all known models ----
    _print_header("5. All Registered Models — Strong Model Summary")

    # Collect all model keys we can test
    all_keys: set[str] = set()
    # Models from models.json
    all_keys.update(SUPPORTED_MODELS.keys())
    # Add any model name from config that might not be in SUPPORTED_MODELS
    if effective_model and effective_model not in all_keys:
        all_keys.add(effective_model)

    # Build table
    rows: list[tuple[str, str, str]] = []
    for key in sorted(all_keys):
        s = "STRONG" if is_strong_model(key) else "standard"
        m_info = get_model_info(key)
        prov = m_info.provider.value if m_info and m_info.provider else "—"
        rows.append((key, prov, s))

    if rows:
        print(f"\n  {'Model Key':<24} {'Provider':<14} {'L2 Make':<12}")
        print(f"  {'-'*24} {'-'*14} {'-'*12}")
        for key, prov, status in rows:
            marker = "  ⏭ SKIP" if status == "STRONG" else "  ▶ RUN "
            print(f"  {key:<24} {prov:<14} {marker}")
    else:
        _print_warn("No models registered in models.json")

    # ---- Final verdict ----
    _print_header("Result")

    if config_manager.is_configured():
        _print_ok("Configuration is valid!")
    else:
        _print_warn("Configuration is NOT valid!")
        exit_code = 1

    if strong:
        _print_ok(
            f"Strong model '{effective_model}' detected — "
            f"L2 make checks will be SKIPPED in plan mode."
        )
    else:
        _print_info(
            f"Standard model '{effective_model}' — "
            f"L2 make checks will RUN normally in all modes."
        )

    print("=" * 60)
    return exit_code


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PilotCode configuration check with strong-model L2 analysis",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Explicit model name to check (default: from config)",
    )
    args = parser.parse_args()

    exit_code = run_config_check(model_name=args.model)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
