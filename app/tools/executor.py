from typing import Any

from app.tools.registry import ToolRegistry


class ToolExecutor:
    """Executes tools registered in ToolRegistry."""

    def __init__(self, registry: ToolRegistry):
        if not isinstance(registry, ToolRegistry):
            raise TypeError("registry must be a ToolRegistry")

        self.registry = registry

    def execute(self, tool_name: str, **kwargs) -> Any:
        """Execute a registered tool by name."""
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be a string")

        tool_name = tool_name.strip()

        if not tool_name:
            raise ValueError("tool_name cannot be empty")

        tool = self.registry.get(tool_name)

        return tool.execute(**kwargs)
