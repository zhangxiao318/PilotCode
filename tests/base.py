"""Test base classes and utilities."""

import pytest
from typing import Any, Dict, Optional
from pathlib import Path

from pilotcode.tools.registry import get_tool_by_name
from pilotcode.tools.base import ToolUseContext, ToolResult


class ToolTestBase:
    """Base class for tool tests.
    
    Provides common utilities for testing tools including:
    - Standard tool execution
    - Common assertions
    - Test data setup
    
    Example:
        class TestFileReadTool(ToolTestBase):
            tool_name = "FileRead"
            
            @pytest.mark.asyncio
            async def test_read_existing_file(self, temp_dir):
                path = self.create_test_file(temp_dir, "test.txt", "hello")
                result = await self.run_tool({"file_path": path})
                self.assert_success(result)
                assert result.data.content == "hello"
    """
    
    tool_name: str = None
    
    @pytest.fixture
    def tool(self):
        """Get the tool instance."""
        if not self.tool_name:
            raise ValueError("tool_name must be set")
        return get_tool_by_name(self.tool_name)
    
    async def run_tool(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[ToolUseContext] = None
    ) -> ToolResult:
        """Execute tool with given input.
        
        Args:
            input_data: Tool input parameters
            context: Optional tool context
            
        Returns:
            Tool execution result
        """
        tool = get_tool_by_name(self.tool_name)
        ctx = context or ToolUseContext()
        parsed = tool.input_schema(**input_data)
        
        async def allow_callback(*args, **kwargs):
            return {"behavior": "allow"}
        
        return await tool.call(
            parsed,
            ctx,
            allow_callback,
            None,  # parent_message
            lambda x: None  # on_progress
        )
    
    def assert_success(self, result: ToolResult, msg: str = None):
        """Assert tool execution succeeded.
        
        Args:
            result: Tool execution result
            msg: Optional error message
        """
        assert not result.is_error, msg or f"Tool failed: {result.error}"
    
    def assert_error(self, result: ToolResult, msg: str = None):
        """Assert tool execution failed.
        
        Args:
            result: Tool execution result
            msg: Optional error message
        """
        assert result.is_error, msg or "Expected tool to fail but it succeeded"
    
    def assert_output_contains(self, result: ToolResult, expected: str):
        """Assert output contains expected string.
        
        Args:
            result: Tool execution result
            expected: Expected substring in output
        """
        output = str(result.data)
        assert expected in output, f"Expected '{expected}' in output: {output[:200]}"
    
    def create_test_file(self, directory: Path, filename: str, content: str) -> Path:
        """Create a test file with given content.
        
        Args:
            directory: Parent directory
            filename: File name
            content: File content
            
        Returns:
            Path to created file
        """
        path = directory / filename
        path.write_text(content)
        return path
    
    def create_test_json(self, directory: Path, filename: str, data: dict) -> Path:
        """Create a test JSON file.
        
        Args:
            directory: Parent directory
            filename: File name
            data: JSON data
            
        Returns:
            Path to created file
        """
        import json
        path = directory / filename
        path.write_text(json.dumps(data, indent=2))
        return path


class IntegrationTestBase:
    """Base class for integration tests.
    
    Provides setup for tests that need multiple components.
    """
    
    @pytest.fixture(autouse=True)
    def setup_integration(self, app_store):
        """Setup integration test environment."""
        self.store = app_store
        self.ctx = ToolUseContext(
            get_app_state=app_store.get_state,
            set_app_state=lambda f: app_store.set_state(f)
        )


class MockLLMHelper:
    """Helper for mocking LLM responses."""
    
    @staticmethod
    def create_response(content: str, tool_calls=None):
        """Create a mock LLM response.
        
        Args:
            content: Response content
            tool_calls: Optional tool calls
            
        Returns:
            Mock response object
        """
        from unittest.mock import MagicMock
        
        mock = MagicMock()
        mock.choices = [MagicMock()]
        mock.choices[0].message.content = content
        mock.choices[0].message.tool_calls = tool_calls
        return mock
    
    @staticmethod
    def create_tool_call(tool_name: str, tool_input: dict):
        """Create a mock tool call.
        
        Args:
            tool_name: Tool name
            tool_input: Tool input
            
        Returns:
            Mock tool call
        """
        from unittest.mock import MagicMock
        import json
        
        mock = MagicMock()
        mock.function.name = tool_name
        mock.function.arguments = json.dumps(tool_input)
        return mock


# ============================================================================
# Test Categories
# ============================================================================

class CategoryMarkers:
    """Test category markers for organizing tests."""
    
    UNIT = pytest.mark.unit
    """Unit tests - fast, isolated"""
    
    INTEGRATION = pytest.mark.integration
    """Integration tests - multiple components"""
    
    E2E = pytest.mark.e2e
    """End-to-end tests - full workflows"""
    
    NETWORK = pytest.mark.network
    """Tests requiring network access"""
    
    SLOW = pytest.mark.slow
    """Slow tests (> 1 second)"""
    
    SECURITY = pytest.mark.security
    """Security-related tests"""
    
    PERFORMANCE = pytest.mark.performance
    """Performance tests"""


# Convenience imports
__all__ = [
    'ToolTestBase',
    'IntegrationTestBase',
    'MockLLMHelper',
    'CategoryMarkers',
]
