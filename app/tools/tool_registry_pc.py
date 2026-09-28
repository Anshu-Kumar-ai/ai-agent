
from .base_tool import Tool


class ToolRegistry:
    """Simple registry mapping tool names to Tool instances."""
    _mapping: dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        cls._mapping[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Tool:
        tool = cls._mapping.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' not registered")
        return tool

    @classmethod
    def list_names(cls) -> list:
        return list(cls._mapping.keys())