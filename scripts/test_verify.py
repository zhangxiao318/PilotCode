"""Test LLM verification."""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.utils.config import get_config_manager


async def test():
    config_manager = get_config_manager()
    
    print("=" * 60)
    print("Testing LLM verification")
    print("=" * 60)
    
    result = await config_manager.verify_configuration(timeout=15.0)
    
    print(f"\nSuccess: {result['success']}")
    print(f"Message: {result['message']}")
    if result.get('response'):
        print(f"Response: {result['response']}")
    if result.get('error'):
        print(f"Error: {result['error']}")
    
    print("\n" + "=" * 60)
    if result['success']:
        print("[OK] LLM is working!")
    else:
        print("[FAILED] LLM connection failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())
