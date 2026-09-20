from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID, uuid4
import time
from copy import deepcopy

from .observation import Observation
from .evaluation import EvaluationEnum, ProgressInfo
from .action import Action  # forward reference

@dataclass
class Attempt:
    attempt_id: UUID
    action: Action
    pre_task_state_snapshot: Any  # shallow copy of relevant TaskGoalState
    observation: Observation
    evaluation: EvaluationEnum
    progress_info: Optional[ProgressInfo]
    started_at: float
    ended_at: float
    agent_state_version: int

    @staticmethod
    def create(
        action: Action,
        pre_task_state_snapshot: Any,
        agent_state_version: int
    ) -> 'Attempt':
        """Create a new attempt before execution. Call end() after execution completes."""
        now = time.time()
        return Attempt(
            attempt_id=uuid4(),
            action=action,
            pre_task_state_snapshot=pre_task_state_snapshot,
            observation=Observation.error("Action not yet executed"),
            evaluation=EvaluationEnum.ACTION_FAILED,
            progress_info=None,
            started_at=now,
            ended_at=now,  # will be updated by end()
            agent_state_version=agent_state_version
        )

    def end(
        self,
        observation: Observation,
        evaluation: EvaluationEnum,
        progress_info: Optional[ProgressInfo]
    ) -> None:
        """Mark the attempt as completed with the final results."""
        self.observation = observation
        self.evaluation = evaluation
        self.progress_info = progress_info
        self.ended_at = time.time()

    @staticmethod
    def _make_json_serializable(obj):
        if obj is None:
            return None
        if isinstance(obj, (int, float, str, bool)):
            return obj
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, list):
            return [Attempt._make_json_serializable(item) for item in obj]
        if isinstance(obj, dict):
            return {k: Attempt._make_json_serializable(v) for k, v in obj.items()}
        if hasattr(obj, "to_dict"):
            return Attempt._make_json_serializable(obj.to_dict())
        return obj

    def to_dict(self) -> dict:
        snapshot = deepcopy(self.pre_task_state_snapshot)
        if isinstance(snapshot, dict) and 'attempt_history' in snapshot and isinstance(snapshot['attempt_history'], list):
            # Serialize attempt_history as minimal references to avoid cyclic serialization.
            # Each entry becomes a dict with just attempt_id and agent_state_version.
            minimal_history = []
            for attempt in snapshot['attempt_history']:
                if hasattr(attempt, 'attempt_id') and hasattr(attempt, 'agent_state_version'):
                    minimal_history.append({
                        "attempt_id": str(attempt.attempt_id),
                        "agent_state_version": attempt.agent_state_version,
                    })
                else:
                    # Already serialized or unexpected format - include as-is
                    minimal_history.append(attempt)
            snapshot['attempt_history'] = minimal_history
        snapshot = Attempt._make_json_serializable(snapshot)
        d = {
            "attempt_id": str(self.attempt_id),
            "action": self.action.to_dict(),
            "pre_task_state_snapshot": snapshot,
            "observation": self.observation.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "progress_info": self.progress_info.to_dict() if self.progress_info is not None else None,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "agent_state_version": self.agent_state_version,
        }
        return d

    @staticmethod
    def from_dict(data: dict) -> 'Attempt':
        data = data.copy()
        data['attempt_id'] = UUID(data['attempt_id'])
        data['action'] = Action.from_dict(data['action'])
        data['pre_task_state_snapshot'] = data.get('pre_task_state_snapshot')
        data['observation'] = Observation.from_dict(data['observation'])
        data['evaluation'] = EvaluationEnum.from_dict(data['evaluation'])
        progress_info = data.get('progress_info')
        if progress_info is not None:
            data['progress_info'] = ProgressInfo.from_dict(progress_info)
        else:
            data['progress_info'] = None
        data['started_at'] = float(data['started_at'])
        data['ended_at'] = float(data['ended_at'])
        data['agent_state_version'] = int(data['agent_state_version'])
        return Attempt(**data)