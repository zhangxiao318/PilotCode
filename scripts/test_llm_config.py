"""Test LLM configuration and connectivity."""

import os
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.utils.models_config import (
    SUPPORTED_MODELS,
    get_default_model,
    check_api_key_configured,
    get_model_from_env,
)


def check_env_variables():
    """Check all supported environment variables."""
    env_vars = [
        ("DEEPSEEK_API_KEY", "deepseek"),
        ("OPENAI_API_KEY", "openai"),
        ("ANTHROPIC_API_KEY", "anthropic"),
        ("MOONSHOT_API_KEY", "moonshot"),
        ("DASHSCOPE_API_KEY", "qwen"),
        ("ZHIPU_API_KEY", "zhipu"),
        ("BAICHUAN_API_KEY", "baichuan"),
        ("ARK_API_KEY", "doubao"),
        ("AZURE_OPENAI_API_KEY", "azure"),
        ("PILOTCODE_API_KEY", "custom"),
    ]

    print("=" * 70)
    print("LLM Configuration Test")
    print("=" * 70)

    print("\n1. Environment Variables Check:")
    print("-" * 70)

    found_keys = []
    for env_var, model in env_vars:
        value = os.environ.get(env_var)
        if value:
            masked = value[:8] + "*" * (len(value) - 8) if len(value) > 8 else "***"
            print(f"  [OK] {env_var}: {masked} ({model})")
            found_keys.append((env_var, model, value))
        else:
            print(f"  [--] {env_var}: not set")

    return found_keys


def check_model_status():
    """Check configuration status for each model."""
    print("\n2. Model Configuration Status:")
    print("-" * 70)

    configured = []
    for name, info in SUPPORTED_MODELS.items():
        is_ready = check_api_key_configured(name)
        status = "[OK]" if is_ready else "[--]"
        env_key = info.env_key or "N/A"
        print(f"  {status} {info.display_name:<30} env: {env_key}")
        if is_ready:
            configured.append(name)

    return configured


def test_api_connection(model_name, api_key, base_url=None):
    """Test actual API connectivity."""
    from pilotcode.utils.model_client import ModelClient, Message

    model_info = SUPPORTED_MODELS.get(model_name)
    if not model_info:
        print(f"  Unknown model: {model_name}")
        return False

    print(f"\n  Testing {model_info.display_name}...")

    try:
        client = ModelClient(
            api_key=api_key or "no-key",
            base_url=base_url or model_info.base_url,
            model=model_info.default_model,
        )

        # Simple test message
        messages = [Message(role="user", content="Hello")]

        # Run async test
        async def test():
            try:
                # Collect all chunks
                chunks = []
                async for chunk in client.chat_completion(messages, max_tokens=5, stream=True):
                    chunks.append(chunk)
                    if len(chunks) > 0:  # Got at least one chunk
                        break
                await client.close()
                return len(chunks) > 0
            except Exception as e:
                print(f"    Error: {str(e)[:100]}")
                try:
                    await client.close()
                except:
                    pass
                return False

        result = asyncio.run(test())
        return result

    except Exception as e:
        print(f"  Failed to initialize client: {str(e)[:100]}")
        return False


def check_config_file():
    """Check configuration file."""
    print("\n3. Configuration File Check:")
    print("-" * 70)

    from pilotcode.utils.config import ConfigManager

    config_manager = ConfigManager()
    config_file = config_manager.SETTINGS_FILE

    print(f"  Config file path: {config_file}")

    if not config_file.exists():
        print("  [--] Config file does not exist")
        return None

    try:
        import json

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        print(f"  [OK] Config file loaded successfully")
        print(f"       - default_model: {config.get('default_model', 'not set')}")
        print(f"       - base_url: {config.get('base_url', 'not set')}")
        print(f"       - model_provider: {config.get('model_provider', 'not set')}")

        api_key = config.get("api_key", "")
        if api_key:
            masked = api_key[:8] + "*" * (len(api_key) - 8) if len(api_key) > 8 else "***"
            print(f"       - api_key: {masked}")
        else:
            print(f"       - api_key: (empty)")

        return config
    except Exception as e:
        print(f"  [ERROR] Failed to load config: {e}")
        return None


def main():
    """Main test function."""
    # Check environment variables
    found_keys = check_env_variables()

    # Check model status
    configured_models = check_model_status()

    # Check config file
    config = check_config_file()

    # Summary
    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)

    has_config = found_keys or (config and config.get("default_model"))

    if not has_config:
        print("\n  [WARNING] No LLM configuration found!")
        print("\n  To use PilotCode, please either:")
        print("\n  1. Set environment variable:")
        print("     $env:DEEPSEEK_API_KEY = 'your-api-key'")
        print("\n  2. Or configure via settings file:")
        print(f"     {config_manager.SETTINGS_FILE}")
        print("\n  3. Or run configuration wizard:")
        print("     pilotcode configure")
        return 1

    if found_keys:
        print(f"\n  [OK] Found {len(found_keys)} API key(s) in environment")

    if config and config.get("default_model"):
        print(f"  [OK] Config file configured with model: {config.get('default_model')}")
        print(f"       Base URL: {config.get('base_url', 'default')}")

    print(f"  [OK] {len(configured_models)} model(s) ready to use")

    # Test API connectivity
    if config and config.get("base_url"):
        print(f"\n4. Testing API Connection:")
        print("-" * 70)

        model_name = config.get("default_model", "custom")
        api_key = config.get("api_key", "")
        base_url = config.get("base_url")

        if test_api_connection(model_name, api_key, base_url):
            print(f"  [OK] API connection successful!")
        else:
            print(f"  [ERROR] API connection failed!")
            print(f"         Please check base_url: {base_url}")
    elif len(found_keys) == 1:
        env_var, model_name, api_key = found_keys[0]
        print(f"\n4. Testing API Connection:")
        print("-" * 70)
        if test_api_connection(model_name, api_key):
            print(f"  [OK] API connection successful!")
        else:
            print(f"  [ERROR] API connection failed!")
            print(f"         Please check {env_var} is valid.")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
