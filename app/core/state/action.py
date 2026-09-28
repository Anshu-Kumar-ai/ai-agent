from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from .observation import ToolStatus


@dataclass(frozen=True)
class SandboxSpec:
    fs_root: str | None = None  # path to chroot or restricted directory
    container_limits: dict[str, Any] = field(default_factory=dict)  # e.g., memory, cpu
    browser_profile: str | None = None
    # add more as needed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'SandboxSpec':
        return SandboxSpec(**data)

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_factor: float = 1.0  # seconds
    retry_on: list = field(default_factory=lambda: [ToolStatus.ERROR, ToolStatus.TIMEOUT])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['retry_on'] = [e.value if isinstance(e, Enum) else e for e in self.retry_on]
        return d

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'RetryPolicy':
        # retry_on is expected to be a list of strings matching ToolStatus constants
        data['retry_on'] = data.get('retry_on', [])
        return RetryPolicy(**data)

@dataclass(frozen=True)
class Action:
    action_id: UUID
    tool_name: str
    arguments: dict[str, Any]
    sandbox: SandboxSpec
    timeout_sec: float
    retry_policy: RetryPolicy

    @staticmethod
    def create(
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        sandbox: SandboxSpec | None = None,
        timeout_sec: float = 30.0,
        retry_policy: RetryPolicy | None = None
    ) -> 'Action':
        return Action(
            action_id=uuid4(),
            tool_name=tool_name,
            arguments={} if arguments is None else dict(arguments),
            sandbox=sandbox if sandbox is not None else SandboxSpec(),
            timeout_sec=timeout_sec,
            retry_policy=retry_policy if retry_policy is not None else RetryPolicy()
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d['action_id'] = str(self.action_id)
        d['sandbox'] = self.sandbox.to_dict()
        d['retry_policy'] = self.retry_policy.to_dict()
        return d

    @staticmethod
    def from_dict(data: dict[str, Any]) -> 'Action':
        data = data.copy()
        data['action_id'] = UUID(data['action_id'])
        data['sandbox'] = SandboxSpec.from_dict(data['sandbox'])
        data['retry_policy'] = RetryPolicy.from_dict(data['retry_policy'])
        return Action(**data)