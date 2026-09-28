
from ...core.state.agent_state import ConversationState, TaskGoalState
from ...core.state.attempt import Attempt
from ...core.state.next_action import NextAction
from ...core.state.reflection import Reflection
from .base import ReflectionEngine


class StubReflector(ReflectionEngine):
    """Simple reflector that logs the attempt and suggests NOOP (replan)."""
    def reflect(
        self,
        attempt: Attempt,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> tuple[Reflection, NextAction | None]:
        reasoning = f"Attempted {attempt.action.tool_name} with args {attempt.action.arguments}; result: {attempt.observation.status}"
        # Always suggest NOOP -> orchestrator will increment version and replan
        next_action = NextAction.noop()
        reflection = Reflection.create(
            attempt=attempt,
            goal_id=task_state.active_goal_id if task_state.active_goal_id else attempt.action.action_id,  # fallback
            reasoning=reasoning,
            next_action=next_action
        )
        return reflection, next_action