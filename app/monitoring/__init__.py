"""Monitoring package for AI Agent Framework.

Provides observability for agent activity including:
- Structured event system
- Persistent SQLite store
- Metrics aggregation
- Local web dashboard
"""

from app.monitoring.events import (
    MonitorEvent,
    EventType,
    create_event,
    sanitize_metadata,
    SENSITIVE_KEYS,
)
from app.monitoring.store import MonitoringStore, get_store, set_store
from app.monitoring.emitter import (
    EventEmitter,
    get_emitter,
    set_emitter,
    configure_monitoring,
    # Convenience functions
    emit_task_started,
    emit_task_completed,
    emit_task_failed,
    emit_provider_request,
    emit_provider_success,
    emit_provider_failure,
    emit_provider_fallback,
    emit_tool_started,
    emit_tool_completed,
    emit_tool_failed,
    emit_permission_requested,
    emit_permission_granted,
    emit_permission_denied,
    emit_memory_write,
    emit_attempt_created,
    emit_attempt_comparison,
    emit_local_model_activated,
    emit_agent_loop_iteration,
)
from app.monitoring.integration import (
    instrument_agent,
    create_monitored_agent,
    configure_agent_monitoring,
    configure_planner_monitoring,
    configure_omniroute_monitoring,
    configure_tool_executor_monitoring,
    configure_permission_manager_monitoring,
    configure_enhanced_memory_monitoring,
    configure_agent_loop_monitoring,
)
# Dashboard is optional; only import if Flask is available
try:
    from app.monitoring.dashboard import (
        create_dashboard_app,
        run_dashboard,
    )
    _dashboard_available = True
except ImportError:
    # Flask is not available, dashboard is disabled
    create_dashboard_app = None
    run_dashboard = None
    _dashboard_available = False

__all__ = [
    # Events
    "MonitorEvent",
    "EventType",
    "create_event",
    "sanitize_metadata",
    "SENSITIVE_KEYS",
    # Store
    "MonitoringStore",
    "get_store",
    "set_store",
    # Emitter
    "EventEmitter",
    "get_emitter",
    "set_emitter",
    "configure_monitoring",
    "emit_task_started",
    emit_task_completed,
    emit_task_failed,
    emit_provider_request,
    emit_provider_success,
    emit_provider_failure,
    emit_provider_fallback,
    emit_tool_started,
    emit_tool_completed,
    emit_tool_failed,
    emit_permission_requested,
    emit_permission_granted,
    emit_permission_denied,
    emit_memory_write,
    emit_attempt_created,
    emit_attempt_comparison,
    emit_local_model_activated,
    emit_agent_loop_iteration,
    # Integration
    "instrument_agent",
    "create_monitored_agent",
    "configure_agent_monitoring",
    configure_planner_monitoring,
    configure_omniroute_monitoring,
    configure_tool_executor_monitoring,
    configure_permission_manager_monitoring,
    configure_enhanced_memory_monitoring,
    configure_agent_loop_monitoring,
]
if _dashboard_available:
    __all__ += ["create_dashboard_app", "run_dashboard"]