from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any
from ...core.state.action import Action
from ...core.state.attempt import Attempt
from ...core.state.agent_state import TaskGoalState, ConversationState
from ...core.state.reflection import Reflection, NextAction

class ReflectionEngine(ABC):
    """Interface for reflecting on an attempt and suggesting next steps."""
    @abstractmethod
    def reflect(
        self,
        attempt: Attempt,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> Tuple[Reflection, Optional[NextAction]]:
        """Return a Reflection record and an optional NextAction suggestion."""
        pass