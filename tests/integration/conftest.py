"""
Integration Test Configuration
Shared fixtures and configuration for integration/E2E tests.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure we can import from app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.permissions import PermissionManager, ApprovalMode, RiskLevel
from app.core.providers import get_provider_manager, ProviderType
from app.llm.mock_provider import MockLLMProvider
from app.core.gateway import ModelGateway
from app.core.omniroute import OmniRoute, RoutingPolicy
from app.core.planner import LLMPlanner
from app.core.agent import Agent
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.calculator import CalculatorTool
from app.tools.time_tool import TimeTool
from app.tools.filesystem import ReadFileTool, WriteFileTool, ListFileTool, MoveFileTool
from app.tools.terminal_tools import RunCommandTool
from app.tools.web_tools import HTTPFetchTool, WebSearchTool
from app.tools.python_exec import create_python_exec_tool
from app.tools.advanced_browser_agent import create_browser_agent_tools
from app.tools.desktop_tools import create_desktop_tools
from app.tools.rag_tools import create_rag_tools
from app.tools.multi_agent import create_orchestrator, MultiAgentTool


# ============================================================
# Environment Configuration
# ============================================================

@pytest.fixture(scope="session", autouse=True)
def set_mock_llm_env():
    """Ensure mock LLM providers are used by default in integration tests."""
    os.environ["MOCK_LLM_PROVIDERS"] = "true"
    yield
    os.environ.pop("MOCK_LLM_PROVIDERS", None)


@pytest.fixture(scope="session")
def temp_workspace():
    """Create a temporary workspace directory for file operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "test_dir").mkdir()
        (workspace / "test_dir" / "subdir").mkdir()
        (workspace / "test_file.txt").write_text("initial content")
        yield workspace


# ============================================================
# Mock Provider Fixtures
# ============================================================

@pytest.fixture
def mock_llm_provider():
    """Provide a mock LLM provider with configurable responses."""
    return MockLLMProvider(responses=[
        '{"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "2 + 2"}, "reason": "Calculate 2+2"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "The answer is 4."}',
    ])


@pytest.fixture
def mock_llm_provider_calculator():
    """Mock provider that returns calculator response for arithmetic."""
    return MockLLMProvider(responses=[
        '{"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "2 + 3 * 4"}, "reason": "Calculate 2+3*4"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "The answer is 14."}',
    ])


@pytest.fixture
def mock_llm_provider_time():
    """Mock provider that returns time tool response."""
    return MockLLMProvider(responses=[
        '{"action": "use_tool", "tool_name": "time", "arguments": {}, "reason": "Get current time"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "The time is now."}',
    ])


@pytest.fixture
def mock_llm_provider_respond():
    """Mock provider that returns direct response."""
    return MockLLMProvider(responses=[
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Hello! I am doing well."}',
    ])


@pytest.fixture
def mock_llm_provider_with_failure():
    """Mock provider that fails first, then succeeds (for fallback testing)."""
    return MockLLMProvider(responses=[
        # First call fails
        Exception("Provider unavailable"),
        # Second call succeeds
        '{"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "2 + 2"}, "reason": "Calculate 2+2"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "The answer is 4."}',
    ])


@pytest.fixture
def mock_llm_provider_sequence():
    """Mock provider with a sequence of different responses."""
    responses = [
        '{"action": "use_tool", "tool_name": "fs.write", "arguments": {"path": "/tmp/test.txt", "content": "hello"}, "reason": "Write test file"}',
        '{"action": "use_tool", "tool_name": "fs.read", "arguments": {"path": "/tmp/test.txt"}, "reason": "Read test file"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "File content: hello"}',
    ]
    return MockLLMProvider(responses=responses)


# ============================================================
# Core Component Fixtures
# ============================================================

@pytest.fixture
def permission_manager(temp_workspace):
    """Create a PermissionManager with test workspace."""
    return PermissionManager(
        workspace_root=str(temp_workspace),
        approval_mode=ApprovalMode.BALANCED
    )


