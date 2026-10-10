from app.tools.base import BaseTool
from app.tools.capabilities import ToolCapability, get_capability, CapabilityCategory


class ToolRegistry:
    """Stores and manages tools available to the agent."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._capabilities: dict[str, ToolCapability] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        if not isinstance(tool, BaseTool):
            raise TypeError("tool must inherit from BaseTool")

        if not tool.name:
            raise ValueError("tool must have a name")

        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool
        
        # Register capability if available
        capability = get_capability(tool.name)
        if capability:
            self._capabilities[tool.name] = capability

    def get(self, name: str) -> BaseTool:
        """Return a registered tool."""
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check whether a tool exists."""
        return name in self._tools

    def get_capability(self, name: str) -> ToolCapability | None:
        """Return the capability metadata for a tool."""
        return self._capabilities.get(name)

    def get_tools_by_category(self, category: CapabilityCategory) -> list[BaseTool]:
        """Get all tools matching a capability category."""
        result = []
        for name, tool in self._tools.items():
            capability = self._capabilities.get(name)
            if capability and capability.matches_category(category):
                result.append(tool)
        return result

    def get_tools_by_operation(self, operation: str) -> list[BaseTool]:
        """Get all tools matching an operation."""
        result = []
        for name, tool in self._tools.items():
            capability = self._capabilities.get(name)
            if capability and capability.matches_operation(operation):
                result.append(tool)
        return result

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

    def list_tools_with_capabilities(self) -> list[dict]:
        """Return information about registered tools with capability metadata."""
        result = []
        for tool in self._tools.values():
            info = {
                "name": tool.name,
                "description": tool.description,
                "selection_phrases": list(tool.selection_phrases),
                "parameters": tool.parameters,
            }
            capability = self._capabilities.get(tool.name)
            if capability:
                info["capability"] = capability.to_dict()
            result.append(info)
        return result

    def count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)
