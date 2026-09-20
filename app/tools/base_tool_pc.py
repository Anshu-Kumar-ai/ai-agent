from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from app.core.state.action import Action, SandboxSpec
from app.core.state.observation import Observation


class Tool(ABC):
    """Interface for all tools."""
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the tool, e.g., 'fs.read'."""
        pass

    @abstractmethod
    def prepare(self, action: Action) -> Any:
        """Prepare sandbox/resources; returns a context object."""
        pass

    @abstractmethod
    def execute(self, action: Action, context: Any) -> Observation:
        """Execute the tool with given action and prepared context."""
        pass

    @abstractmethod
    def cleanup(self, action: Action, context: Any) -> None:
        """Release any resources held by context."""
        pass

    def validate_arguments(self, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate the arguments for this tool.

        Returns:
            Tuple[bool, str]: (is_valid, error_message). If is_valid is True, error_message should be empty.
            If is_valid is False, error_message should describe the validation error.
            By default, returns (True, "") meaning no validation is performed.
        """
        return True, ""