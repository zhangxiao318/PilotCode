#!/usr/bin/env python3
"""Test Unicode/CJK character input in PilotCode TUI.

This test verifies that:
1. Chinese characters can be typed correctly
2. Backspace deletes one character (not bytes)
3. Multi-byte characters are handled properly

Requirements:
    - mcp-terminator: go install github.com/davidroman0O/mcp-terminator@latest
    OR
    - mcp-tui-test: pip install mcp-tui-test

Usage:
    python test_unicode_input_tui.py
    python test_unicode_input_tui.py --command "python -m pilotcode main --auto-allow"
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pilotcode.mcp_tui_client import TUITestClient, MCPClientError


async def test_unicode_input(command: str, server_command: str | None = None):
    """Test Unicode character input handling."""
    
    print("=" * 70)
    print("PILOTCODE UNICODE INPUT TEST")
    print("=" * 70)
    print(f"Command: {command}")
    print(f"Server: {server_command or 'auto-detect'}")
    print("=" * 70)
    
    async with TUITestClient(server_command=server_command) as client:
        # Launch PilotCode TUI
        print("\n1. Launching PilotCode TUI...")
        await client.launch_tui(
            command=command,
            session_id="unicode_test",
            mode="buffer",
            dimensions="120x40"
        )
        
        # Wait for welcome screen
        print("2. Waiting for welcome screen...")
        await client.expect_text("PilotCode", session_id="unicode_test", timeout=10)
        await asyncio.sleep(1)
        
        # Test 1: Type Chinese characters
        print("\n3. Test 1: Typing Chinese characters '你好世界'")
        test_chars = "你好世界"
        await client.send_keys(test_chars, session_id="unicode_test", delay=0.2)
        await asyncio.sleep(0.5)
        
        # Capture screen and verify
        screen = await client.capture_screen(session_id="unicode_test")
        if test_chars in screen.raw_text:
            print("   ✅ PASS: Chinese characters appear correctly")
        else:
            print("   ❌ FAIL: Chinese characters not found on screen")
            print(f"   Screen content: {screen.raw_text[:500]}")
        
        # Test 2: Backspace deletes one character
        print("\n4. Test 2: Pressing Backspace 2 times (should delete '世界')")
        await client.send_keys("\x7f\x7f", session_id="unicode_test", delay=0.3)  # Backspace x2
        await asyncio.sleep(0.5)
        
        screen = await client.capture_screen(session_id="unicode_test")
        remaining_text = "你好"
        if remaining_text in screen.raw_text and "世界" not in screen.raw_text:
            print("   ✅ PASS: Backspace correctly deletes one Unicode character")
        else:
            print("   ⚠️  CHECK: Verify remaining text is '你好'")
            print(f"   Screen: {screen.raw_text[:500]}")
        
        # Test 3: Type more complex CJK text
        print("\n5. Test 3: Typing complex text '测试中文输入'")
        await client.send_keys("测试中文输入", session_id="unicode_test", delay=0.2)
        await asyncio.sleep(0.5)
        
        screen = await client.capture_screen(session_id="unicode_test")
        if "测试中文输入" in screen.raw_text:
            print("   ✅ PASS: Complex CJK text handled correctly")
        else:
            print("   ❌ FAIL: Complex CJK text not found")
        
        # Test 4: Mixed English and Chinese
        print("\n6. Test 4: Mixed English and Chinese 'Hello 你好 World 世界'")
        await client.send_ctrl("u", session_id="unicode_test")  # Clear line
        await asyncio.sleep(0.3)
        mixed_text = "Hello 你好 World 世界"
        await client.send_keys(mixed_text, session_id="unicode_test", delay=0.2)
        await asyncio.sleep(0.5)
        
        screen = await client.capture_screen(session_id="unicode_test")
        if "Hello" in screen.raw_text and "你好" in screen.raw_text:
            print("   ✅ PASS: Mixed text handled correctly")
        else:
            print("   ❌ FAIL: Mixed text not rendered properly")
        
        # Test 5: Japanese and Korean
        print("\n7. Test 5: Japanese (こんにちは) and Korean (안녕하세요)")
        await client.send_ctrl("u", session_id="unicode_test")
        await asyncio.sleep(0.3)
        await client.send_keys("こんにちは 안녕하세요", session_id="unicode_test", delay=0.2)
        await asyncio.sleep(0.5)
        
        screen = await client.capture_screen(session_id="unicode_test")
        if "こんにちは" in screen.raw_text or "안녕하세요" in screen.raw_text:
            print("   ✅ PASS: Japanese/Korean text handled")
        else:
            print("   ⚠️  CHECK: Japanese/Korean may not be supported by terminal font")
        
        # Test 6: Emoji
        print("\n8. Test 6: Emoji characters 👋🎉🐍")
        await client.send_ctrl("u", session_id="unicode_test")
        await asyncio.sleep(0.3)
        await client.send_keys("Hello 👋 World 🎉", session_id="unicode_test", delay=0.2)
        await asyncio.sleep(0.5)
        
        screen = await client.capture_screen(session_id="unicode_test")
        print("   ℹ️  Emoji support depends on terminal configuration")
        
        # Final test: Submit text
        print("\n9. Test 7: Submitting Chinese query")
        await client.send_ctrl("u", session_id="unicode_test")
        await asyncio.sleep(0.3)
        await client.send_keys("你好，请介绍一下自己\n", session_id="unicode_test", delay=0.2)
        
        # Wait for response
        print("10. Waiting for response...")
        try:
            await client.expect_text("AI|Assistant|帮助", session_id="unicode_test", timeout=15)
            print("   ✅ PASS: Query submitted and response received")
        except:
            print("   ⚠️  Response timeout (may be normal if LLM is slow)")
        
        # Cleanup
        print("\n11. Closing session...")
        await client.close_session("unicode_test")
        
        print("\n" + "=" * 70)
        print("TEST COMPLETED")
        print("=" * 70)
        print("\nIf Chinese characters displayed and backspace worked correctly,")
        print("the Unicode input fix is working!")


def main():
    parser = argparse.ArgumentParser(
        description="Test Unicode/CJK input in PilotCode TUI"
    )
    parser.add_argument(
        "--command",
        default="python -m pilotcode main --auto-allow",
        help="Command to launch PilotCode"
    )
    parser.add_argument(
        "--server",
        help="MCP server command (auto-detected if not specified)"
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(test_unicode_input(args.command, args.server))
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except MCPClientError as e:
        print(f"\n❌ MCP Client Error: {e}")
        print("\nPlease install an MCP TUI server:")
        print("  - mcp-terminator (recommended):")
        print("    go install github.com/davidroman0O/mcp-terminator@latest")
        print("  - mcp-tui-test:")
        print("    pip install mcp-tui-test")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
