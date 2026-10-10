"""Monitoring store using SQLite for persistent event storage."""

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.monitoring.events import MonitorEvent, EventType


class MonitoringStore:
    """SQLite-based monitoring event store with thread-safe access."""

    def __init__(self, db_path: Optional[str] = None, max_metadata_size: int = 10000):
        if db_path is None:
            db_path = str(Path.home() / ".ai_agent" / "monitoring.db")

        self.db_path = db_path
        self.max_metadata_size = max_metadata_size
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    session_id TEXT,
                    provider TEXT,
                    model TEXT,
                    tool TEXT,
                    duration_ms REAL,
                    success INTEGER,
                    error_type TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_task_id
                ON events(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_session_id
                ON events(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_event_type
                ON events(event_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_provider
                ON events(provider)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_tool
                ON events(tool)
            """)

    @contextmanager
    def _connection(self):
        """Thread-safe database connection."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _truncate_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Truncate metadata if it exceeds max size."""
        metadata_json = json.dumps(metadata, default=str)
        if len(metadata_json) > self.max_metadata_size:
            # Truncate large string values
            truncated = {}
            for k, v in metadata.items():
                if isinstance(v, str) and len(v) > 1000:
                    truncated[k] = v[:1000] + "... [TRUNCATED]"
                else:
                    truncated[k] = v
            return truncated
        return metadata

    def insert_event(self, event: MonitorEvent) -> None:
        """Insert a monitoring event."""
        metadata = self._truncate_metadata(event.metadata)
        with self._lock:
            with self._connection() as conn:
                conn.execute("""
                    INSERT INTO events (
                        event_id, timestamp, event_type, task_id, session_id,
                        provider, model, tool, duration_ms, success, error_type, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.event_id,
                    event.timestamp,
                    event.event_type,
                    event.task_id,
                    event.session_id,
                    event.provider,
                    event.model,
                    event.tool,
                    event.duration_ms,
                    1 if event.success else 0 if event.success is not None else None,
                    event.error_type,
                    json.dumps(metadata, default=str)
                ))

    def query_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        provider: Optional[str] = None,
        tool: Optional[str] = None,
        success: Optional[bool] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[MonitorEvent]:
        """Query events with optional filters."""
        conditions = []
        params = []

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat() + "Z")

        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat() + "Z")

        if event_type:
            conditions.append("event_type = ?")
            # Handle both string and EventType enum
            if hasattr(event_type, 'value'):
                params.append(event_type.value)
            else:
                params.append(event_type)

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)

        if provider:
            conditions.append("provider = ?")
            params.append(provider)

        if tool:
            conditions.append("tool = ?")
            params.append(tool)

        if success is not None:
            conditions.append("success = ?")
            params.append(1 if success else 0)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(f"""
                    SELECT * FROM events
                    {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                events = []
                for row in cursor:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    events.append(MonitorEvent(
                        event_id=row["event_id"],
                        timestamp=row["timestamp"],
                        event_type=row["event_type"],
                        task_id=row["task_id"],
                        session_id=row["session_id"],
                        provider=row["provider"],
                        model=row["model"],
                        tool=row["tool"],
                        duration_ms=row["duration_ms"],
                        success=bool(row["success"]) if row["success"] is not None else None,
                        error_type=row["error_type"],
                        metadata=metadata
                    ))
                return events

    def get_recent_events(self, limit: int = 100) -> list[MonitorEvent]:
        """Get most recent events."""
        return self.query_events(limit=limit)

    def get_events_by_task(self, task_id: str) -> list[MonitorEvent]:
        """Get all events for a specific task."""
        return self.query_events(task_id=task_id, limit=10000)

    # Aggregation methods

    def get_provider_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict[str, dict[str, Any]]:
        """Get aggregated provider statistics."""
        base_conditions = ["event_type IN (?, ?, ?)"]
        base_params = [
            EventType.PROVIDER_REQUEST.value,
            EventType.PROVIDER_SUCCESS.value,
            EventType.PROVIDER_FAILURE.value,
        ]

        if start_time:
            base_conditions.append("timestamp >= ?")
            base_params.append(start_time.isoformat() + "Z")
        if end_time:
            base_conditions.append("timestamp <= ?")
            base_params.append(end_time.isoformat() + "Z")

        where_clause = "WHERE " + " AND ".join(base_conditions)

        with self._lock:
            with self._connection() as conn:
                # Total requests by provider - only PROVIDER_REQUEST events
                request_conditions = ["event_type = ?"]
                request_params = [EventType.PROVIDER_REQUEST.value]
                if start_time:
                    request_conditions.append("timestamp >= ?")
                    request_params.append(start_time.isoformat() + "Z")
                if end_time:
                    request_conditions.append("timestamp <= ?")
                    request_params.append(end_time.isoformat() + "Z")
                where_request = "WHERE " + " AND ".join(request_conditions)

                cursor = conn.execute(f"""
                    SELECT provider, COUNT(*) as count
                    FROM events
                    {where_request}
                    GROUP BY provider
                """, request_params)
                requests = {row["provider"]: row["count"] for row in cursor if row["provider"]}

                # Successes by provider
                success_conditions = ["event_type = ?"]
                success_params = [EventType.PROVIDER_SUCCESS.value]
                if start_time:
                    success_conditions.append("timestamp >= ?")
                    success_params.append(start_time.isoformat() + "Z")
                if end_time:
                    success_conditions.append("timestamp <= ?")
                    success_params.append(end_time.isoformat() + "Z")
                where_success = "WHERE " + " AND ".join(success_conditions)

                cursor = conn.execute(f"""
                    SELECT provider, COUNT(*) as count
                    FROM events
                    {where_success}
                    GROUP BY provider
                """, success_params)
                successes = {row["provider"]: row["count"] for row in cursor if row["provider"]}

                # Failures by provider
                failure_conditions = ["event_type = ?"]
                failure_params = [EventType.PROVIDER_FAILURE.value]
                if start_time:
                    failure_conditions.append("timestamp >= ?")
                    failure_params.append(start_time.isoformat() + "Z")
                if end_time:
                    failure_conditions.append("timestamp <= ?")
                    failure_params.append(end_time.isoformat() + "Z")
                where_failure = "WHERE " + " AND ".join(failure_conditions)

                cursor = conn.execute(f"""
                    SELECT provider, COUNT(*) as count
                    FROM events
                    {where_failure}
                    GROUP BY provider
                """, failure_params)
                failures = {row["provider"]: row["count"] for row in cursor if row["provider"]}

                # Average latency - from success events only (successful requests)
                latency_conditions = ["event_type = ?"]
                latency_params = [EventType.PROVIDER_SUCCESS.value]
                if start_time:
                    latency_conditions.append("timestamp >= ?")
                    latency_params.append(start_time.isoformat() + "Z")
                if end_time:
                    latency_conditions.append("timestamp <= ?")
                    latency_params.append(end_time.isoformat() + "Z")
                where_latency = "WHERE " + " AND ".join(latency_conditions)

                cursor = conn.execute(f"""
                    SELECT provider, AVG(duration_ms) as avg_latency
                    FROM events
                    {where_latency} AND duration_ms IS NOT NULL
                    GROUP BY provider
                """, latency_params)
                latencies = {row["provider"]: row["avg_latency"] for row in cursor if row["provider"]}

                # Fallbacks
                fallback_conditions = ["event_type = ?"]
                fallback_params = [EventType.PROVIDER_FALLBACK.value]
                if start_time:
                    fallback_conditions.append("timestamp >= ?")
                    fallback_params.append(start_time.isoformat() + "Z")
                if end_time:
                    fallback_conditions.append("timestamp <= ?")
                    fallback_params.append(end_time.isoformat() + "Z")
                where_fallback = "WHERE " + " AND ".join(fallback_conditions)

                cursor = conn.execute(f"""
                    SELECT COUNT(*) as count FROM events {where_fallback}
                """, fallback_params)
                fallback_count = cursor.fetchone()["count"] or 0

                # Cooldowns
                cooldown_conditions = ["event_type = ?"]
                cooldown_params = [EventType.PROVIDER_COOLDOWN.value]
                if start_time:
                    cooldown_conditions.append("timestamp >= ?")
                    cooldown_params.append(start_time.isoformat() + "Z")
                if end_time:
                    cooldown_conditions.append("timestamp <= ?")
                    cooldown_params.append(end_time.isoformat() + "Z")
                where_cooldown = "WHERE " + " AND ".join(cooldown_conditions)

                cursor = conn.execute(f"""
                    SELECT COUNT(*) as count FROM events {where_cooldown}
                """, cooldown_params)
                cooldown_count = cursor.fetchone()["count"] or 0

                # Build result
                all_providers = set(requests.keys()) | set(successes.keys()) | set(failures.keys())
                result = {}
                for provider in all_providers:
                    req = requests.get(provider, 0)
                    succ = successes.get(provider, 0)
                    fail = failures.get(provider, 0)
                    result[provider] = {
                        "requests": req,
                        "successes": succ,
                        "failures": fail,
                        "success_rate": succ / req if req > 0 else 0.0,
                        "average_latency_ms": latencies.get(provider, 0.0),
                    }
                result["_fallback_count"] = fallback_count
                result["_cooldown_count"] = cooldown_count

                return result

    def get_tool_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict[str, dict[str, Any]]:
        """Get aggregated tool statistics."""
        with self._lock:
            with self._connection() as conn:
                # Invocations by tool - only TOOL_STARTED events
                inv_conditions = ["event_type = ?"]
                inv_params = [EventType.TOOL_STARTED.value]
                if start_time:
                    inv_conditions.append("timestamp >= ?")
                    inv_params.append(start_time.isoformat() + "Z")
                if end_time:
                    inv_conditions.append("timestamp <= ?")
                    inv_params.append(end_time.isoformat() + "Z")
                where_inv = "WHERE " + " AND ".join(inv_conditions)

                cursor = conn.execute(f"""
                    SELECT tool, COUNT(*) as count
                    FROM events
                    {where_inv}
                    GROUP BY tool
                """, inv_params)
                invocations = {row["tool"]: row["count"] for row in cursor if row["tool"]}

                # Successes
                success_conditions = ["event_type = ?"]
                success_params = [EventType.TOOL_COMPLETED.value]
                if start_time:
                    success_conditions.append("timestamp >= ?")
                    success_params.append(start_time.isoformat() + "Z")
                if end_time:
                    success_conditions.append("timestamp <= ?")
                    success_params.append(end_time.isoformat() + "Z")
                where_success = "WHERE " + " AND ".join(success_conditions)

                cursor = conn.execute(f"""
                    SELECT tool, COUNT(*) as count
                    FROM events
                    {where_success}
                    GROUP BY tool
                """, success_params)
                successes = {row["tool"]: row["count"] for row in cursor if row["tool"]}

                # Failures
                failure_conditions = ["event_type = ?"]
                failure_params = [EventType.TOOL_FAILED.value]
                if start_time:
                    failure_conditions.append("timestamp >= ?")
                    failure_params.append(start_time.isoformat() + "Z")
                if end_time:
                    failure_conditions.append("timestamp <= ?")
                    failure_params.append(end_time.isoformat() + "Z")
                where_failure = "WHERE " + " AND ".join(failure_conditions)

                cursor = conn.execute(f"""
                    SELECT tool, COUNT(*) as count
                    FROM events
                    {where_failure}
                    GROUP BY tool
                """, failure_params)
                failures = {row["tool"]: row["count"] for row in cursor if row["tool"]}

                # Average latency - from success and failure events (which have durations)
                latency_conditions = ["event_type IN (?, ?)"]
                latency_params = [EventType.TOOL_COMPLETED.value, EventType.TOOL_FAILED.value]
                if start_time:
                    latency_conditions.append("timestamp >= ?")
                    latency_params.append(start_time.isoformat() + "Z")
                if end_time:
                    latency_conditions.append("timestamp <= ?")
                    latency_params.append(end_time.isoformat() + "Z")
                where_latency = "WHERE " + " AND ".join(latency_conditions)

                cursor = conn.execute(f"""
                    SELECT tool, AVG(duration_ms) as avg_latency
                    FROM events
                    {where_latency} AND duration_ms IS NOT NULL
                    GROUP BY tool
                """, latency_params)
                latencies = {row["tool"]: row["avg_latency"] for row in cursor if row["tool"]}

                all_tools = set(invocations.keys()) | set(successes.keys()) | set(failures.keys())
                result = {}
                for tool in all_tools:
                    inv = invocations.get(tool, 0)
                    succ = successes.get(tool, 0)
                    fail = failures.get(tool, 0)
                    result[tool] = {
                        "invocations": inv,
                        "successes": succ,
                        "failures": fail,
                        "failure_rate": fail / inv if inv > 0 else 0.0,
                        "average_latency_ms": latencies.get(tool, 0.0),
                    }
                return result

    def get_permission_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get permission statistics."""
        conditions = ["event_type IN (?, ?, ?)"]
        params = [
            EventType.PERMISSION_REQUESTED.value,
            EventType.PERMISSION_GRANTED.value,
            EventType.PERMISSION_DENIED.value,
        ]

        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat() + "Z")
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat() + "Z")

        where_clause = "WHERE " + " AND ".join(conditions)

        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(f"""
                    SELECT event_type, COUNT(*) as count
                    FROM events
                    {where_clause}
                    GROUP BY event_type
                """, params)
                counts = {row["event_type"]: row["count"] for row in cursor}

                return {
                    "requested": counts.get(EventType.PERMISSION_REQUESTED.value, 0),
                    "granted": counts.get(EventType.PERMISSION_GRANTED.value, 0),
                    "denied": counts.get(EventType.PERMISSION_DENIED.value, 0),
                }

    def get_task_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get task-level statistics."""
        base_conditions = ["event_type IN (?, ?, ?)"]
        base_params = [
            EventType.TASK_STARTED.value,
            EventType.TASK_COMPLETED.value,
            EventType.TASK_FAILED.value,
        ]

        if start_time:
            base_conditions.append("timestamp >= ?")
            base_params.append(start_time.isoformat() + "Z")
        if end_time:
            base_conditions.append("timestamp <= ?")
            base_params.append(end_time.isoformat() + "Z")

        where_clause = "WHERE " + " AND ".join(base_conditions)

        with self._lock:
            with self._connection() as conn:
                # Task counts
                cursor = conn.execute(f"""
                    SELECT event_type, COUNT(*) as count
                    FROM events
                    {where_clause}
                    GROUP BY event_type
                """, base_params)
                counts = {row["event_type"]: row["count"] for row in cursor}

                # Average duration for completed tasks
                cursor = conn.execute(f"""
                    SELECT AVG(duration_ms) as avg_duration
                    FROM events
                    WHERE event_type = ? AND duration_ms IS NOT NULL
                    AND (? IS NULL OR timestamp >= ?)
                    AND (? IS NULL OR timestamp <= ?)
                """, [
                    EventType.TASK_COMPLETED.value,
                    start_time.isoformat() + "Z" if start_time else None,
                    start_time.isoformat() + "Z" if start_time else None,
                    end_time.isoformat() + "Z" if end_time else None,
                    end_time.isoformat() + "Z" if end_time else None,
                ])
                avg_duration = cursor.fetchone()["avg_duration"] or 0.0

                # Average iterations (loop iterations per task)
                iter_params = [EventType.AGENT_LOOP_ITERATION.value]
                iter_conditions = ["event_type = ?", "task_id IS NOT NULL"]
                if start_time:
                    iter_conditions.append("timestamp >= ?")
                    iter_params.append(start_time.isoformat() + "Z")
                if end_time:
                    iter_conditions.append("timestamp <= ?")
                    iter_params.append(end_time.isoformat() + "Z")
                iter_where = "WHERE " + " AND ".join(iter_conditions)
                
                cursor = conn.execute(f"""
                    SELECT AVG(iteration_count) as avg_iterations
                    FROM (
                        SELECT task_id, COUNT(*) as iteration_count
                        FROM events
                        {iter_where}
                        GROUP BY task_id
                    )
                """, iter_params)
                avg_iterations = cursor.fetchone()["avg_iterations"] or 0.0

                # Local model fallbacks - separate query
                fallback_conditions = base_conditions + ["event_type = ?"]
                fallback_params = base_params + [EventType.LOCAL_MODEL_ACTIVATED.value]
                where_fallback = "WHERE " + " AND ".join(fallback_conditions)
                cursor = conn.execute(f"""
                    SELECT COUNT(*) as count FROM events {where_fallback}
                """, fallback_params)
                local_fallback_count = cursor.fetchone()["count"] or 0

                started = counts.get(EventType.TASK_STARTED.value, 0)
                completed = counts.get(EventType.TASK_COMPLETED.value, 0)
                failed = counts.get(EventType.TASK_FAILED.value, 0)

                return {
                    "total_started": started,
                    "completed": completed,
                    "failed": failed,
                    "success_rate": completed / started if started > 0 else 0.0,
                    "average_duration_ms": avg_duration,
                    "average_iterations": avg_iterations,
                    "local_model_fallbacks": local_fallback_count,
                }

    def get_overview(self) -> dict[str, Any]:
        """Get overview statistics for dashboard."""
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        with self._lock:
            with self._connection() as conn:
                # Total events
                cursor = conn.execute("SELECT COUNT(*) as count FROM events")
                total_events = cursor.fetchone()["count"]

                # Events in last hour
                cursor = conn.execute("SELECT COUNT(*) as count FROM events WHERE timestamp >= ?", [hour_ago.isoformat() + "Z"])
                events_last_hour = cursor.fetchone()["count"]

                # Unique tasks
                cursor = conn.execute("SELECT COUNT(DISTINCT task_id) as count FROM events WHERE task_id IS NOT NULL")
                unique_tasks = cursor.fetchone()["count"]

                # Unique sessions
                cursor = conn.execute("SELECT COUNT(DISTINCT session_id) as count FROM events WHERE session_id IS NOT NULL")
                unique_sessions = cursor.fetchone()["count"]

        provider_stats = self.get_provider_stats(start_time=day_ago)
        tool_stats = self.get_tool_stats(start_time=day_ago)
        permission_stats = self.get_permission_stats(start_time=day_ago)
        task_stats = self.get_task_stats(start_time=day_ago)

        # Provider health summary
        provider_health = {}
        for provider, stats in provider_stats.items():
            if provider.startswith("_"):
                continue
            sr = stats.get("success_rate", 0)
            if sr >= 0.9:
                health = "healthy"
            elif sr >= 0.5:
                health = "degraded"
            else:
                health = "unavailable"
            provider_health[provider] = {
                "success_rate": sr,
                "requests": stats.get("requests", 0),
                "status": health,
            }

        return {
            "total_events": total_events,
            "events_last_hour": events_last_hour,
            "unique_tasks": unique_tasks,
            "unique_sessions": unique_sessions,
            "task_success_rate": task_stats.get("success_rate", 0.0),
            "average_task_duration_ms": task_stats.get("average_duration_ms", 0.0),
            "provider_health": provider_health,
            "active_provider": max(provider_health, key=lambda p: (provider_health[p]["requests"], provider_health[p]["success_rate"])) if provider_health else None,
            "permission_approval_rate": (
                permission_stats.get("granted", 0) /
                max(1, permission_stats.get("requested", 1))
            ),
        }

    def cleanup_old_events(self, older_than: datetime) -> int:
        """Delete events older than the specified timestamp."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute("""
                    DELETE FROM events WHERE timestamp < ?
                """, [older_than.isoformat() + "Z"])
                return cursor.rowcount

    def cleanup_old_events_days(self, days: int) -> int:
        """Delete events older than N days."""
        older_than = datetime.utcnow() - timedelta(days=days)
        return self.cleanup_old_events(older_than)

    def get_event_count(self) -> int:
        """Get total event count."""
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM events")
                return cursor.fetchone()["count"]

    def close(self) -> None:
        """Close any open connections (no-op for connection-per-operation)."""
        pass


# Global store instance (lazy initialization)
_store: Optional[MonitoringStore] = None
_store_lock = threading.Lock()


def get_store() -> MonitoringStore:
    """Get or create the global monitoring store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = MonitoringStore()
    return _store


def set_store(store: MonitoringStore) -> None:
    """Set the global monitoring store (for testing)."""
    global _store
    _store = store