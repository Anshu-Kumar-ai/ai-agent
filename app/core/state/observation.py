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
    def create_success(payload=None, metadata=None, side_effects=None, raw=""):
        return Observation(
            status=ToolStatus.SUCCESS,
            payload=payload,
            metadata={} if metadata is None else dict(metadata),
            side_effects={} if side_effects is None else dict(side_effects),
            raw=raw
        )

    @staticmethod
    def create_error(message="", metadata=None, raw=""):
        if metadata is None:
            metadata = {}
        metadata["error"] = message
        return Observation(
            status=ToolStatus.ERROR,
            metadata=metadata,
            raw=raw
        )

    @staticmethod
    def create_timeout(metadata=None, raw=""):
        return Observation(
            status=ToolStatus.TIMEOUT,
            metadata={} if metadata is None else dict(metadata),
            raw=raw
        )

    @staticmethod
    def create_permission_denied(raw=""):
        return Observation(status=ToolStatus.PERMISSION_DENIED, raw=raw)

    @staticmethod
    def create_tool_not_found(raw=""):
        return Observation(status=ToolStatus.TOOL_NOT_FOUND, raw=raw)

    # Compatibility properties for tests
    @property
    def is_success(self) -> bool:
        """Return True if the observation status is SUCCESS."""
        return self.status == ToolStatus.SUCCESS

    # Alias for backward compatibility
    @property
    def success(self) -> bool:
        """Return True if the observation status is SUCCESS (alias for is_success)."""
        return self.status == ToolStatus.SUCCESS

    @property
    def data(self) -> dict:
        """Return payload as data for compatibility."""
        if self.payload is None:
            return {"error": self.metadata.get("error", ""), "stderr": self.metadata.get("stderr", "")}
        if isinstance(self.payload, dict):
            return self.payload
        return {"content": self.payload, "error": self.metadata.get("error", ""), "stderr": self.metadata.get("stderr", "")}
