"""Event emitter for integrating monitoring into existing components."""

import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

from app.monitoring.events import (
    MonitorEvent,
    EventType,
    create_event,
    sanitize_metadata,
)
from app.monitoring.store import MonitoringStore, get_store


logger = logging.getLogger(__name__)


class EventEmitter:
    """Thread-safe event emitter that records monitoring events."""

    def __init__(
        self,
        store: Optional[MonitoringStore] = None,
        session_id: Optional[str] = None,
        enabled: bool = True,
    ):
        self._store = store
        self._session_id = session_id
        self._enabled = enabled
        self._lock = None  # Will be initialized on first use

    @property
    def store(self) -> MonitoringStore:
        """Get the monitoring store (lazy initialization)."""
        if self._store is None:
            self._store = get_store()
        return self._store

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def emit(
        self,
        event_type: EventType,
        task_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tool: Optional[str] = None,
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        error_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        sanitize: bool = True,
    ) -> Optional[MonitorEvent]:
        """Emit a monitoring event. Returns the event if successful, None if disabled or failed."""
        if not self._enabled:
            return None

        try:
            meta = metadata or {}
            if sanitize:
                meta = sanitize_metadata(meta)

            event = create_event(
                event_type=event_type,
                task_id=task_id,
                session_id=self._session_id,
                provider=provider,
                model=model,
                tool=tool,
                duration_ms=duration_ms,
                success=success,
                error_type=error_type,
                metadata=meta,
            )

            self.store.insert_event(event)
            return event

        except Exception as e:
            # Monitoring failure must not break agent execution
            logger.debug(f"Monitoring emit failed: {e}")
            return None

    @contextmanager
    def measure(
        self,
        event_type: EventType,
        task_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tool: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """Context manager to measure duration and emit start/completion events."""
        start_time = time.perf_counter()
        success = True
        error_type = None

        # Emit start event
        self.emit(
            event_type=event_type,
            task_id=task_id,
            provider=provider,
            model=model,
            tool=tool,
            duration_ms=None,
            success=None,
            error_type=None,
            metadata=metadata,
        )

        try:
            yield
        except Exception as e:
            success = False
            error_type = type(e).__name__
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Emit completion or failure event based on the event_type
            if event_type == EventType.TOOL_STARTED:
                if success:
                    self.emit(
                        event_type=EventType.TOOL_COMPLETED,
                        task_id=task_id,
                        provider=provider,
                        model=model,
                        tool=tool,
                        duration_ms=duration_ms,
                        success=True,
                        error_type=None,
                        metadata=metadata,
                    )
                else:
                    self.emit(
                        event_type=EventType.TOOL_FAILED,
                        task_id=task_id,
                        provider=provider,
                        model=model,
                        tool=tool,
                        duration_ms=duration_ms,
                        success=False,
                        error_type=error_type,
                        metadata=metadata,
                    )
            elif event_type == EventType.PROVIDER_REQUEST:
                if success:
                    self.emit(
                        event_type=EventType.PROVIDER_SUCCESS,
                        task_id=task_id,
                        provider=provider,
                        model=model,
                        duration_ms=duration_ms,
                        success=True,
                        metadata=metadata,
                    )
                else:
                    self.emit(
                        event_type=EventType.PROVIDER_FAILURE,
                        task_id=task_id,
                        provider=provider,
                        model=model,
                        duration_ms=duration_ms,
                        success=False,
                        error_type=error_type,
                        metadata=metadata,
                    )
            else:
                # For other event types, emit with the original event_type but with duration and success
                self.emit(
                    event_type=event_type,
                    task_id=task_id,
                    provider=provider,
                    model=model,
                    tool=tool,
                    duration_ms=duration_ms,
                    success=success,
                    error_type=error_type,
                    metadata=metadata,
                )


# Global emitter instance
_emitter: Optional[EventEmitter] = None


def get_emitter() -> EventEmitter:
    """Get or create the global event emitter."""
    global _emitter
    if _emitter is None:
        _emitter = EventEmitter()
    return _emitter


def set_emitter(emitter: EventEmitter) -> None:
    """Set the global event emitter (for testing)."""
    global _emitter
    _emitter = emitter


def configure_monitoring(
    enabled: bool = True,
    session_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> EventEmitter:
    """Configure global monitoring settings."""
    from app.monitoring.store import MonitoringStore, set_store

    if db_path:
        store = MonitoringStore(db_path=db_path)
        set_store(store)

    emitter = EventEmitter(session_id=session_id, enabled=enabled)
    set_emitter(emitter)
    return emitter


# Convenience functions for common event types

def emit_task_started(task_id: str, message: str, **kwargs) -> Optional[MonitorEvent]:
    """Emit task_started event."""
    return get_emitter().emit(
        EventType.TASK_STARTED,
        task_id=task_id,
        metadata={"message_preview": message[:200], **kwargs},
    )


def emit_task_completed(task_id: str, duration_ms: float, **kwargs) -> Optional[MonitorEvent]:
    """Emit task_completed event."""
    return get_emitter().emit(
        EventType.TASK_COMPLETED,
        task_id=task_id,
        duration_ms=duration_ms,
        success=True,
        **kwargs,
    )


def emit_task_failed(task_id: str, duration_ms: float, error: str, **kwargs) -> Optional[MonitorEvent]:
    """Emit task_failed event."""
    return get_emitter().emit(
        EventType.TASK_FAILED,
        task_id=task_id,
        duration_ms=duration_ms,
        success=False,
        error_type=error,
        **kwargs,
    )


def emit_provider_request(
    provider: str,
    model: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit provider_request event."""
    return get_emitter().emit(
        EventType.PROVIDER_REQUEST,
        task_id=task_id,
        provider=provider,
        model=model,
        metadata=kwargs,
    )


def emit_provider_success(
    provider: str,
    model: str,
    duration_ms: float,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit provider_success event."""
    return get_emitter().emit(
        EventType.PROVIDER_SUCCESS,
        task_id=task_id,
        provider=provider,
        model=model,
        duration_ms=duration_ms,
        success=True,
        metadata=kwargs,
    )


def emit_provider_failure(
    provider: str,
    model: str,
    duration_ms: float,
    error_type: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit provider_failure event."""
    return get_emitter().emit(
        EventType.PROVIDER_FAILURE,
        task_id=task_id,
        provider=provider,
        model=model,
        duration_ms=duration_ms,
        success=False,
        error_type=error_type,
        metadata=kwargs,
    )


def emit_provider_fallback(
    from_provider: str,
    to_provider: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit provider_fallback event."""
    return get_emitter().emit(
        EventType.PROVIDER_FALLBACK,
        task_id=task_id,
        provider=from_provider,
        model=to_provider,
        metadata={"from_provider": from_provider, "to_provider": to_provider, **kwargs},
    )


def emit_tool_started(
    tool: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit tool_started event."""
    return get_emitter().emit(
        EventType.TOOL_STARTED,
        task_id=task_id,
        tool=tool,
        metadata=kwargs,
    )


def emit_tool_completed(
    tool: str,
    duration_ms: float,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit tool_completed event."""
    return get_emitter().emit(
        EventType.TOOL_COMPLETED,
        task_id=task_id,
        tool=tool,
        duration_ms=duration_ms,
        success=True,
        metadata=kwargs,
    )


def emit_tool_failed(
    tool: str,
    duration_ms: float,
    error_type: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit tool_failed event."""
    return get_emitter().emit(
        EventType.TOOL_FAILED,
        task_id=task_id,
        tool=tool,
        duration_ms=duration_ms,
        success=False,
        error_type=error_type,
        metadata=kwargs,
    )


def emit_permission_requested(
    tool: str,
    risk_level: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit permission_requested event."""
    return get_emitter().emit(
        EventType.PERMISSION_REQUESTED,
        task_id=task_id,
        tool=tool,
        metadata={"risk_level": risk_level, **kwargs},
    )


def emit_permission_granted(
    tool: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit permission_granted event."""
    return get_emitter().emit(
        EventType.PERMISSION_GRANTED,
        task_id=task_id,
        tool=tool,
        success=True,
        metadata=kwargs,
    )


def emit_permission_denied(
    tool: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit permission_denied event."""
    return get_emitter().emit(
        EventType.PERMISSION_DENIED,
        task_id=task_id,
        tool=tool,
        success=False,
        metadata=kwargs,
    )


def emit_memory_write(
    memory_type: str,
    task_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit memory_write event."""
    combined_metadata = {**kwargs}
    if metadata:
        combined_metadata.update(metadata)
    return get_emitter().emit(
        EventType.MEMORY_WRITE,
        task_id=task_id,
        tool=memory_type,
        metadata=combined_metadata,
    )


def emit_attempt_created(
    task_id: str,
    attempt_num: int,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit attempt_created event."""
    return get_emitter().emit(
        EventType.ATTEMPT_CREATED,
        task_id=task_id,
        metadata={"attempt_number": attempt_num, **kwargs},
    )


def emit_attempt_comparison(
    task_id: str,
    is_improvement: bool,
    score_delta: float,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit attempt_comparison event."""
    return get_emitter().emit(
        EventType.ATTEMPT_COMPARISON,
        task_id=task_id,
        success=is_improvement,
        metadata={"score_delta": score_delta, **kwargs},
    )


def emit_local_model_activated(
    reason: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit local_model_activated event."""
    return get_emitter().emit(
        EventType.LOCAL_MODEL_ACTIVATED,
        task_id=task_id,
        metadata={"reason": reason, **kwargs},
    )


def emit_agent_loop_iteration(
    task_id: str,
    iteration: int,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit agent_loop_iteration event."""
    return get_emitter().emit(
        EventType.AGENT_LOOP_ITERATION,
        task_id=task_id,
        metadata={"iteration": iteration, **kwargs},
    )


# Planning event emitters (Phase 19)

def emit_planning_goal_interpreted(
    task_id: str,
    goal: str,
    interpretation: str,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.goal_interpreted event."""
    return get_emitter().emit(
        EventType.PLANNING_GOAL_INTERPRETED,
        task_id=task_id,
        metadata={"goal": goal, "interpretation": interpretation, **kwargs},
    )


def emit_planning_capabilities_discovered(
    task_id: str,
    capabilities: list[str],
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.capabilities_discovered event."""
    return get_emitter().emit(
        EventType.PLANNING_CAPABILITIES_DISCOVERED,
        task_id=task_id,
        metadata={"capabilities": capabilities, **kwargs},
    )


def emit_planning_tools_ranked(
    task_id: str,
    tools: list[str],
    scores: list[float],
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.tools_ranked event."""
    return get_emitter().emit(
        EventType.PLANNING_TOOLS_RANKED,
        task_id=task_id,
        metadata={"tools": tools, "scores": scores, **kwargs},
    )


def emit_planning_memory_retrieved(
    task_id: str,
    memories_retrieved: int,
    reflections_used: int,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.memory_retrieved event."""
    return get_emitter().emit(
        EventType.PLANNING_MEMORY_RETRIEVED,
        task_id=task_id,
        metadata={"memories_retrieved": memories_retrieved, "reflections_used": reflections_used, **kwargs},
    )


def emit_planning_skill_selected(
    task_id: str,
    skill_name: str,
    match_score: float,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.skill_selected event."""
    return get_emitter().emit(
        EventType.PLANNING_SKILL_SELECTED,
        task_id=task_id,
        metadata={"skill_name": skill_name, "match_score": match_score, **kwargs},
    )


def emit_planning_plan_generated(
    task_id: str,
    plan_id: str,
    version: int,
    steps: int,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.plan_generated event."""
    return get_emitter().emit(
        EventType.PLANNING_PLAN_GENERATED,
        task_id=task_id,
        metadata={"plan_id": plan_id, "version": version, "steps": steps, **kwargs},
    )


def emit_planning_plan_validated(
    task_id: str,
    plan_id: str,
    valid: bool,
    issues: list[str],
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.plan_validated event."""
    return get_emitter().emit(
        EventType.PLANNING_PLAN_VALIDATED,
        task_id=task_id,
        success=valid,
        metadata={"plan_id": plan_id, "valid": valid, "issues": issues, **kwargs},
    )


def emit_planning_plan_rejected(
    task_id: str,
    plan_id: str,
    reason: str,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.plan_rejected event."""
    return get_emitter().emit(
        EventType.PLANNING_PLAN_REJECTED,
        task_id=task_id,
        success=False,
        metadata={"plan_id": plan_id, "reason": reason, **kwargs},
    )


def emit_planning_plan_evaluated(
    task_id: str,
    plan_id: str,
    score: float,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.plan_evaluated event."""
    return get_emitter().emit(
        EventType.PLANNING_PLAN_EVALUATED,
        task_id=task_id,
        metadata={"plan_id": plan_id, "score": score, **kwargs},
    )


def emit_planning_replan(
    task_id: str,
    from_version: int,
    to_version: int,
    failure_category: str,
    reason: str,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.replan event."""
    return get_emitter().emit(
        EventType.PLANNING_REPLAN,
        task_id=task_id,
        metadata={
            "from_version": from_version,
            "to_version": to_version,
            "failure_category": failure_category,
            "reason": reason,
            **kwargs,
        },
    )


def emit_planning_reflection_created(
    task_id: str,
    reflection_type: str,
    task_type: str,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.reflection_created event."""
    return get_emitter().emit(
        EventType.PLANNING_REFLECTION_CREATED,
        task_id=task_id,
        metadata={"reflection_type": reflection_type, "task_type": task_type, **kwargs},
    )


def emit_planning_skill_updated(
    task_id: str,
    skill_name: str,
    success: bool,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.skill_updated event."""
    return get_emitter().emit(
        EventType.PLANNING_SKILL_UPDATED,
        task_id=task_id,
        success=success,
        metadata={"skill_name": skill_name, "success": success, **kwargs},
    )


def emit_planning_capability_unavailable(
    task_id: str,
    capability: str,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit planning.capability_unavailable event."""
    return get_emitter().emit(
        EventType.PLANNING_CAPABILITY_UNAVAILABLE,
        task_id=task_id,
        success=False,
        metadata={"capability": capability, **kwargs},
    )


# Browser event emitters

def emit_browser_session_created(
    session_id: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_session_created event."""
    return get_emitter().emit(
        EventType.BROWSER_SESSION_CREATED,
        task_id=task_id,
        session_id=session_id,
        metadata=kwargs,
    )


def emit_browser_session_closed(
    session_id: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_session_closed event."""
    return get_emitter().emit(
        EventType.BROWSER_SESSION_CLOSED,
        task_id=task_id,
        session_id=session_id,
        metadata=kwargs,
    )


def emit_browser_tab_opened(
    session_id: str,
    tab_id: str,
    url: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_tab_opened event."""
    return get_emitter().emit(
        EventType.BROWSER_TAB_OPENED,
        task_id=task_id,
        session_id=session_id,
        metadata={"tab_id": tab_id, "url": url, **kwargs},
    )


def emit_browser_tab_closed(
    session_id: str,
    tab_id: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_tab_closed event."""
    return get_emitter().emit(
        EventType.BROWSER_TAB_CLOSED,
        task_id=task_id,
        session_id=session_id,
        metadata={"tab_id": tab_id, **kwargs},
    )


def emit_browser_navigation(
    session_id: str,
    tab_id: str,
    url: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_navigation event."""
    return get_emitter().emit(
        EventType.BROWSER_NAVIGATION,
        task_id=task_id,
        session_id=session_id,
        metadata={"tab_id": tab_id, "url": url, **kwargs},
    )


def emit_browser_action(
    session_id: str,
    tab_id: str,
    action_type: str,
    task_id: Optional[str] = None,
    success: Optional[bool] = None,
    duration_ms: Optional[float] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_action event."""
    emitter = get_emitter()
    original_session_id = emitter.session_id
    emitter.session_id = session_id
    try:
        return emitter.emit(
            EventType.BROWSER_ACTION,
            task_id=task_id,
            tool=action_type,
            success=success,
            duration_ms=duration_ms,
            metadata={"tab_id": tab_id, **kwargs},
        )
    finally:
        emitter.session_id = original_session_id


def emit_browser_error(
    session_id: str,
    tab_id: str,
    error_type: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit browser_error event."""
    emitter = get_emitter()
    original_session_id = emitter.session_id
    emitter.session_id = session_id
    try:
        return emitter.emit(
            EventType.BROWSER_ERROR,
            task_id=task_id,
            error_type=error_type,
            success=False,
            metadata={"tab_id": tab_id, **kwargs},
        )
    finally:
        emitter.session_id = original_session_id


# Desktop event emitters

def emit_desktop_application_opened(
    executable: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit desktop_application_opened event."""
    return get_emitter().emit(
        EventType.DESKTOP_APPLICATION_OPENED,
        task_id=task_id,
        tool=executable,
        success=True,
        metadata=kwargs,
    )


def emit_desktop_window_changed(
    window_title: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit desktop_window_changed event."""
    return get_emitter().emit(
        EventType.DESKTOP_WINDOW_CHANGED,
        task_id=task_id,
        metadata={"window_title": window_title, **kwargs},
    )


def emit_desktop_action(
    action_type: str,
    task_id: Optional[str] = None,
    success: Optional[bool] = None,
    duration_ms: Optional[float] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit desktop_action event."""
    return get_emitter().emit(
        EventType.DESKTOP_ACTION,
        task_id=task_id,
        tool=action_type,
        success=success,
        duration_ms=duration_ms,
        metadata=kwargs,
    )


def emit_desktop_error(
    error_type: str,
    task_id: Optional[str] = None,
    **kwargs,
) -> Optional[MonitorEvent]:
    """Emit desktop_error event."""
    return get_emitter().emit(
        EventType.DESKTOP_ERROR,
        task_id=task_id,
        error_type=error_type,
        success=False,
        metadata=kwargs,
    )


# Decorator for automatic instrumentation

def monitored(
    event_type: EventType,
    task_id_getter: Optional[Callable[[], Optional[str]]] = None,
    tool_getter: Optional[Callable[[], Optional[str]]] = None,
    provider_getter: Optional[Callable[[], Optional[str]]] = None,
    model_getter: Optional[Callable[[], Optional[str]]] = None,
):
    """Decorator to automatically emit start/completion events for a function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            emitter = get_emitter()
            task_id = task_id_getter() if task_id_getter else None
            tool = tool_getter() if tool_getter else func.__name__
            provider = provider_getter() if provider_getter else None
            model = model_getter() if model_getter else None

            emitter.emit(
                EventType.TOOL_STARTED if event_type in (EventType.TOOL_STARTED, EventType.TOOL_COMPLETED, EventType.TOOL_FAILED)
                else event_type,
                task_id=task_id,
                tool=tool,
                provider=provider,
                model=model,
            )

            start_time = time.perf_counter()
            success = True
            error_type = None
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_type = type(e).__name__
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if event_type in (EventType.TOOL_STARTED, EventType.TOOL_COMPLETED, EventType.TOOL_FAILED):
                    if success:
                        emitter.emit(
                            EventType.TOOL_COMPLETED,
                            task_id=task_id,
                            tool=tool,
                            duration_ms=duration_ms,
                            success=True,
                        )
                    else:
                        emitter.emit(
                            EventType.TOOL_FAILED,
                            task_id=task_id,
                            tool=tool,
                            duration_ms=duration_ms,
                            success=False,
                            error_type=error_type,
                        )
                else:
                    emitter.emit(
                        event_type,
                        task_id=task_id,
                        tool=tool,
                        provider=provider,
                        model=model,
                        duration_ms=duration_ms,
                        success=success,
                        error_type=error_type,
                    )
        return wrapper
    return decorator