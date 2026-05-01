"""Interactive configuration wizard for PilotCode.

This module provides an interactive CLI to configure PilotCode,
including model selection and API key setup.
"""

import sys
import os
from dataclasses import replace

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from .models_config import (
    get_all_models,
    get_model_info,
    get_international_models,
    get_domestic_models,
    ModelInfo,
)
from .config import GlobalConfig, save_global_config, get_config_manager, is_local_url

console = Console()


class ConfigurationWizard:
    """Interactive configuration wizard."""

    def __init__(self):
        self.config = GlobalConfig()
        self.selected_model: ModelInfo | None = None

    def run(self) -> bool:
        """Run the configuration wizard.

        Returns:
            True if configuration was successful, False otherwise.
        """
        console.print(
            Panel.fit(
                "[bold cyan]PilotCode Configuration Wizard[/bold cyan]\n"
                "[dim]Let's set up your AI model configuration[/dim]",
                border_style="cyan",
            )
        )

        # Step 1: Select model category and specific model
        if not self._select_model_category():
            return False

        # Step 2: Confirm or enter base URL
        if not self._confirm_url():
            return False

        # Step 3: Enter API key
        if not self._enter_api_key():
            return False

        # Step 4: Select API protocol
        if not self._select_protocol():
            return False

        # Step 5: Confirm and save
        if self._confirm_and_save():
            console.print("\n[bold green]✅ Configuration saved successfully![/bold green]")
            console.print(f"[dim]Config file: {get_config_manager().SETTINGS_FILE}[/dim]")
            console.print(
                "\n[dim]Tip: Run [cyan]pc config --list[/cyan] to probe and fine-tune "
                "runtime parameters such as context_window.[/dim]"
            )
            return True
        else:
            console.print("\n[yellow]Configuration cancelled.[/yellow]")
            return False

    def _select_model_category(self) -> bool:
        """Select model category (Domestic/International/Local)."""
        console.print("\n[bold]Step 1: Select Model Category[/bold]")

        table = Table(box=box.ROUNDED)
        table.add_column("Option", style="cyan", justify="center")
        table.add_column("Category", style="green")
        table.add_column("Description", style="dim")

        table.add_row("1", "Domestic (国内)", "DeepSeek, Qwen, GLM, Moonshot, etc.")
        table.add_row("2", "International", "OpenAI, Anthropic, Azure, Gemini, etc.")
        table.add_row("3", "Local/Custom", "Ollama, vLLM, llama.cpp, or custom endpoint")

        console.print(table)

        choice = Prompt.ask("Select category", choices=["1", "2", "3", "q"], default="1")

        if choice == "q":
            return False

        categories = {
            "1": ("Domestic", get_domestic_models()),
            "2": ("International", get_international_models()),
            "3": (
                "Local/Custom",
                {
                    "local": get_model_info("vllm"),
                    "custom": get_model_info("custom"),
                },
            ),
        }

        category_name, models = categories[choice]
        return self._select_specific_model(category_name, models)

    def _select_specific_model(self, category_name: str, models: dict[str, ModelInfo]) -> bool:
        """Select a specific model from the category."""
        console.print(f"\n[bold]Available {category_name} Providers:[/bold]")

        table = Table(box=box.ROUNDED)
        table.add_column("#", style="cyan", justify="center")
        table.add_column("Provider", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Features", style="blue")

        model_list = [(k, v) for k, v in models.items() if v is not None and not v.disabled]

        # De-duplicate by (provider, base_url) so each provider appears once
        seen = set()
        deduped = []
        for key, info in model_list:
            sig = (info.provider, info.base_url)
            if sig not in seen:
                seen.add(sig)
                deduped.append((key, info))
        model_list = deduped

        # Add "Other Provider" option for domestic category
        if category_name == "Domestic":
            other_info = get_model_info("custom")
            if other_info:
                other_info = replace(
                    other_info,
                    display_name="Other Provider (Custom URL)",
                    base_url="",
                    env_key="",
                    description="Enter your own provider URL and API key",
                )
                model_list.append(("other", other_info))

        # Merge ollama/vllm into a single "Local Server" option
        for idx, (key, info) in enumerate(model_list):
            if key == "local":
                model_list[idx] = (
                    key,
                    replace(
                        info,
                        display_name="Local Server (Ollama / vLLM / llama.cpp)",
                        env_key="",
                        description="Local OpenAI-compatible inference server",
                    ),
                )

        for idx, (key, info) in enumerate(model_list, 1):
            features = []
            if info.supports_tools:
                features.append("tools")
            if info.supports_vision:
                features.append("vision")

            table.add_row(
                str(idx),
                info.display_name,
                info.description[:50] + "..." if len(info.description) > 50 else info.description,
                ", ".join(features) if features else "-",
            )

        console.print(table)

        choices = [str(i) for i in range(1, len(model_list) + 1)] + ["q"]
        choice = Prompt.ask("Select provider", choices=choices)

        if choice == "q":
            return False

        self.selected_model = model_list[int(choice) - 1][1]

        # Set config values from selected model
        self.config.default_model = self.selected_model.name
        self.config.base_url = self.selected_model.base_url
        self.config.model_provider = self.selected_model.provider.value
        self.config.api_protocol = getattr(self.selected_model, "api_protocol", "")

        return True

    def _confirm_url(self) -> bool:
        """Confirm or override the base URL.

        For local models the user is asked to enter a URL directly.
        For cloud providers the default URL is shown and the user can
        confirm (default) or enter a custom one.
        """
        if not self.selected_model:
            return False

        default_url = self.config.base_url
        is_local = is_local_url(default_url or "")

        console.print("\n[bold]Step 2: Base URL[/bold]")

        if is_local:
            url = Prompt.ask("Enter base URL", default=default_url or "http://localhost:8000/v1")
            if url:
                self.config.base_url = url
            return True

        # Cloud provider or custom with no default URL
        if not default_url:
            url = Prompt.ask("Enter base URL")
            if url:
                self.config.base_url = url
            return True

        if Confirm.ask(f"Use default URL {default_url}?", default=True):
            return True

        url = Prompt.ask("Enter base URL")
        if url:
            self.config.base_url = url
        return True

    def _enter_api_key(self) -> bool:
        """Enter API key for the selected model."""
        if not self.selected_model:
            return False

        console.print("\n[bold]Step 3: API Key Configuration[/bold]")

        # For local models, no API key needed
        if self.selected_model.name in ("ollama", "vllm"):
            console.print(
                f"[green]✓[/green] {self.selected_model.display_name} runs locally, no API key needed."
            )
            self.config.api_key = ""
            return True

        env_key = self.selected_model.get_env_key()

        # Check if already set in environment
        existing_key = os.environ.get(env_key) or os.environ.get("PILOTCODE_API_KEY")
        if existing_key:
            if Confirm.ask(f"Use existing API key from {env_key}?", default=True):
                self.config.api_key = existing_key
                return True

        # Prompt for API key
        while True:
            api_key = Prompt.ask(
                f"Enter your API key for {self.selected_model.display_name}",
                password=True,
            )
            if api_key:
                self.config.api_key = api_key
                return True

            # No key entered — ask for confirmation (default yes to allow skipping)
            if Confirm.ask("No API key entered. Continue without API key?", default=True):
                self.config.api_key = ""
                return True
            # User chose to retry

    def _ask_protocol(self, default: str = "openai") -> str:
        """Ask user to select API protocol via numbered choice."""
        default_num = "1" if default == "openai" else "2"
        choice = Prompt.ask(
            "Select API protocol: 1.OpenAI 2.Anthropic",
            choices=["1", "2"],
            default=default_num,
        )
        return "openai" if choice == "1" else "anthropic"

    def _select_protocol(self) -> bool:
        """Confirm or override the API protocol."""
        if not self.selected_model:
            return False

        default_proto = self.config.api_protocol or "openai"
        console.print("\n[bold]Step 4: API Protocol[/bold]")
        console.print(
            f"[dim]Detected protocol for {self.selected_model.display_name}: {default_proto}[/dim]"
        )

        protocol = self._ask_protocol(default=default_proto)
        self.config.api_protocol = protocol
        return True

    def _get_api_key_instructions(self, model_name: str) -> str:
        """Get instructions for obtaining API key."""
        instructions = {
            "openai": "Get from: https://platform.openai.com/api-keys",
            "openai-gpt4": "Get from: https://platform.openai.com/api-keys",
            "anthropic": "Get from: https://console.anthropic.com/settings/keys",
            "azure": "Get from Azure Portal > Cognitive Services > Keys and Endpoint",
            "deepseek": "Get from: https://platform.deepseek.com/api_keys",
            "qwen": "Get from: https://dashscope.aliyun.com/api-key-management",
            "qwen-plus": "Get from: https://dashscope.aliyun.com/api-key-management",
            "zhipu": "Get from: https://open.bigmodel.cn/usercenter/apikeys",
            "moonshot": "Get from: https://platform.moonshot.cn/console/api-keys",
            "baichuan": "Get from: https://platform.baichuan-ai.com/console/apikey",
            "doubao": "Get from: https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
            "vllm": "No API key needed for local vLLM server",
            "custom": "Enter your custom API endpoint and key",
        }
        return instructions.get(model_name, "Please check the provider's documentation.")

    def _confirm_and_save(self) -> bool:
        """Confirm configuration and save."""
        console.print("\n[bold]Configuration Summary:[/bold]")

        table = Table(box=box.ROUNDED)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row(
            "Model", self.selected_model.display_name if self.selected_model else "Unknown"
        )
        table.add_row("Base URL", self.config.base_url or "Default")
        api_key_display = (
            "***" + self.config.api_key[-4:]
            if self.config.api_key and len(self.config.api_key) > 4
            else ("Set" if self.config.api_key else "Not set")
        )
        table.add_row("API Key", api_key_display)
        table.add_row("API Protocol", self.config.api_protocol or "auto-detect")
        table.add_row("Theme", self.config.theme)
        table.add_row("Auto Compact", "Yes" if self.config.auto_compact else "No")

        console.print(table)
        if Confirm.ask("\nSave this configuration?", default=True):
            save_global_config(self.config)
            return True
        return False


def run_configure_wizard() -> bool:
    """Run the configuration wizard (convenience function).

    Returns:
        True if configuration was successful.
    """
    wizard = ConfigurationWizard()
    return wizard.run()


def quick_configure(
    model_name: str,
    api_key: str | None = None,
    base_url: str | None = None,
    api_protocol: str | None = None,
) -> bool:
    """Quickly configure with specific model.

    Args:
        model_name: Name of the model to configure
        api_key: Optional API key (will prompt if not provided)
        base_url: Optional custom base URL
        api_protocol: Optional API protocol override ("openai" or "anthropic")

    Returns:
        True if configuration was successful.
    """
    model_info = get_model_info(model_name)
    if not model_info:
        console.print(f"[red]Unknown model: {model_name}[/red]")
        return False

    config = GlobalConfig()
    config.default_model = model_info.name
    config.base_url = base_url or model_info.base_url
    config.model_provider = model_info.provider.value
    config.api_protocol = api_protocol or getattr(model_info, "api_protocol", "")

    if api_key is None and model_info.name not in ("ollama", "vllm"):
        env_key = model_info.get_env_key()
        existing_key = os.environ.get(env_key) or os.environ.get("PILOTCODE_API_KEY")
        if existing_key:
            console.print(f"[green]✓ Found {env_key} in environment variables[/green]")
            use_existing = Confirm.ask("Use existing API key?", default=True)
            if use_existing:
                api_key = existing_key
        if api_key is None:
            api_key = Prompt.ask(f"Enter your API key for {model_info.display_name}", password=True)

    config.api_key = api_key or ""

    console.print("\n[bold]Configuration Summary:[/bold]")
    table = Table(box=box.ROUNDED)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Model", model_info.display_name)
    table.add_row("Base URL", config.base_url or "Default")
    api_key_display = (
        "***" + config.api_key[-4:]
        if config.api_key and len(config.api_key) > 4
        else ("Set" if config.api_key else "Not set")
    )
    table.add_row("API Key", api_key_display)
    table.add_row("API Protocol", config.api_protocol or "auto-detect")
    console.print(table)

    if Confirm.ask("\nSave this configuration?", default=True):
        save_global_config(config)
        console.print("[green]✅ Configuration saved![/green]")
        return True
    return False


def show_current_config() -> None:
    """Display current configuration."""
    from .config import get_config_status

    status = get_config_status()

    console.print("\n[bold cyan]Current Configuration Status[/bold cyan]")

    table = Table(box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Configured", "✅ Yes" if status["configured"] else "❌ No")
    table.add_row("Config File", status["config_file_path"])
    table.add_row("Config File Exists", "Yes" if status["config_file_exists"] else "No")
    table.add_row("Model", status["model"] or "Not set")
    table.add_row("API Protocol", status.get("api_protocol") or "auto-detect")
    table.add_row("Base URL", status["base_url"] or "Default")
    table.add_row("API Key", "***set***" if status["has_api_key"] else "Not set")

    if status["env_overrides"]:
        table.add_row("Env Overrides", ", ".join(status["env_overrides"].keys()))

    console.print(table)


def get_available_model_names() -> list[str]:
    """Get list of available model names (excluding disabled)."""
    return [k for k, v in get_all_models().items() if not v.disabled]


def main() -> int:
    """Main entry point for configure command."""
    import argparse

    parser = argparse.ArgumentParser(description="Configure PilotCode")
    parser.add_argument("--wizard", "-w", action="store_true", help="Run interactive wizard")
    parser.add_argument("--model", "-m", help="Quick configure with model name")
    parser.add_argument("--api-key", "-k", help="API key for quick configure")
    parser.add_argument("--base-url", "-u", help="Custom base URL")
    parser.add_argument("--protocol", "-p", help='API protocol: "openai" or "anthropic"')
    parser.add_argument("--show", "-s", action="store_true", help="Show current config")
    parser.add_argument("--list-models", "-l", action="store_true", help="List all models")

    args = parser.parse_args()

    if args.list_models:
        from .models_config import format_model_list

        console.print(format_model_list())
        return 0

    if args.show:
        show_current_config()
        return 0

    if args.model:
        success = quick_configure(args.model, args.api_key, args.base_url, args.protocol)
        return 0 if success else 1

    # Default: run wizard
    success = run_configure_wizard()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
