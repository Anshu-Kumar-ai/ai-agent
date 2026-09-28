from abc import ABC, abstractmethod

from ...core.state.agent_state import ConversationState, TaskGoalState
from ...core.state.attempt import Attempt
from ...core.state.reflection import NextAction, Reflection


class ReflectionEngine(ABC):
    """Interface for reflecting on an attempt and suggesting next steps."""
    @abstractmethod
    def reflect(
        self,
        attempt: Attempt,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> tuple[Reflection, NextAction | None]:
        """Return a Reflection record and an optional NextAction suggestion."""
