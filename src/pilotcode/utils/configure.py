"""Interactive configuration wizard for PilotCode.

This module provides an interactive CLI to configure PilotCode,
including model selection and API key setup.
"""

import sys
import os

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
    format_model_list,
    ModelInfo,
    SUPPORTED_MODELS,
)
from .config import GlobalConfig, save_global_config, get_config_manager

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

        # Step 1: Select model category
        if not self._select_model_category():
            return False

        # Step 2: Enter API key
        if not self._enter_api_key():
            return False

        # Step 3: Optional settings
        self._optional_settings()

        # Step 4: Confirm and save
        if self._confirm_and_save():
            console.print("\n[bold green]✅ Configuration saved successfully![/bold green]")
            console.print(f"[dim]Config file: {get_config_manager().SETTINGS_FILE}[/dim]")
            return True
        else:
            console.print("\n[yellow]Configuration cancelled.[/yellow]")
            return False

    def _select_model_category(self) -> bool:
        """Select model category (International/Domestic/Local)."""
        console.print("\n[bold]Step 1: Select Model Category[/bold]")

        table = Table(box=box.ROUNDED)
        table.add_column("Option", style="cyan", justify="center")
        table.add_column("Category", style="green")
        table.add_column("Description", style="dim")

        table.add_row("1", "International", "OpenAI, Anthropic Claude, Azure, etc.")
        table.add_row("2", "Domestic (国内)", "DeepSeek, Qwen, GLM, Moonshot, etc.")
        table.add_row("3", "Local/Custom", "Ollama, vLLM, or custom OpenAI-compatible endpoint")

        console.print(table)

        choice = Prompt.ask("Select category", choices=["1", "2", "3", "q"], default="1")

        if choice == "q":
            return False

        categories = {
            "1": ("International", get_international_models()),
            "2": ("Domestic", get_domestic_models()),
            "3": (
                "Local/Custom",
                {
                    "ollama": get_model_info("ollama"),
                    "vllm": get_model_info("vllm"),
                    "custom": get_model_info("custom"),
                },
            ),
        }

        category_name, models = categories[choice]
        return self._select_specific_model(category_name, models)

    def _select_specific_model(self, category_name: str, models: dict[str, ModelInfo]) -> bool:
        """Select a specific model from the category."""
        console.print(f"\n[bold]Available {category_name} Models:[/bold]")

        table = Table(box=box.ROUNDED)
        table.add_column("#", style="cyan", justify="center")
        table.add_column("Model", style="green")
        table.add_column("Description", style="dim")
        table.add_column("Features", style="blue")

        model_list = list(models.items())
        for idx, (key, info) in enumerate(model_list, 1):
            if info is None:
                continue
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
        choice = Prompt.ask("Select model", choices=choices)

        if choice == "q":
            return False

        self.selected_model = model_list[int(choice) - 1][1]

        # Set config values from selected model
        self.config.default_model = self.selected_model.name
        self.config.base_url = self.selected_model.base_url
        self.config.model_provider = self.selected_model.provider.value

        return True

    def _enter_api_key(self) -> bool:
        """Enter API key for the selected model."""
        console.print("\n[bold]Step 2: API Key Configuration[/bold]")

        if not self.selected_model:
            console.print("[red]No model selected![/red]")
            return False

        # For Ollama and vLLM, no API key needed
        if self.selected_model.name in ("ollama", "vllm"):
            console.print(
                f"[green]✓[/green] {self.selected_model.display_name} runs locally, no API key needed."
            )
            self.config.api_key = ""
            return True

        # Show instructions for getting API key
        env_key = self.selected_model.get_env_key()
        console.print(f"\n[cyan]Model:[/cyan] {self.selected_model.display_name}")
        console.print(f"[cyan]Required env var:[/cyan] {env_key}")

        # Check if already set in environment
        existing_key = os.environ.get(env_key) or os.environ.get("PILOTCODE_API_KEY")
        if existing_key:
            console.print(f"[green]✓ Found {env_key} in environment variables[/green]")
            use_existing = Confirm.ask("Use existing API key from environment?", default=True)
            if use_existing:
                self.config.api_key = existing_key
                return True

        # Prompt for API key
        console.print("\n[dim]How to get your API key:[/dim]")
        console.print(self._get_api_key_instructions(self.selected_model.name))

        api_key = Prompt.ask(
            f"\nEnter your API key for {self.selected_model.display_name}", password=True
        )

        if not api_key or len(api_key) < 10:
            console.print("[yellow]Warning: API key seems too short. Please verify.[/yellow]")
            if not Confirm.ask("Continue anyway?", default=False):
                return False

        self.config.api_key = api_key
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

    def _optional_settings(self) -> None:
        """Configure optional settings."""
        console.print("\n[bold]Step 3: Optional Settings[/bold] [dim](press Enter to skip)[/dim]")

        # Custom base URL (if needed)
        # Local models (Ollama, vLLM) may run on another host in the LAN
        if self.selected_model and self.selected_model.name in (
            "ollama",
            "custom",
            "vllm",
            "azure",
        ):
            custom_url = Prompt.ask("Enter base URL", default=self.config.base_url)
            if custom_url:
                self.config.base_url = custom_url

        # Theme
        theme = Prompt.ask(
            "Select theme",
            choices=["default", "dark", "light", "high-contrast"],
            default=self.config.theme,
        )
        self.config.theme = theme

        # Auto compact
        auto_compact = Confirm.ask(
            "Enable auto context compression?", default=self.config.auto_compact
        )
        self.config.auto_compact = auto_compact

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
    model_name: str, api_key: str | None = None, base_url: str | None = None
) -> bool:
    """Quickly configure with specific model.

    Args:
        model_name: Name of the model to configure
        api_key: Optional API key (will prompt if not provided)
        base_url: Optional custom base URL

    Returns:
        True if configuration was successful.
    """
    model_info = get_model_info(model_name)
    if not model_info:
        console.print(f"[red]Unknown model: {model_name}[/red]")
        console.print(f"Available models: {', '.join(SUPPORTED_MODELS.keys())}")
        return False

    config = GlobalConfig()
    config.default_model = model_name
    config.base_url = base_url or model_info.base_url
    config.model_provider = model_info.provider.value

    # Get API key
    if api_key:
        config.api_key = api_key
    elif model_name not in ("ollama", "vllm"):
        env_key = model_info.get_env_key()
        env_api_key = os.environ.get(env_key) or os.environ.get("PILOTCODE_API_KEY")
        if env_api_key:
            config.api_key = env_api_key
            console.print(f"[green]Using API key from {env_key} environment variable[/green]")
        else:
            config.api_key = Prompt.ask(
                f"Enter API key for {model_info.display_name}", password=True
            )

    save_global_config(config)
    console.print(f"[green]✅ Configured {model_info.display_name}[/green]")
    return True


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
    table.add_row("Base URL", status["base_url"] or "Default")
    table.add_row("API Key", "***set***" if status["has_api_key"] else "Not set")

    if status["env_overrides"]:
        table.add_row("Env Overrides", ", ".join(status["env_overrides"].keys()))

    console.print(table)


def get_available_model_names() -> list[str]:
    """Get list of available model names."""
    return list(get_all_models().keys())


def main() -> int:
    """Main entry point for configure command."""
    import argparse

    parser = argparse.ArgumentParser(description="Configure PilotCode")
    parser.add_argument("--wizard", "-w", action="store_true", help="Run interactive wizard")
    parser.add_argument("--model", "-m", help="Quick configure with model name")
    parser.add_argument("--api-key", "-k", help="API key for quick configure")
    parser.add_argument("--base-url", "-u", help="Custom base URL")
    parser.add_argument("--show", "-s", action="store_true", help="Show current config")
    parser.add_argument("--list-models", "-l", action="store_true", help="List all models")

    args = parser.parse_args()

    if args.list_models:
        console.print(format_model_list())
        return 0

    if args.show:
        show_current_config()
        return 0

    if args.model:
        success = quick_configure(args.model, args.api_key, args.base_url)
        return 0 if success else 1

    # Default: run wizard
    success = run_configure_wizard()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
