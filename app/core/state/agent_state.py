from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
import time

from .observation import Observation
from .evaluation import EvaluationEnum, ProgressInfo
from .action import Action
from .attempt import Attempt

@dataclass
class TaskGoalState:
    version: int
    active_goal_id: Optional[UUID]
    goal_stack: List[UUID]
    progress_metrics: Dict[str, float]
    attempt_history: List['Attempt']
    working_memory: Dict[str, Any]
    sandbox_context: Dict[str, Any]

    @staticmethod
    def initial() -> 'TaskGoalState':
        return TaskGoalState(
            version=0,
            active_goal_id=None,
            goal_stack=[],
            progress_metrics={},
            attempt_history=[],
            working_memory={},
            sandbox_context={}
        )

    def to_dict(self) -> dict:
        d = {
            "version": self.version,
            "active_goal_id": str(self.active_goal_id) if self.active_goal_id is not None else None,
            "goal_stack": [str(uid) for uid in self.goal_stack],
            "progress_metrics": self.progress_metrics,
            "attempt_history": [attempt.to_dict() for attempt in self.attempt_history],
            "working_memory": self.working_memory,
            "sandbox_context": self.sandbox_context,
        }
        return d

    @staticmethod
    def from_dict(data: dict) -> 'TaskGoalState':
        data = data.copy()
        data['version'] = int(data['version'])
        active_goal_id = data.get('active_goal_id')
        data['active_goal_id'] = UUID(active_goal_id) if active_goal_id is not None else None
        goal_stack = data.get('goal_stack', [])
        data['goal_stack'] = [UUID(uid) for uid in goal_stack]
        data['progress_metrics'] = data['progress_metrics']
        data['attempt_history'] = [Attempt.from_dict(attempt_dict) for attempt_dict in data['attempt_history']]
        data['working_memory'] = data['working_memory']
        data['sandbox_context'] = data['sandbox_context']
        return TaskGoalState(**data)

@dataclass
class ConversationState:
    turns: List['Turn'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_user_utterance(self, text: str) -> None:
        self.turns.append(Turn(role="user", text=text, timestamp=time.time()))
        if len(self.turns) > 20:
            self.turns = self.turns[-20:]

    def add_agent_utterance(self, text: str) -> None:
        self.turns.append(Turn(role="agent", text=text, timestamp=time.time()))
        if len(self.turns) > 20:
            self.turns = self.turns[-20:]

    def get_recent_turns(self, n: int) -> List['Turn']:
        return self.turns[-n:] if n <= len(self.turns) else self.turns[:]

    def to_dict(self) -> dict:
        d = {
            "turns": [turn.to_dict() for turn in self.turns],
            "metadata": self.metadata,
        }
        return d

    @staticmethod
    def from_dict(data: dict) -> 'ConversationState':
        data = data.copy()
        data['turns'] = [Turn.from_dict(turn_dict) for turn_dict in data['turns']]
        data['metadata'] = data['metadata']
        return ConversationState(**data)

@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "agent"
    text: str
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> 'Turn':
        return Turn(
            role=data['role'],
            text=data['text'],
            timestamp=float(data['timestamp'])
        )