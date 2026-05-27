#!/usr/bin/env python3
"""
调试脚本：输出 token 计算的详细过程和结果
用于调试 token 使用量不更新的问题
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pilotcode.query.token_manager import TokenManager
from pilotcode.types.message import UserMessage, AssistantMessage
from pilotcode.utils.token_utils import get_context_token_usage


def debug_token_calculation():
    """调试 token 计算过程"""

    # 模拟一个简单的测试环境
    print("=== Token 计算调试信息 ===")

    # 创建一个简单的 TokenManager 实例（为了演示）
    try:
        # 由于我们无法直接创建完整实例，这里只说明调试方法

        print("调试建议：")
        print("1. 在 TokenManager.count_tokens() 方法中添加调试日志")
        print("2. 在 query_engine.py 的 submit_message 方法中添加调试日志")
        print("3. 在状态栏更新时添加调试输出")
        print("")
        print("建议修改的代码位置：")
        print("- src/pilotcode/query/token_manager.py: count_tokens() 方法")
        print("- src/pilotcode/query_engine.py: submit_message() 方法")
        print("- src/pilotcode/tui_v2/screens/session.py: token 更新逻辑")
        print("")
        print("调试输出示例：")
        print("  [DEBUG] Message list size: 3")
        print("  [DEBUG] Cache hash: abc123")
        print("  [DEBUG] Using cached result: 1234 tokens")
        print("  [DEBUG] Reset cache triggered")
        print("  [DEBUG] Recalculated tokens: 1256 tokens")

    except Exception as e:
        print(f"调试脚本执行出错: {e}")


if __name__ == "__main__":
    debug_token_calculation()
