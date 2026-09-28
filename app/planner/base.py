from abc import ABC, abstractmethod

from ...core.state.action import Action
from ...core.state.agent_state import ConversationState, TaskGoalState
from ...core.state.goal_state import Goal


class Planner(ABC):
    """Interface for generating candidate actions given a goal and state."""
    @abstractmethod
    def plan(
        self,
        goal: Goal,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> list[Action]:
        """Return an ordered list of actions to try."""
