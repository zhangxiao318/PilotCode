"""Tests for MCP config manager."""

import json
import tempfile
from pathlib import Path

import pytest

from pilotcode.services.mcp_config_manager import (
    MCPConfigManager,
    ConfigScope,
    MCPServerEntry,
    get_mcp_config_manager,
)
from pilotcode.services.mcp_client import MCPConfig


class TestMCPConfigManager:
    """Tests for MCPConfigManager."""
    
    def test_singleton_instance(self):
        """Test that global manager is singleton."""
        manager1 = get_mcp_config_manager()
        manager2 = get_mcp_config_manager()
        assert manager1 is manager2
    
    def test_add_and_get_global_server(self):
        """Test adding and retrieving global server."""
        manager = MCPConfigManager()
        
        config = MCPConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env={"KEY": "value"},
            enabled=True
        )
        
        # Create temp config dir
        with tempfile.TemporaryDirectory() as tmpdir:
            manager._config_dir = Path(tmpdir)
            manager._global_config_file = Path(tmpdir) / "settings.json"
            
            manager.add_global_server("test-server", config)
            
            servers = manager.get_global_servers()
            assert "test-server" in servers
            assert servers["test-server"].command == "npx"
    
    def test_remove_global_server(self):
        """Test removing global server."""
        manager = MCPConfigManager()
        
        config = MCPConfig(command="test", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager._config_dir = Path(tmpdir)
            manager._global_config_file = Path(tmpdir) / "settings.json"
            
            manager.add_global_server("to-remove", config)
            assert manager.remove_global_server("to-remove") is True
            assert manager.remove_global_server("to-remove") is False
            
            servers = manager.get_global_servers()
            assert "to-remove" not in servers
    
    def test_get_all_servers_priority(self):
        """Test that lower scopes override higher scopes."""
        manager = MCPConfigManager()
        
        global_config = MCPConfig(command="global-cmd", args=[])
        project_config = MCPConfig(command="project-cmd", args=[])
        mcprc_config = MCPConfig(command="mcprc-cmd", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Setup global
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            manager.add_global_server("shared-server", global_config)
            
            # Setup project
            project_dir = tmpdir_path / "project"
            project_dir.mkdir()
            (project_dir / ".pilotcode.json").write_text(json.dumps({
                "mcp_servers": {
                    "shared-server": {
                        "command": "project-cmd",
                        "args": [],
                        "enabled": True
                    }
                }
            }))
            
            # Setup mcprc
            (project_dir / ".mcprc").write_text(json.dumps({
                "shared-server": {
                    "command": "mcprc-cmd",
                    "args": [],
                    "enabled": True
                }
            }))
            
            # Get all servers from project dir
            all_servers = manager.get_all_servers(cwd=project_dir)
            
            # mcprc should override project, which overrides global
            assert "shared-server" in all_servers
            assert all_servers["shared-server"].config.command == "mcprc-cmd"
            assert all_servers["shared-server"].scope == ConfigScope.MCPRC
    
    def test_mcprc_file_operations(self):
        """Test .mcprc file read/write operations."""
        manager = MCPConfigManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            config = MCPConfig(
                command="mcprc-cmd",
                args=["arg1"],
                enabled=True
            )
            
            manager.add_mcprc_server("mcprc-server", config, tmpdir_path)
            
            mcprc_file = tmpdir_path / ".mcprc"
            assert mcprc_file.exists()
            
            content = json.loads(mcprc_file.read_text())
            assert content["mcprc-server"]["command"] == "mcprc-cmd"
            
            # Read back
            servers = manager.get_mcprc_servers(tmpdir_path)
            assert "mcprc-server" in servers
            assert servers["mcprc-server"].command == "mcprc-cmd"
    
    def test_list_servers(self):
        """Test listing all servers."""
        manager = MCPConfigManager()
        
        config = MCPConfig(command="test", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            
            manager.add_global_server("server1", config)
            manager.add_global_server("server2", config)
            
            servers = manager.list_servers()
            names = [s.name for s in servers]
            
            assert "server1" in names
            assert "server2" in names
    
    def test_get_server_specific(self):
        """Test getting specific server."""
        manager = MCPConfigManager()
        
        config = MCPConfig(command="specific", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            
            manager.add_global_server("specific-server", config)
            
            server = manager.get_server("specific-server")
            assert server is not None
            assert server.name == "specific-server"
            
            missing = manager.get_server("non-existent")
            assert missing is None
    
    def test_disabled_servers_not_included(self):
        """Test that disabled servers are not returned."""
        manager = MCPConfigManager()
        
        enabled_config = MCPConfig(command="enabled", args=[], enabled=True)
        disabled_config = MCPConfig(command="disabled", args=[], enabled=False)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            
            manager.add_global_server("enabled-server", enabled_config)
            manager.add_global_server("disabled-server", disabled_config)
            
            servers = manager.get_global_servers()
            assert "enabled-server" in servers
            assert "disabled-server" not in servers
    
    def test_find_project_root_git(self):
        """Test finding project root by .git directory."""
        manager = MCPConfigManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create git repo
            git_dir = tmpdir_path / ".git"
            git_dir.mkdir()
            
            # Create subdirectory
            subdir = tmpdir_path / "src" / "components"
            subdir.mkdir(parents=True)
            
            root = manager._find_project_root(subdir)
            assert root == tmpdir_path
    
    def test_find_project_root_config(self):
        """Test finding project root by config file."""
        manager = MCPConfigManager()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create config file
            (tmpdir_path / ".pilotcode.json").write_text("{}")
            
            # Create subdirectory
            subdir = tmpdir_path / "nested"
            subdir.mkdir()
            
            root = manager._find_project_root(subdir)
            assert root == tmpdir_path
    
    def test_add_server_with_scope(self):
        """Test add_server with different scopes."""
        manager = MCPConfigManager()
        config = MCPConfig(command="test", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            
            # Add to global scope
            manager.add_server("global-srv", config, ConfigScope.GLOBAL)
            assert "global-srv" in manager.get_global_servers()
    
    def test_remove_server_all_scopes(self):
        """Test remove_server without scope tries all."""
        manager = MCPConfigManager()
        config = MCPConfig(command="test", args=[])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            manager._config_dir = tmpdir_path
            manager._global_config_file = tmpdir_path / "settings.json"
            
            # Add to global
            manager.add_global_server("removable", config)
            
            # Remove without scope
            assert manager.remove_server("removable") is True
            assert "removable" not in manager.get_global_servers()
    
    def test_mcpserver_entry_dataclass(self):
        """Test MCPServerEntry dataclass."""
        config = MCPConfig(command="test", args=[])
        entry = MCPServerEntry(
            name="test-entry",
            config=config,
            scope=ConfigScope.GLOBAL,
            source_path=None
        )
        
        assert entry.name == "test-entry"
        assert entry.scope == ConfigScope.GLOBAL


class TestConfigScope:
    """Tests for ConfigScope enum."""
    
    def test_scope_values(self):
        """Test scope enum values."""
        assert ConfigScope.GLOBAL.value == "global"
        assert ConfigScope.PROJECT.value == "project"
        assert ConfigScope.MCPRC.value == "mcprc"
    
    def test_scope_comparison(self):
        """Test scope comparison."""
        # MCPRC has highest priority
        assert ConfigScope.MCPRC != ConfigScope.PROJECT
        assert ConfigScope.GLOBAL != ConfigScope.MCPRC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