@pytest.fixture
def full_auto_permission_manager(temp_workspace):
    """PermissionManager in FULL_AUTO mode for testing."""
    return PermissionManager(
        workspace_root=str(temp_workspace),
        approval_mode=ApprovalMode.FULL_AUTO
    )


@pytest.fixture
def safe_permission_manager(temp_workspace):
    """PermissionManager in SAFE mode."""
    return PermissionManager(
        workspace_root=str(temp_workspace),
        approval_mode=ApprovalMode.SAFE
    )


@pytest.fixture
def mock_provider_manager():
    """Provide a mocked provider manager for testing."""
    pm = get_provider_manager()
    # Force all providers to appear available with mock keys
    for provider_type in ProviderType:
        config = pm.get_config(provider_type)
        if config and provider_type != ProviderType.LOCAL:
            config.enabled = True
            config.api_key = "mock-key"
    return pm


@pytest.fixture
def model_gateway(mock_provider_manager):
    """Create a ModelGateway with mocked provider manager."""
    return ModelGateway(mock_provider_manager)


@pytest.fixture
def omniroute(mock_provider_manager, model_gateway):
    """Create an OmniRoute instance with mocked components."""
    return OmniRoute(
        provider_manager=mock_provider_manager,
        models=model_gateway._models,
        policy=RoutingPolicy.HEALTH
    )


@pytest.fixture
def llm_planner(mock_llm_provider):
    """Create an LLMPlanner with mocked MockLLMProvider directly."""
    # MockLLMProvider has generate() method, but LLMPlanner expects router with ask(provider_type, prompt) or select_provider()+ask()
    # Create a simple adapter
    class MockRouter:
        def __init__(self, mock_provider):
            self.mock_provider = mock_provider
        
        def ask(self, provider_type, prompt: str) -> str:
            return self.mock_provider.generate(prompt)
        
        def generate(self, prompt: str) -> str:
            # For backward compatibility with tests that patch generate
            return self.mock_provider.generate(prompt)
        
        def select_provider(self, message: str):
            from app.core.providers import ProviderType
            return ProviderType.GEMINI  # Default
        
    return LLMPlanner(router=MockRouter(mock_llm_provider))


@pytest.fixture
def tool_registry():
    """Create a fully populated ToolRegistry."""
    registry = ToolRegistry()
    
    # Core tools (these inherit from BaseTool)
    registry.register(CalculatorTool())
    registry.register(TimeTool())
    # Note: Filesystem, terminal, web, python_exec tools use the PC tool architecture
    # (Tool base class with Action/Observation) which is different from BaseTool.
    # They are tested separately via their own fixtures.
    # Advanced tools (will be mocked in tests)
    # We'll skip multi-agent for most tests to keep them simple
    
    return registry


@pytest.fixture
def tool_executor(tool_registry):
    """Create a ToolExecutor with the test registry."""
    return ToolExecutor(tool_registry)


@pytest.fixture
def test_agent(mock_llm_provider):
    """Create an agent configured for testing with mocked LLM."""
    agent = Agent()
    
    # Mock LLM provider
    responses = iter([
        '{"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "5 * 6"}, "reason": "Calculate 5 * 6"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Result is 30"}',
        '{"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "10 + 20"}, "reason": "Calculate 10 + 20"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Result is 30"}',
        '{"action": "use_tool", "tool_name": "time_tool", "arguments": {}, "reason": "Get current time"}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Current time is..."}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Permission denied to delete /etc/passwd"}',
        # Extra responses to prevent fallback
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Done."}',
        '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Done."}',
    ])
    
    class MockProvider:
        def generate(self, prompt: str) -> str:
            try:
                return next(responses)
            except StopIteration:
                return '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "Done."}'
    
    mock_provider = MockProvider()
    
    # Create a mock router adapter that uses mock_llm_provider
    class MockRouter:
        def __init__(self, mock_provider):
            self.mock_provider = mock_provider
        
        def ask(self, provider_type, prompt: str) -> str:
            return self.mock_provider.generate(prompt)
        
        def generate(self, prompt: str) -> str:
            return self.mock_provider.generate(prompt)
        
        def select_provider(self, message: str):
            from app.core.providers import ProviderType
            return ProviderType.GEMINI  # Default
    
    # Also need a mock gateway for fallback
    class MockGateway:
        def __init__(self, mock_provider):
            self.mock_provider = mock_provider
        
        def ask(self, provider_type, prompt: str) -> str:
            return self.mock_provider.generate(prompt)

    # Replace planner with one using mock router
    agent.planner = LLMPlanner(router=MockRouter(mock_provider), fallback_gateway=MockGateway(mock_provider))
    
    return agent

