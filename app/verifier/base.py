from dataclasses import dataclass
from typing import Any
from abc import ABC, abstractmethod
from ...core.state.goal_state import Goal
from ...core.state.agent_state import TaskGoalState

@dataclass(frozen=True)
class VerificationResult:
    success: bool
    detail: str = ""  # optional message or debug info

class Verifier(ABC):
    """Interface for checking whether a goal is truly satisfied."""
    @abstractmethod
    def verify(self, goal: Goal, task_state: TaskGoalState) -> VerificationResult:
        """Return VerificationResult indicating if goal is met."""
        pass
