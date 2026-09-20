from .base import Planner
from ...core.state.action import Action, SandboxSpec
from ...core.state.agent_state import TaskGoalState, ConversationState
from ...core.state.goal_state import Goal

class StubPlanner(Planner):
    """Very simple planner that always returns a single echo action."""
    def plan(
        self,
        goal: Goal,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> list:
        # Return an echo tool action with a simple argument
        action = Action.create(
            tool_name="echo",
            arguments={"msg": f"Processing goal: {goal.description}"},
            sandbox=SandboxSpec(),
            timeout_sec=10.0
        )
        return [action]