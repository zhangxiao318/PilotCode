"""Test configuration check."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pilotcode.utils.config import ConfigManager

config_manager = ConfigManager()

print("=" * 60)
print("Configuration Check Test")
print("=" * 60)

print(f"\nConfig file: {config_manager.SETTINGS_FILE}")
print(f"is_configured: {config_manager.is_configured()}")

# Load and display config
config = config_manager.load_global_config()
print(f"\ndefault_model: {config.default_model}")
print(f"base_url: {config.base_url}")
print(f"api_key: {'(set)' if config.api_key else '(empty)'}")

# Detailed check
print("\nDetailed checks:")
if config.api_key:
    print("  - api_key: set")
else:
    print("  - api_key: not set")

if config.default_model == "ollama":
    print("  - default_model is 'ollama': yes")
else:
    print(f"  - default_model is 'ollama': no (is '{config.default_model}')")

if ".gguf" in config.default_model:
    print("  - has .gguf extension: yes")
else:
    print("  - has .gguf extension: no")

if config.base_url:
    if "localhost" in config.base_url or "127.0.0.1" in config.base_url:
        print("  - base_url is local: yes")
    else:
        print(f"  - base_url is local: no (is '{config.base_url}')")
    
    if not config.base_url.startswith("https://api."):
        print("  - base_url is not https://api.: yes")
    else:
        print("  - base_url is not https://api.: no")

print("\n" + "=" * 60)
if config_manager.is_configured():
    print("[OK] Configuration is valid!")
else:
    print("[WARNING] Configuration is NOT valid!")
print("=" * 60)
