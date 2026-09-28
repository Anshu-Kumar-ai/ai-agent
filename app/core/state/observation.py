from dataclasses import asdict, dataclass, field
from typing import Any


class ToolStatus:
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"

@dataclass(frozen=True)
class Observation:
    status: str
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    side_effects: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'Observation':
        return Observation(**data)

    @staticmethod
    def success(payload=None, metadata=None, side_effects=None, raw=""):
        return Observation(
            status=ToolStatus.SUCCESS,
            payload=payload,
            metadata={} if metadata is None else dict(metadata),
            side_effects={} if side_effects is None else dict(side_effects),
            raw=raw
        )

    @staticmethod
    def error(message="", raw=""):
        return Observation(
            status=ToolStatus.ERROR,
            metadata={"error": message},
            raw=raw
        )

    @staticmethod
    def timeout(raw=""):
        return Observation(status=ToolStatus.TIMEOUT, raw=raw)

    @staticmethod
    def permission_denied(raw=""):
        return Observation(status=ToolStatus.PERMISSION_DENIED, raw=raw)

    @staticmethod
    def tool_not_found(raw=""):
        return Observation(status=ToolStatus.TOOL_NOT_FOUND, raw=raw)
