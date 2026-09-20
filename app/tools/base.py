from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Generic interface for safe, registered agent tools."""

    name: str = "unknown"
    description: str = ""
    selection_phrases: tuple[str, ...] = ()
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool with validated arguments."""
        raise NotImplementedError

    def run(self, **kwargs) -> Any:
        """Compatibility alias for older callers."""
        return self.execute(**kwargs)
