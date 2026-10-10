"""Event model for monitoring and observability."""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventType(Enum):
    """Types of events that can be recorded."""
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_SUCCESS = "provider_success"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_FALLBACK = "provider_fallback"
    PROVIDER_COOLDOWN = "provider_cooldown"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    PERMISSION_REQUESTED = "permission_requested"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    MEMORY_WRITE = "memory_write"
    ATTEMPT_CREATED = "attempt_created"
    ATTEMPT_COMPARISON = "attempt_comparison"
    LOCAL_MODEL_ACTIVATED = "local_model_activated"
    AGENT_LOOP_ITERATION = "agent_loop_iteration"
    # Planning events (Phase 19)
    PLANNING_GOAL_INTERPRETED = "planning.goal_interpreted"
    PLANNING_CAPABILITIES_DISCOVERED = "planning.capabilities_discovered"
    PLANNING_TOOLS_RANKED = "planning.tools_ranked"
    PLANNING_MEMORY_RETRIEVED = "planning.memory_retrieved"
    PLANNING_SKILL_SELECTED = "planning.skill_selected"
    PLANNING_PLAN_GENERATED = "planning.plan_generated"
    PLANNING_PLAN_VALIDATED = "planning.plan_validated"
    PLANNING_PLAN_REJECTED = "planning.plan_rejected"
    PLANNING_PLAN_EVALUATED = "planning.plan_evaluated"
    PLANNING_REPLAN = "planning.replan"
    PLANNING_REFLECTION_CREATED = "planning.reflection_created"
    PLANNING_SKILL_UPDATED = "planning.skill_updated"
    PLANNING_CAPABILITY_UNAVAILABLE = "planning.capability_unavailable"
    # Browser events
    BROWSER_SESSION_CREATED = "browser_session_created"
    BROWSER_SESSION_CLOSED = "browser_session_closed"
    BROWSER_TAB_OPENED = "browser_tab_opened"
    BROWSER_TAB_CLOSED = "browser_tab_closed"
    BROWSER_NAVIGATION = "browser_navigation"
    BROWSER_ACTION = "browser_action"
    BROWSER_ERROR = "browser_error"
    # Desktop events
    DESKTOP_APPLICATION_OPENED = "desktop_application_opened"
    DESKTOP_WINDOW_CHANGED = "desktop_window_changed"
    DESKTOP_ACTION = "desktop_action"
    DESKTOP_ERROR = "desktop_error"


@dataclass
class MonitorEvent:
    """A structured monitoring event."""
    event_id: str
    timestamp: str  # ISO format
    event_type: str
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tool: Optional[str] = None
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    error_type: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonitorEvent":
        """Create from dictionary."""
        return cls(**data)


def create_event(
    event_type: EventType,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    tool: Optional[str] = None,
    duration_ms: Optional[float] = None,
    success: Optional[bool] = None,
    error_type: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> MonitorEvent:
    """Create a new monitoring event."""
    return MonitorEvent(
        event_id=str(uuid.uuid4()),
        timestamp=timestamp or datetime.utcnow().isoformat() + "Z",
        event_type=event_type.value,
        task_id=task_id,
        session_id=session_id,
        provider=provider,
        model=model,
        tool=tool,
        duration_ms=duration_ms,
        success=success,
        error_type=error_type,
        metadata=metadata or {},
    )


# Sensitive keys that should be redacted
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "api_key",
    "authorization",
    "auth_token",
    "access_token",
    "secret",
    "password",
    "passwd",
    "token",
    "bearer",
    "cookie",
    "x-api-key",
    "x-auth-token",
    "private_key",
    "privatekey",
}


def sanitize_metadata(metadata: dict[str, Any], redact_full_prompts: bool = True) -> dict[str, Any]:
    """Sanitize metadata by removing or redacting sensitive information."""
    if not metadata:
        return {}

    sanitized = {}

    for key, value in metadata.items():
        key_lower = key.lower()

        # Check for sensitive keys
        if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "[REDACTED]"
            continue

        # Handle string values that might contain sensitive data
        if isinstance(value, str):
            # Redact API key patterns
            if redact_full_prompts and len(value) > 500:
                sanitized[key] = value[:200] + "... [TRUNCATED]"
            else:
                sanitized[key] = value
        elif isinstance(value, dict):
            sanitized[key] = sanitize_metadata(value, redact_full_prompts)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_metadata(item, redact_full_prompts) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized