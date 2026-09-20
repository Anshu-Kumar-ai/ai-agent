from abc import ABC, abstractmethod
from typing import Optional, Tuple
from ...core.state.action import Action
from ...core.state.observation import Observation
from ...core.state.goal_state import Goal
from ...core.state.evaluation import EvaluationEnum, ProgressInfo

class Evaluator(ABC):
    """Interface for evaluating an action attempt."""

    @abstractmethod
    def evaluate(
        self,
        action: Action,
        observation: Observation,
        goal: Goal,
        pre_task_state: dict
    ) -> Tuple[EvaluationEnum, Optional[ProgressInfo]]:
        """Return an evaluation and optional progress info.

        Args:
            action: The action that was executed.
            observation: The observation resulting from the action.
            goal: The goal being pursued.
            pre_task_state: A snapshot of the task state before the action.

        Returns:
            A tuple (evaluation, progress_info).
        """
        pass
