from abc import ABC, abstractmethod
from typing import Any

from app.core.state.action import Action
from app.core.state.observation import Observation


class Tool(ABC):
    """Interface for all tools."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the tool, e.g., 'fs.read'."""

    @abstractmethod
    def prepare(self, action: Action) -> Any:
        """Prepare sandbox/resources; returns a context object."""

    @abstractmethod
    def execute(self, action: Action, context: Any) -> Observation:
        """Execute the tool with given action and prepared context."""

    @abstractmethod
    def cleanup(self, action: Action, context: Any) -> None:
        """Release any resources held by context."""

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Validate the arguments for this tool.

        Returns:
            Tuple[bool, str]: (is_valid, error_message). If is_valid is True, error_message should be empty.
            If is_valid is False, error_message should describe the validation error.
            By default, returns (True, "") meaning no validation is performed.
        """
        return True, ""