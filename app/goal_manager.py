from typing import Dict, Optional
from uuid import UUID
from ..core.state.goal_state import Goal, SubGoal
import time

class GoalManager:
    """Owns the lifecycle of Goal definitions and provides creation/retrieval."""
    def __init__(self):
        self._goals: Dict[UUID, Goal] = {}

    def create_goal(self, description: str, success_criteria) -> Goal:
        goal = Goal.create(description, success_criteria)
        self._goals[goal.goal_id] = goal
        return goal

    def create_subgoal(self, parent_goal_id: UUID, description: str, success_criteria) -> 'SubGoal':
        parent = self._goals.get(parent_goal_id)
        if parent is None:
            raise ValueError(f"Parent goal {parent_goal_id} not found")
        subgoal = SubGoal(
            goal_id=uuid4(),
            description=description,
            success_criteria=success_criteria,
            parent_goal_id=parent_goal_id,
            created_at=time.time()
        )
        self._goals[subgoal.goal_id] = subgoal
        return subgoal

    def get_goal(self, goal_id: UUID) -> Optional[Goal]:
        return self._goals.get(goal_id)