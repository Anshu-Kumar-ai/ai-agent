import time
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class SuccessSpec:
    criteria: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'SuccessSpec':
        return SuccessSpec(**data)

@dataclass(frozen=True)
class Goal:
    goal_id: UUID
    description: str
    success_criteria: SuccessSpec
    subgoal_ids: list[UUID] = field(default_factory=list)
    parent_goal_id: UUID | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert UUIDs to strings
        d['goal_id'] = str(self.goal_id)
        d['subgoal_ids'] = [str(uid) for uid in self.subgoal_ids]
        if self.parent_goal_id is not None:
            d['parent_goal_id'] = str(self.parent_goal_id)
        # success_criteria is a dataclass, asdict already handled it
        return d

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'Goal':
        data = data.copy()
        data['goal_id'] = UUID(data['goal_id'])
        data['subgoal_ids'] = [UUID(uid) for uid in data.get('subgoal_ids', [])]
        parent_goal_id = data.get('parent_goal_id')
        if parent_goal_id is not None:
            data['parent_goal_id'] = UUID(parent_goal_id)
        # success_criteria is a nested dict
        data['success_criteria'] = SuccessSpec.from_dict(data['success_criteria'])
        return Goal(**data)

    @staticmethod
    def create(description: str, success_criteria: SuccessSpec) -> 'Goal':
        return Goal(
            goal_id=uuid4(),
            description=description,
            success_criteria=success_criteria,
            created_at=time.time()
        )

@dataclass(frozen=True)
class SubGoal(Goal):
    def __post_init__(self):
        if self.parent_goal_id is None:
            raise ValueError("SubGoal must have a parent_goal_id")

    # Note: SubGoal inherits to_dict and from_dict from Goal, but we need to ensure
    # that when we instantiate from_dict we get a SubGoal.
    # We'll override from_dict to return SubGoal.
    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'SubGoal':
        data = data.copy()
        data['goal_id'] = UUID(data['goal_id'])
        data['subgoal_ids'] = [UUID(uid) for uid in data.get('subgoal_ids', [])]
        parent_goal_id = data.get('parent_goal_id')
        if parent_goal_id is not None:
            data['parent_goal_id'] = UUID(parent_goal_id)
        data['success_criteria'] = SuccessSpec.from_dict(data['success_criteria'])
        return SubGoal(**data)
