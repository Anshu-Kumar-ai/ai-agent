from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

class EvaluationEnum(Enum):
    TOOL_SUCCEEDED = "TOOL_SUCCEEDED"
    PROGRESS_MADE = "PROGRESS_MADE"
    NO_MEANINGFUL_PROGRESS = "NO_MEANINGFUL_PROGRESS"
    ACTION_FAILED = "ACTION_FAILED"
    GOAL_COMPLETED = "GOAL_COMPLETED"
    GOAL_BLOCKED = "GOAL_BLOCKED"
    GOAL_IMPOSSIBLE = "GOAL_IMPOSSIBLE"

    def to_dict(self) -> str:
        return self.value

    @staticmethod
    def from_dict(value: str) -> 'EvaluationEnum':
        return EvaluationEnum(value)

@dataclass(frozen=True)
class ProgressInfo:
    metric_name: str
    value: float  # normalized 0-1 or raw
    delta: float  # change from pre to post
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ProgressInfo':
        return ProgressInfo(**data)

    @staticmethod
    def unknown() -> 'ProgressInfo':
        return ProgressInfo(metric_name="unknown", value=0.0, delta=0.0)