@pytest.fixture
def calculator_tool():
    return CalculatorTool()


@pytest.fixture
def time_tool():
    return TimeTool()


@pytest.fixture
def fs_read_tool():
    tool = ReadFileTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="fs.read", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def fs_write_tool():
    tool = WriteFileTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="fs.write", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def fs_list_tool():
    tool = ListFileTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="fs.list", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def fs_move_tool():
    tool = MoveFileTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="fs.move", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def terminal_tool():
    tool = RunCommandTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="terminal.run", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def http_fetch_tool():
    tool = HTTPFetchTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="http.fetch", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def web_search_tool():
    tool = WebSearchTool()
    class ToolWrapper:
        def run(self, **kwargs):
            from app.core.state.action import Action
            action = Action.create(tool_name="web.search", arguments=kwargs)
            return tool.execute(action, None)
    return ToolWrapper()


@pytest.fixture
def python_exec_tool():
    tool = create_python_exec_tool()
    class ToolWrapper:
        def run(self, **kwargs):
            return tool.run(**kwargs)
    return ToolWrapper()


# ============================================================
# Browser Fixtures (Mocked)
# ============================================================

@pytest.fixture
def mock_browser_agent():
    """Create mocked browser agent tools."""
    from unittest.mock import AsyncMock, MagicMock
    
    tools = create_browser_agent_tools()
    for tool in tools:
        # Mock the execute method
        tool.execute = AsyncMock(return_value=MagicMock(
            success=True,
            data={"content": "Mocked page content", "url": "https://example.com"}
        ))
    return tools


@ pytest.fixture
def mock_desktop_tools():
    """Create mocked desktop automation tools."""
    from unittest.mock import AsyncMock, MagicMock

    tools = create_desktop_tools()
    for tool in tools:
        tool.execute = AsyncMock(return_value=MagicMock(
            success=True,
            data={"result": "Mocked desktop action"}
        ))
    return tools


# ============================================================
# Enhanced Memory Fixture
# ============================================================

@pytest.fixture
def enhanced_memory():
    """Create an EnhancedMemory instance for testing."""
    from app.memory.enhanced import EnhancedMemory
    return EnhancedMemory()


# ============================================================
# Utility Functions
# ============================================================

def create_test_file(workspace: Path, name: str, content: str = "test content") -> Path:
    """Create a test file in the workspace."""
    file_path = workspace / name
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    return file_path


def assert_tool_result(result, expected_success=True, expected_content=None):
    """Assert tool execution result."""
    assert result is not None
    if hasattr(result, 'success'):
        assert result.success == expected_success
    if expected_content and hasattr(result, 'data'):
        if isinstance(result.data, dict):
            for key, value in expected_content.items():
                assert key in result.data, f"Expected key '{key}' in result.data"
                if value is not None:
                    assert result.data[key] == value


# ============================================================
# Pytest Configuration
# ============================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: integration test requiring mocked external services")
    config.addinivalue_line("markers", "e2e: end-to-end test covering full agent workflow")
    config.addinivalue_line("markers", "real_provider: test requiring real LLM provider API (opt-in)")
    config.addinivalue_line("markers", "browser: test requiring browser automation")
    config.addinivalue_line("markers", "network: test requiring network access")
    config.addinivalue_line("markers", "slow: test that takes longer than 10 seconds")
    config.addinivalue_line("markers", "unit: unit test with no external dependencies")


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests based on location."""
    for item in items:
        # Mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        # Mark e2e tests
        if "e2e" in item.name.lower():
            item.add_marker(pytest.mark.e2e)
        # Mark real provider tests
        if "real_provider" in item.keywords:
            item.add_marker(pytest.mark.real_provider)