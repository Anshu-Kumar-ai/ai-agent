from dataclasses import asdict, dataclass, field
from typing import Any


class NextActionType:
    RETRY = "RETRY"
    ALTERNATIVE_TOOL = "ALTERNATIVE_TOOL"
    PARAM_CHANGE = "PARAM_CHANGE"
    DECOMPOSE_FURTHER = "DECOMPOSE_FURTHER"
    WAIT_FOR_EXTERNAL = "WAIT_FOR_EXTERNAL"
    NOOP = "NOOP"

@dataclass(frozen=True)
class NextAction:
    action_type: str  # one of NextActionType constants
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 0-1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'NextAction':
        return NextAction(**data)

    @staticmethod
    def retry(payload: dict[str, Any] | None = None, confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.RETRY,
            payload={} if payload is None else dict(payload),
            confidence=confidence
        )

    @staticmethod
    def alternative_tool(tool_name: str, payload: dict[str, Any] | None = None, confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.ALTERNATIVE_TOOL,
            payload={"tool_name": tool_name, **(payload or {})},
            confidence=confidence
        )

    @staticmethod
    def param_change(params: dict[str, Any], confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.PARAM_CHANGE,
            payload=dict(params),
            confidence=confidence
        )

    @staticmethod
    def decompose_further(payload: dict[str, Any] | None = None, confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.DECOMPOSE_FURTHER,
            payload={} if payload is None else dict(payload),
            confidence=confidence
        )

    @staticmethod
    def wait_for_external(payload: dict[str, Any] | None = None, confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.WAIT_FOR_EXTERNAL,
            payload={} if payload is None else dict(payload),
            confidence=confidence
        )

    @staticmethod
    def noop(payload: dict[str, Any] | None = None, confidence: float = 1.0) -> 'NextAction':
        return NextAction(
            action_type=NextActionType.NOOP,
            payload={} if payload is None else dict(payload),
            confidence=confidence
        )
