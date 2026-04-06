"""Test PilotCode configuration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.utils.config import get_global_config
from pilotcode.utils.models_config import get_model_info, check_api_key_configured

print("=" * 70)
print("PilotCode Configuration Check")
print("=" * 70)

config = get_global_config()
print(f"\nConfig loaded from: {config}")
print(f"default_model: {config.default_model}")
print(f"base_url: {config.base_url}")
print(f"api_key: {'(set)' if config.api_key else '(empty)'}")

model_info = get_model_info(config.default_model)
print(f"\nModel info lookup:")
if model_info:
    print(f"  Found: {model_info.display_name}")
    print(f"  base_url: {model_info.base_url}")
    print(f"  default_model: {model_info.default_model}")
    print(f"  env_key: {model_info.env_key}")
else:
    print(f"  Not found in SUPPORTED_MODELS")

is_configured = check_api_key_configured(config.default_model)
print(f"\nAPI key configured: {is_configured}")

# Test model client
print("\n" + "=" * 70)
print("Testing Model Client")
print("=" * 70)

from pilotcode.utils.model_client import ModelClient, Message
import asyncio


async def test():
    try:
        client = ModelClient()
        print(f"Client created successfully")
        print(f"  model: {client.model}")
        print(f"  base_url: {client.base_url}")

        # Test simple completion
        messages = [Message(role="user", content="几点了")]
        print("\nSending test message...")

        chunks = []
        async for chunk in client.chat_completion(messages, max_tokens=20, stream=True):
            chunks.append(chunk)
            if len(chunks) >= 5:  # Just get first few chunks
                break

        await client.close()

        if chunks:
            print(f"SUCCESS: Received {len(chunks)} chunks")
            # Try to extract content
            for chunk in chunks[:2]:
                if "choices" in chunk and chunk["choices"]:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        print(f"  Content: {content[:50]}")
        else:
            print("ERROR: No chunks received")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()


asyncio.run(test())
print("\n" + "=" * 70)
