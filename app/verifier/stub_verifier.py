from .base import Verifier, VerificationResult
from ...core.state.goal_state import Goal
from ...core.state.agent_state import TaskGoalState
from ...core.state.observation import Observation, ToolStatus

class StubVerifier(Verifier):
    """Verifier that succeeds if any echo tool action succeeded."""
    def verify(self, goal: Goal, task_state: TaskGoalState) -> VerificationResult:
        for attempt in task_state.attempt_history:
            if attempt.action.tool_name == "echo" and attempt.observation.status == ToolStatus.SUCCESS:
                return VerificationResult(success=True, detail="Echo succeeded")
        return VerificationResult(success=False, detail="No successful echo yet")