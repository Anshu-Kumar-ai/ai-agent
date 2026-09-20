from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
import time

from .action import Action
from .observation import Observation
from .evaluation import EvaluationEnum, ProgressInfo
from .next_action import NextAction

@dataclass(frozen=True)
class Reflection:
    reflection_id: UUID
    attempt_id: UUID
    goal_id: UUID
    action: Action
    observation: Observation
    evaluation: EvaluationEnum
    progress_info: Optional[ProgressInfo]
    reasoning: str
    next_action: Optional[NextAction]
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert UUIDs to strings
        d['reflection_id'] = str(self.reflection_id)
        d['attempt_id'] = str(self.attempt_id)
        d['goal_id'] = str(self.goal_id)
        # action is a dataclass
        d['action'] = self.action.to_dict()
        # observation is a dataclass
        d['observation'] = self.observation.to_dict()
        # evaluation is an Enum
        d['evaluation'] = self.evaluation.to_dict()
        # progress_info is a dataclass or None
        if self.progress_info is not None:
            d['progress_info'] = self.progress_info.to_dict()
        # next_action is a dataclass or None
        if self.next_action is not None:
            d['next_action'] = self.next_action.to_dict()
        # timestamp is a float, fine as is
        return d

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Reflection':
        data = data.copy()
        data['reflection_id'] = UUID(data['reflection_id'])
        data['attempt_id'] = UUID(data['attempt_id'])
        data['goal_id'] = UUID(data['goal_id'])
        data['action'] = Action.from_dict(data['action'])
        data['observation'] = Observation.from_dict(data['observation'])
        data['evaluation'] = EvaluationEnum.from_dict(data['evaluation'])
        progress_info = data.get('progress_info')
        if progress_info is not None:
            data['progress_info'] = ProgressInfo.from_dict(progress_info)
        next_action = data.get('next_action')
        if next_action is not None:
            data['next_action'] = NextAction.from_dict(next_action)
        # timestamp is a float
        return Reflection(**data)

    @staticmethod
    def create(
        attempt: 'Attempt',
        goal_id: UUID,
        reasoning: str,
        next_action: Optional[NextAction] = None
    ) -> 'Reflection':
        return Reflection(
            reflection_id=uuid4(),
            attempt_id=attempt.attempt_id,
            goal_id=goal_id,
            action=attempt.action,
            observation=attempt.observation,
            evaluation=attempt.evaluation,
            progress_info=attempt.progress_info,
            reasoning=reasoning,
            next_action=next_action,
            timestamp=time.time()
        )
