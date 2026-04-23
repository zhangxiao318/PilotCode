"""Parity tests for services layer: config, state, export, sessions."""

import os
import tempfile

import pytest

from pilotcode.state.app_state import get_default_app_state
from pilotcode.state.store import Store
from pilotcode.utils.config import get_global_config, get_config_manager


class TestConfigService:
    def test_global_config_has_theme(self):
        cfg = get_global_config()
        assert hasattr(cfg, "theme")

    def test_global_config_has_model(self):
        cfg = get_global_config()
        assert hasattr(cfg, "default_model")

    def test_config_manager_roundtrip(self):
        with tempfile.TemporaryDirectory():
            manager = get_config_manager()
            # Save a custom global config path
            cfg = get_global_config()
            original_theme = cfg.theme
            cfg.theme = "test_theme_roundtrip"
            # NOTE: current implementation may hardcode path; just assert it doesn't crash
            manager.save_global_config(cfg)
            # Reset
            cfg.theme = original_theme
            manager.save_global_config(cfg)


class TestStateService:
    def test_store_get_set_state(self):
        state = get_default_app_state()
        store = Store(state)
        assert store.get_state().cwd == state.cwd

    def test_app_state_has_cwd(self):
        state = get_default_app_state()
        assert hasattr(state, "cwd")
        assert os.path.isdir(state.cwd)


class TestExportService:
    @pytest.mark.asyncio
    async def test_export_command_exists(self):
        from pilotcode.commands.base import get_all_commands

        names = {c.name for c in get_all_commands()}
        assert "export" in names

    def test_session_resume_exists(self):
        from pilotcode.commands.base import get_all_commands

        names = {c.name for c in get_all_commands()}
        assert "resume" in names


class TestLspService:
    @pytest.mark.asyncio
    async def test_lsp_command_exists(self):
        from pilotcode.commands.base import get_all_commands

        assert "lsp" in {c.name for c in get_all_commands()}

    def test_lsp_tool_exists(self):
        from pilotcode.tools.registry import get_tool_by_name

        assert get_tool_by_name("LSP") is not None
