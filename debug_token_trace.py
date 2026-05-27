#!/usr/bin/env python3
"""
Token 计算调试跟踪脚本
用于跟踪 token 计算的完整流程
"""

import sys
import os
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))


def setup_debug_logging():
    """设置调试日志"""
    print("=== Token 计算跟踪调试 ===")
    print("为了完整跟踪 token 计算过程，建议在以下关键位置添加调试输出：")
    print()

    debug_points = [
        "1. TokenManager.count_tokens() 方法 - 核心计算逻辑",
        "2. query_engine.py submit_message() 方法 - 消息添加点",
        "3. session_cmd.py load 操作 - 会话加载点",
        "4. status bar 更新逻辑 - UI 显示点",
        "5. TokenManager.reset_cache() 方法 - 缓存重置点",
    ]

    for point in debug_points:
        print(f"  {point}")

    print()
    print("建议的调试输出格式：")
    print("  [TOKEN_DEBUG] 时间戳 - 操作: [消息数] [缓存状态] [计算结果]")
    print(
        "  [TOKEN_DEBUG] 12:34:56.789 - count_tokens() called: 3 messages, using cache: True, result: 1234"
    )
    print("  [TOKEN_DEBUG] 12:34:57.123 - message added: 4 messages, cache reset, recalc: 1256")
    print()


def analyze_current_implementation():
    """分析当前实现中的问题"""
    print("=== 当前实现分析 ===")

    # 检查关键方法中的缓存处理
    methods_to_check = [
        "TokenManager.count_tokens()",
        "query_engine.clear_history()",
        "query_engine.load_session()",
        "query_engine.load_from_storage()",
        "session_cmd.load()",
    ]

    print("已实现的缓存重置点：")
    for method in methods_to_check:
        print(f"  ✓ {method}")

    print()
    print("待修复的缓存重置点（输入消息时）：")
    print("  ✗ query_engine.submit_message() - 添加消息后未重置缓存")
    print()

    print("=== 问题诊断 ===")
    print("1. 用户输入消息后，消息被添加到 self.messages")
    print("2. 但 TokenManager 缓存未被重置")
    print("3. 下次 count_tokens() 调用时使用旧缓存")
    print("4. 状态栏显示的 token 数量始终不变")
    print()
    print("=== 解决方案 ===")
    print("在 query_engine.submit_message() 中每次添加消息后添加：")
    print("  self._token_mgr.reset_cache()")
    print()
    print("建议在以下位置添加调试输出：")
    print("- 每次消息添加后")
    print("- 每次缓存重置后")
    print("- 每次 token 重新计算后")


if __name__ == "__main__":
    setup_debug_logging()
    analyze_current_implementation()
