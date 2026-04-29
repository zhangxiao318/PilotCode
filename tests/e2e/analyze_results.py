#!/usr/bin/env python3
"""Analyze and compare PilotCode E2E test results.

Usage:
    python analyze_results.py <summary.json>                  # Single run report
    python analyze_results.py <cli_summary.json> <ws_summary.json>  # Compare modes
"""
import json
import sys
from pathlib import Path


def load_summary(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_single_report(data: dict):
    """Print a detailed report for a single test run."""
    results = data.get("results", [])
    mode = data.get("mode", "unknown")
    run_id = data.get("run_id", "unknown")

    print(f"# PilotCode E2E Test Report\n")
    print(f"- **Run ID**: `{run_id}`")
    print(f"- **Mode**: `{mode}`")
    print(f"- **Total Tasks**: {len(results)}")
    print(f"- **Compile OK**: {data.get('compile_ok', 0)}/{len(results)}")
    print(f"- **Run OK**: {data.get('run_ok', 0)}/{len(results)}")
    print(f"- **Output Check OK**: {data.get('output_check_ok', 0)}/{len(results)}")
    print(f"- **Total Files**: {data.get('total_files', 0)}")
    print(f"- **Total Lines**: {data.get('total_lines', 0)}")
    print()

    print("| Task | Compile | Run | Output | Elapsed | Lines | Files |")
    print("|------|---------|-----|--------|---------|-------|-------|")
    for r in results:
        c = "✅" if r.get("compile_ok") else "❌"
        ru = "✅" if r.get("run_ok") else "❌"
        o = "✅" if r.get("output_check") else "❌"
        tid = r.get("task_id", "?")
        elapsed = r.get("elapsed", 0)
        lines = r.get("total_lines", 0)
        files = r.get("files_generated", 0)
        print(f"| {tid} | {c} | {ru} | {o} | {elapsed:.1f}s | {lines} | {files} |")
    print()

    # Per-category stats
    categories: dict[str, dict] = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "compile_ok": 0, "run_ok": 0, "total_lines": 0, "total_time": 0}
        categories[cat]["count"] += 1
        categories[cat]["compile_ok"] += 1 if r.get("compile_ok") else 0
        categories[cat]["run_ok"] += 1 if r.get("run_ok") else 0
        categories[cat]["total_lines"] += r.get("total_lines", 0)
        categories[cat]["total_time"] += r.get("elapsed", 0)

    print("## Per-Category Statistics\n")
    print("| Category | Tasks | Compile | Run | Avg Time | Avg Lines |")
    print("|----------|-------|---------|-----|----------|-----------|")
    for cat, stats in sorted(categories.items()):
        avg_time = stats["total_time"] / stats["count"] if stats["count"] else 0
        avg_lines = stats["total_lines"] // stats["count"] if stats["count"] else 0
        print(f"| {cat} | {stats['count']} | {stats['compile_ok']}/{stats['count']} | {stats['run_ok']}/{stats['count']} | {avg_time:.1f}s | {avg_lines} |")
    print()

    # Failed tasks detail
    failed = [r for r in results if not r.get("compile_ok") or not r.get("run_ok")]
    if failed:
        print("## Failed Tasks Detail\n")
        for r in failed:
            print(f"### {r['task_id']}")
            if not r.get("compile_ok"):
                print(f"**Compile Error:**")
                print(f"```\n{r.get('compile_output', 'N/A')[:500]}\n```")
            if not r.get("run_ok"):
                print(f"**Run Output:**")
                print(f"```\n{r.get('run_output', 'N/A')[:500]}\n```")
            print()
    else:
        print("**All tasks passed!** 🎉\n")


def print_comparison(data_cli: dict, data_ws: dict):
    """Print a side-by-side comparison of CLI vs WebSocket results."""
    cli_results = {r["task_id"]: r for r in data_cli.get("results", [])}
    ws_results = {r["task_id"]: r for r in data_ws.get("results", [])}
    all_tasks = sorted(set(cli_results) | set(ws_results))

    print(f"# PilotCode E2E: CLI vs WebSocket Comparison\n")
    print(f"| Task | CLI Compile | CLI Run | CLI Time | CLI Lines | WS Compile | WS Run | WS Time | WS Lines |")
    print(f"|------|-------------|---------|----------|-----------|------------|--------|---------|----------|")

    cli_total_time = 0
    ws_total_time = 0
    cli_total_lines = 0
    ws_total_lines = 0
    cli_ok = 0
    ws_ok = 0

    for tid in all_tasks:
        cr = cli_results.get(tid, {})
        wr = ws_results.get(tid, {})
        cc = "✅" if cr.get("compile_ok") else "❌" if cr else "N/A"
        rc = "✅" if cr.get("run_ok") else "❌" if cr else "N/A"
        wc = "✅" if wr.get("compile_ok") else "❌" if wr else "N/A"
        wru = "✅" if wr.get("run_ok") else "❌" if wr else "N/A"
        ct = cr.get("elapsed", 0)
        cl = cr.get("total_lines", 0)
        wt = wr.get("elapsed", 0)
        wl = wr.get("total_lines", 0)
        print(f"| {tid} | {cc} | {rc} | {ct:.1f}s | {cl} | {wc} | {wru} | {wt:.1f}s | {wl} |")

        cli_total_time += ct
        ws_total_time += wt
        cli_total_lines += cl
        ws_total_lines += wl
        if cr.get("compile_ok") and cr.get("run_ok"):
            cli_ok += 1
        if wr.get("compile_ok") and wr.get("run_ok"):
            ws_ok += 1

    print(f"| **Total** | | | **{cli_total_time:.1f}s** | **{cli_total_lines}** | | | **{ws_total_time:.1f}s** | **{ws_total_lines}** |")
    print()
    print(f"- CLI: {cli_ok}/{len(all_tasks)} tasks fully passed")
    print(f"- WebSocket: {ws_ok}/{len(all_tasks)} tasks fully passed")
    print(f"- Time ratio (WS/CLI): {ws_total_time/cli_total_time:.2f}x" if cli_total_time else "")
    print(f"- Lines ratio (WS/CLI): {ws_total_lines/cli_total_lines:.2f}x" if cli_total_lines else "")
    print()


def main():
    args = sys.argv[1:]
    if len(args) == 1:
        data = load_summary(Path(args[0]))
        print_single_report(data)
    elif len(args) == 2:
        data_cli = load_summary(Path(args[0]))
        data_ws = load_summary(Path(args[1]))
        print_comparison(data_cli, data_ws)
    else:
        print("Usage:")
        print(f"  {sys.argv[0]} <summary.json>")
        print(f"  {sys.argv[0]} <cli_summary.json> <ws_summary.json>")
        sys.exit(1)


if __name__ == "__main__":
    main()
