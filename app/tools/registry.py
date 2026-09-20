from app.tools.base import BaseTool


class ToolRegistry:
    """Stores and manages tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        if not isinstance(tool, BaseTool):
            raise TypeError("tool must inherit from BaseTool")

        if not tool.name:
            raise ValueError("tool must have a name")

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Return a registered tool."""
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check whether a tool exists."""
        return name in self._tools

    def list_tools(self) -> list[dict]:
        """Return information about registered tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "selection_phrases": list(tool.selection_phrases),
                "parameters": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    def count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)
