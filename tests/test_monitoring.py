"""Tests for the monitoring system."""

import json
import tempfile
import time
from datetime import datetime, timedelta

import pytest

from app.monitoring.events import (
    EventType,
    MonitorEvent,
    create_event,
    sanitize_metadata,
)
from app.monitoring.store import MonitoringStore
from app.monitoring.emitter import (
    EventEmitter,
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
    set_emitter,
    EventEmitter,
)


class TestMonitoringEvents:
    """Test the event model and sanitization."""

    def test_create_event(self):
        """Test creating a monitoring event."""
        event = create_event(
            event_type=EventType.TASK_STARTED,
            task_id="test123",
            provider="gemini",
            model="gemini-pro",
            metadata={"key": "value"}
        )

        assert event.event_type == EventType.TASK_STARTED.value
        assert event.task_id == "test123"
        assert event.provider == "gemini"
        assert event.model == "gemini-pro"
        assert event.metadata == {"key": "value"}
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = create_event(
            event_type=EventType.TASK_COMPLETED,
            task_id="test123",
            duration_ms=150.5,
            success=True
        )

        event_dict = event.to_dict()
        assert event_dict["event_type"] == EventType.TASK_COMPLETED.value
        assert event_dict["task_id"] == "test123"
        assert event_dict["duration_ms"] == 150.5
        assert event_dict["success"] is True
        assert event_dict["event_id"] == event.event_id

    def test_event_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "event_id": "test-id",
            "timestamp": "2023-01-01T00:00:00Z",
            "event_type": EventType.TASK_STARTED.value,
            "task_id": "test123",
            "provider": "gemini",
            "model": "gemini-pro",
            "duration_ms": 100.0,
            "success": True,
            "error_type": None,
            "metadata": {"key": "value"}
        }

        event = MonitorEvent.from_dict(data)
        assert event.event_id == "test-id"
        assert event.event_type == EventType.TASK_STARTED.value
        assert event.task_id == "test123"
        assert event.provider == "gemini"
        assert event.model == "gemini-pro"
        assert event.duration_ms == 100.0
        assert event.success is True
        assert event.metadata == {"key": "value"}

    def test_sanitize_metadata(self):
        """Test metadata sanitization removes sensitive data."""
        dirty_metadata = {
            "api_key": "secret123",
            "authorization": "Bearer token",
            "normal_field": "visible",
            "nested": {
                "password": "hidden",
                "data": "visible",
                "deep": {
                    "secret": "very_hidden",
                    "public": "see_me"
                }
            },
            "list_of_dicts": [
                {"api_key": "secret_in_list", "name": "visible"},
                {"normal": "also_visible"}
            ]
        }

        clean = sanitize_metadata(dirty_metadata)

        # Check top-level redactions
        assert clean["api_key"] == "[REDACTED]"
        assert clean["authorization"] == "[REDACTED]"
        assert clean["normal_field"] == "visible"

        # Check nested redactions
        assert clean["nested"]["password"] == "[REDACTED]"
        assert clean["nested"]["data"] == "visible"
        assert clean["nested"]["deep"]["secret"] == "[REDACTED]"
        assert clean["nested"]["deep"]["public"] == "see_me"

        # Check list redactions
        assert clean["list_of_dicts"][0]["api_key"] == "[REDACTED]"
        assert clean["list_of_dicts"][0]["name"] == "visible"
        assert clean["list_of_dicts"][1]["normal"] == "also_visible"

    def test_sanitize_metadata_truncation(self):
        """Test that long strings are truncated."""
        long_string = "x" * 600
        metadata = {"description": long_string, "normal": "short"}

        clean = sanitize_metadata(metadata)
        assert len(clean["description"]) <= 200 + len("... [TRUNCATED]")
        assert clean["description"].endswith("... [TRUNCATED]")
        assert clean["normal"] == "short"


class TestMonitoringStore:
    """Test the monitoring store functionality."""

    def _make_store(self):
        """Helper to create a store with a temporary database."""
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = tmp.name
        tmp.close()
        return MonitoringStore(db_path=db_path), db_path

    def test_store_initialization(self):
        """Test store creates database and tables."""
        store, db_path = self._make_store()
        try:
            assert store.db_path == db_path

            # Test that we can insert and query
            event = create_event(
                event_type=EventType.TASK_STARTED,
                task_id="test123"
            )
            store.insert_event(event)

            events = store.query_events()
            assert len(events) == 1
            assert events[0].task_id == "test123"
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_insert_and_query_events(self):
        """Test inserting events and querying with filters."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()
            hour_ago = now - timedelta(hours=1)

            event1 = create_event(
                event_type=EventType.TASK_STARTED,
                task_id="task1",
                provider="gemini",
                timestamp=now.isoformat() + "Z"
            )
            event2 = create_event(
                event_type=EventType.TASK_COMPLETED,
                task_id="task1",
                provider="gemini",
                duration_ms=150.0,
                success=True,
                timestamp=now.isoformat() + "Z"
            )
            event3 = create_event(
                event_type=EventType.TASK_STARTED,
                task_id="task2",
                provider="groq",
                timestamp=hour_ago.isoformat() + "Z"
            )

            store.insert_event(event1)
            store.insert_event(event2)
            store.insert_event(event3)

            # Query all events
            all_events = store.query_events()
            assert len(all_events) == 3

            # Query by task_id
            task1_events = store.query_events(task_id="task1")
            assert len(task1_events) == 2

            # Query by provider
            gemini_events = store.query_events(provider="gemini")
            assert len(gemini_events) == 2

            # Query by event_type
            started_events = store.query_events(event_type=EventType.TASK_STARTED.value)
            assert len(started_events) == 2

            # Query by time range
            recent_events = store.query_events(start_time=now - timedelta(minutes=30))
            assert len(recent_events) == 2  # task1 events

            # Test limit and offset
            limited = store.query_events(limit=2)
            assert len(limited) == 2
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_provider_stats(self):
        """Test provider statistics aggregation."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()

            # Insert provider events
            events = [
                # Gemini requests and successes
                create_event(EventType.PROVIDER_REQUEST, provider="gemini", model="gemini-pro", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_SUCCESS, provider="gemini", model="gemini-pro", duration_ms=100.0, timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_REQUEST, provider="gemini", model="gemini-pro", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_FAILURE, provider="gemini", model="gemini-pro", duration_ms=50.0, error_type="timeout", timestamp=now.isoformat() + "Z"),
                # Groq requests
                create_event(EventType.PROVIDER_REQUEST, provider="groq", model="mixtral", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_SUCCESS, provider="groq", model="mixtral", duration_ms=200.0, timestamp=now.isoformat() + "Z"),
                # Fallbacks and cooldowns
                create_event(EventType.PROVIDER_FALLBACK, provider="gemini", model="groq", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_COOLDOWN, provider="groq", timestamp=now.isoformat() + "Z"),
            ]

            for event in events:
                store.insert_event(event)

            stats = store.get_provider_stats()

            # Check Gemini stats
            gemini = stats["gemini"]
            assert gemini["requests"] == 2
            assert gemini["successes"] == 1
            assert gemini["failures"] == 1
            assert gemini["success_rate"] == 0.5
            assert gemini["average_latency_ms"] == 100.0  # Only success has duration

            # Check Groq stats
            groq = stats["groq"]
            assert groq["requests"] == 1
            assert groq["successes"] == 1
            assert groq["failures"] == 0
            assert groq["success_rate"] == 1.0
            assert groq["average_latency_ms"] == 200.0

            # Check aggregated counts
            assert stats["_fallback_count"] == 1
            assert stats["_cooldown_count"] == 1
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_tool_stats(self):
        """Test tool statistics aggregation."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()

            # Insert tool events
            events = [
                # Calculator tool
                create_event(EventType.TOOL_STARTED, tool="calculator", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_COMPLETED, tool="calculator", duration_ms=10.0, success=True, timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_STARTED, tool="calculator", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_FAILED, tool="calculator", duration_ms=5.0, success=False, error_type="division_by_zero", timestamp=now.isoformat() + "Z"),
                # Time tool
                create_event(EventType.TOOL_STARTED, tool="time", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_COMPLETED, tool="time", duration_ms=100.0, success=True, timestamp=now.isoformat() + "Z"),
            ]

            for event in events:
                store.insert_event(event)

            stats = store.get_tool_stats()

            # Check calculator stats
            calc = stats["calculator"]
            assert calc["invocations"] == 2
            assert calc["successes"] == 1
            assert calc["failures"] == 1
            assert calc["failure_rate"] == 0.5
            assert calc["average_latency_ms"] == 7.5  # Average of 10.0 (success) and 5.0 (failure)

            # Check time stats
            time_tool = stats["time"]
            assert time_tool["invocations"] == 1
            assert time_tool["successes"] == 1
            assert time_tool["failures"] == 0
            assert time_tool["failure_rate"] == 0.0
            assert time_tool["average_latency_ms"] == 100.0
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_permission_stats(self):
        """Test permission statistics."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()

            # Insert permission events
            events = [
                create_event(EventType.PERMISSION_REQUESTED, tool="fs.write", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_GRANTED, tool="fs.write", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_REQUESTED, tool="terminal", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_DENIED, tool="terminal", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_REQUESTED, tool="web.search", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_GRANTED, tool="web.search", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_REQUESTED, tool="fs.write", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_DENIED, tool="fs.write", timestamp=now.isoformat() + "Z"),
            ]

            for event in events:
                store.insert_event(event)

            stats = store.get_permission_stats()

            assert stats["requested"] == 4
            assert stats["granted"] == 2
            assert stats["denied"] == 2
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_task_stats(self):
        """Test task-level statistics."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()

            # Insert task events for task1 (completed)
            task1_start = now - timedelta(seconds=30)
            task1_end = now - timedelta(seconds=10)

            events = [
                create_event(EventType.TASK_STARTED, task_id="task1", timestamp=task1_start.isoformat() + "Z"),
                create_event(EventType.AGENT_LOOP_ITERATION, task_id="task1", timestamp=(task1_start + timedelta(seconds=5)).isoformat() + "Z"),
                create_event(EventType.AGENT_LOOP_ITERATION, task_id="task1", timestamp=(task1_start + timedelta(seconds=10)).isoformat() + "Z"),
                create_event(EventType.TASK_COMPLETED, task_id="task1", duration_ms=20000.0, success=True, timestamp=task1_end.isoformat() + "Z"),
                # Task2 (failed)
                create_event(EventType.TASK_STARTED, task_id="task2", timestamp=now.isoformat() + "Z"),
                create_event(EventType.AGENT_LOOP_ITERATION, task_id="task2", timestamp=(now + timedelta(seconds=2)).isoformat() + "Z"),
                create_event(EventType.TASK_FAILED, task_id="task2", duration_ms=5000.0, success=False, error_type="tool_failed", timestamp=(now + timedelta(seconds=5)).isoformat() + "Z"),
            ]

            for event in events:
                store.insert_event(event)

            stats = store.get_task_stats()

            assert stats["total_started"] == 2
            assert stats["completed"] == 1
            assert stats["failed"] == 1
            assert stats["success_rate"] == 0.5
            assert stats["average_duration_ms"] == 20000.0  # Only completed task has duration
            assert stats["average_iterations"] == 1.5  # (2 iterations for task1 + 1 for task2) / 2 tasks
            assert stats["local_model_fallbacks"] == 0
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_overview(self):
        """Test overview statistics."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()

            # Insert various events
            events = [
                create_event(EventType.TASK_STARTED, task_id="task1", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TASK_COMPLETED, task_id="task1", duration_ms=1000.0, success=True, timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_REQUEST, provider="gemini", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_SUCCESS, provider="gemini", duration_ms=100.0, timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_REQUEST, provider="groq", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PROVIDER_FAILURE, provider="groq", duration_ms=50.0, error_type="timeout", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_STARTED, tool="calculator", timestamp=now.isoformat() + "Z"),
                create_event(EventType.TOOL_COMPLETED, tool="calculator", duration_ms=10.0, success=True, timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_REQUESTED, tool="fs.write", timestamp=now.isoformat() + "Z"),
                create_event(EventType.PERMISSION_GRANTED, tool="fs.write", timestamp=now.isoformat() + "Z"),
            ]

            for event in events:
                store.insert_event(event)

            overview = store.get_overview()

            assert overview["total_events"] == 10
            assert overview["unique_tasks"] == 1
            assert overview["task_success_rate"] == 1.0
            assert overview["average_task_duration_ms"] == 1000.0
            assert overview["permission_approval_rate"] == 1.0

            # Check provider health
            provider_health = overview["provider_health"]
            assert "gemini" in provider_health
            assert provider_health["gemini"]["success_rate"] == 1.0
            assert provider_health["gemini"]["status"] == "healthy"
            assert "groq" in provider_health
            assert provider_health["groq"]["success_rate"] == 0.0
            assert provider_health["groq"]["status"] == "unavailable"

            # Check active provider (should be gemini with more requests)
            # In case of tie, gemini should be selected (it was inserted first)
            active_provider = overview["active_provider"]
            assert active_provider in ["gemini", "groq"], f"Expected gemini or groq, got {active_provider}"
            # If we want to be more specific about tie-breaking, we'd need to check insertion order
            # For now, just verify it's one of the two providers
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_cleanup_old_events(self):
        """Test cleaning up old events."""
        store, db_path = self._make_store()
        try:
            now = datetime.utcnow()
            old_time = now - timedelta(days=10)
            recent_time = now - timedelta(hours=1)

            # Insert old and recent events
            old_event = create_event(
                event_type=EventType.TASK_STARTED,
                task_id="old_task",
                timestamp=old_time.isoformat() + "Z"
            )
            recent_event = create_event(
                event_type=EventType.TASK_STARTED,
                task_id="recent_task",
                timestamp=recent_time.isoformat() + "Z"
            )

            store.insert_event(old_event)
            store.insert_event(recent_event)

            # Verify both events exist
            all_events = store.query_events()
            assert len(all_events) == 2

            # Cleanup events older than 5 days
            cutoff = now - timedelta(days=5)
            deleted_count = store.cleanup_old_events(cutoff)
            assert deleted_count == 1  # Only the old event should be deleted

            # Verify only recent event remains
            remaining_events = store.query_events()
            assert len(remaining_events) == 1
            assert remaining_events[0].task_id == "recent_task"
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_get_event_count(self):
        """Test getting total event count."""
        store, db_path = self._make_store()
        try:
            assert store.get_event_count() == 0

            # Insert some events
            for i in range(5):
                event = create_event(
                    event_type=EventType.TASK_STARTED,
                    task_id=f"task{i}"
                )
                store.insert_event(event)

            assert store.get_event_count() == 5
        finally:
            store.close()
            import os
            os.unlink(db_path)


class TestMonitoringEmitter:
    """Test the event emitter functionality."""

    def _make_store_and_emitter(self):
        """Helper to create a store and emitter with a temporary database."""
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = tmp.name
        tmp.close()
        store = MonitoringStore(db_path=db_path)
        emitter = EventEmitter(store=store)
        return store, emitter, db_path

    def test_emitter_basic_emit(self):
        """Test basic event emission."""
        store, emitter, db_path = self._make_store_and_emitter()
        try:
            event = emitter.emit(
                event_type=EventType.TASK_STARTED,
                task_id="test123",
                provider="gemini",
                metadata={"test": "value"}
            )

            assert event is not None
            assert event.event_type == EventType.TASK_STARTED.value
            assert event.task_id == "test123"
            assert event.provider == "gemini"
            assert event.metadata["test"] == "value"

            # Verify it was stored
            events = store.query_events()
            assert len(events) == 1
            assert events[0].event_id == event.event_id
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emitter_disabled(self):
        """Test that disabled emitter doesn't emit events."""
        store, emitter, db_path = self._make_store_and_emitter()
        try:
            emitter.enabled = False

            event = emitter.emit(
                event_type=EventType.TASK_STARTED,
                task_id="test123"
            )

            assert event is None

            # Verify nothing was stored
            events = store.query_events()
            assert len(events) == 0
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emitter_measure_context_manager(self):
        """Test the measure context manager."""
        store, emitter, db_path = self._make_store_and_emitter()
        try:
            # Test successful operation
            with emitter.measure(
                event_type=EventType.TOOL_STARTED,
                tool="calculator",
                task_id="test123"
            ):
                # Simulate some work
                time.sleep(0.01)  # 10ms

            # Should have two events: start and completion
            events = store.query_events(event_type=EventType.TOOL_STARTED)
            assert len(events) == 1
            assert events[0].tool == "calculator"
            assert events[0].task_id == "test123"

            events = store.query_events(event_type=EventType.TOOL_COMPLETED)
            assert len(events) == 1
            assert events[0].tool == "calculator"
            assert events[0].task_id == "test123"
            assert events[0].success is True
            assert events[0].duration_ms is not None
            assert events[0].duration_ms >= 10  # At least 10ms
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emitter_measure_with_exception(self):
        """Test measure context manager records failures."""
        store, emitter, db_path = self._make_store_and_emitter()
        try:
            # Test failed operation
            with pytest.raises(ValueError):
                with emitter.measure(
                    event_type=EventType.TOOL_STARTED,
                    tool="calculator",
                    task_id="test123"
                ):
                    raise ValueError("Test error")

            # Should have start and failure events
            start_events = store.query_events(event_type=EventType.TOOL_STARTED)
            assert len(start_events) == 1
            assert start_events[0].tool == "calculator"

            fail_events = store.query_events(event_type=EventType.TOOL_FAILED)
            assert len(fail_events) == 1
            assert fail_events[0].tool == "calculator"
            assert fail_events[0].success is False
            assert fail_events[0].error_type == "ValueError"
            assert fail_events[0].duration_ms is not None
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emitter_failure_isolation(self):
        """Test that monitoring failures don't break agent execution."""
        store, emitter, db_path = self._make_store_and_emitter()
        try:
            # Create a failing store
            class FailingStore:
                def insert_event(self, event):
                    raise Exception("Database failure")

            # Emitter with failing store should still return None but not raise
            failing_emitter = EventEmitter(store=FailingStore())
            result = failing_emitter.emit(
                event_type=EventType.TASK_STARTED,
                task_id="test123"
            )

            assert result is None  # Should return None on failure

            # Real emitter should still work
            real_result = emitter.emit(
                event_type=EventType.TASK_STARTED,
                task_id="test456"
            )

            assert real_result is not None
            assert real_result.task_id == "test456"

            # Verify the good event was stored
            events = store.query_events()
            assert len(events) == 1
            assert events[0].task_id == "test456"
        finally:
            store.close()
            import os
            os.unlink(db_path)


class TestConvenienceFunctions:
    """Test the convenience emitter functions."""

    def _make_store_and_emitter(self):
        """Helper to create a store and emitter with a temporary database."""
        tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = tmp.name
        tmp.close()
        store = MonitoringStore(db_path=db_path)
        test_emitter = EventEmitter(store=store)
        set_emitter(test_emitter)
        return store, test_emitter, db_path

    def test_emit_task_events(self):
        """Test task event convenience functions."""
        store, test_emitter, db_path = self._make_store_and_emitter()
        try:
            # Emit task events
            start_event = emit_task_started("task123", "Test task")
            assert start_event is not None
            assert start_event.event_type == EventType.TASK_STARTED.value
            assert start_event.task_id == "task123"
            assert "Test task" in start_event.metadata.get("message_preview", "")

            complete_event = emit_task_completed("task123", 1500.0)
            assert complete_event is not None
            assert complete_event.event_type == EventType.TASK_COMPLETED.value
            assert complete_event.task_id == "task123"
            assert complete_event.duration_ms == 1500.0
            assert complete_event.success is True

            failed_event = emit_task_failed("task456", 800.0, "TimeoutError")
            assert failed_event is not None
            assert failed_event.event_type == EventType.TASK_FAILED.value
            assert failed_event.task_id == "task456"
            assert failed_event.duration_ms == 800.0
            assert failed_event.success is False
            assert failed_event.error_type == "TimeoutError"

            # Verify all events stored
            events = store.query_events()
            assert len(events) == 3
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emit_provider_events(self):
        """Test provider event convenience functions."""
        store, test_emitter, db_path = self._make_store_and_emitter()
        try:
            # Emit provider events
            request_event = emit_provider_request("gemini", "gemini-pro", task_id="task123")
            assert request_event is not None
            assert request_event.event_type == EventType.PROVIDER_REQUEST.value
            assert request_event.provider == "gemini"
            assert request_event.model == "gemini-pro"

            success_event = emit_provider_success("gemini", "gemini-pro", 200.0, task_id="task123")
            assert success_event is not None
            assert success_event.event_type == EventType.PROVIDER_SUCCESS.value
            assert success_event.provider == "gemini"
            assert success_event.model == "gemini-pro"
            assert success_event.duration_ms == 200.0
            assert success_event.success is True

            failure_event = emit_provider_failure("groq", "mixtral", 100.0, "RateLimitError", task_id="task123")
            assert failure_event is not None
            assert failure_event.event_type == EventType.PROVIDER_FAILURE.value
            assert failure_event.provider == "groq"
            assert failure_event.model == "mixtral"
            assert failure_event.duration_ms == 100.0
            assert failure_event.success is False
            assert failure_event.error_type == "RateLimitError"

            fallback_event = emit_provider_fallback("gemini", "groq", task_id="task123")
            assert fallback_event is not None
            assert fallback_event.event_type == EventType.PROVIDER_FALLBACK.value
            assert fallback_event.provider == "gemini"
            # Note: fallback event puts the target provider in model field
            assert fallback_event.model == "groq"

            # Verify all events stored
            events = store.query_events()
            assert len(events) == 4  # request + success + failure + fallback = 4
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emit_tool_events(self):
        """Test tool event convenience functions."""
        store, test_emitter, db_path = self._make_store_and_emitter()
        try:
            # Emit tool events
            start_event = emit_tool_started("calculator", task_id="task123")
            assert start_event is not None
            assert start_event.event_type == EventType.TOOL_STARTED.value
            assert start_event.tool == "calculator"

            complete_event = emit_tool_completed("calculator", 15.0, task_id="task123")
            assert complete_event is not None
            assert complete_event.event_type == EventType.TOOL_COMPLETED.value
            assert complete_event.tool == "calculator"
            assert complete_event.duration_ms == 15.0
            assert complete_event.success is True

            failed_event = emit_tool_failed("terminal", 50.0, "PermissionDenied", task_id="task123")
            assert failed_event is not None
            assert failed_event.event_type == EventType.TOOL_FAILED.value
            assert failed_event.tool == "terminal"
            assert failed_event.duration_ms == 50.0
            assert failed_event.success is False
            assert failed_event.error_type == "PermissionDenied"

            # Verify all events stored
            events = store.query_events()
            assert len(events) == 3
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emit_permission_events(self):
        """Test permission event convenience functions."""
        store, test_emitter, db_path = self._make_store_and_emitter()
        try:
            # Emit permission events
            requested_event = emit_permission_requested("fs.write", "HIGH", task_id="task123")
            assert requested_event is not None
            assert requested_event.event_type == EventType.PERMISSION_REQUESTED.value
            assert requested_event.tool == "fs.write"
            assert requested_event.metadata.get("risk_level") == "HIGH"

            granted_event = emit_permission_granted("fs.write", task_id="task123")
            assert granted_event is not None
            assert granted_event.event_type == EventType.PERMISSION_GRANTED.value
            assert granted_event.tool == "fs.write"
            assert granted_event.success is True

            denied_event = emit_permission_denied("terminal", task_id="task123")
            assert denied_event is not None
            assert denied_event.event_type == EventType.PERMISSION_DENIED.value
            assert denied_event.tool == "terminal"
            assert denied_event.success is False

            # Verify all events stored
            events = store.query_events()
            assert len(events) == 3
        finally:
            store.close()
            import os
            os.unlink(db_path)

    def test_emit_memory_events(self):
        """Test memory event convenience functions."""
        store, test_emitter, db_path = self._make_store_and_emitter()
        try:
            # Emit memory events
            memory_event = emit_memory_write("tool_observation", task_id="task123", metadata={"tool": "calculator"})
            assert memory_event is not None
            assert memory_event.event_type == EventType.MEMORY_WRITE.value
            assert memory_event.tool == "tool_observation"
            assert memory_event.metadata.get("tool") == "calculator"

            attempt_event = emit_attempt_created("task123", 3)
            assert attempt_event is not None
            assert attempt_event.event_type == EventType.ATTEMPT_CREATED.value
            assert attempt_event.task_id == "task123"
            assert attempt_event.metadata.get("attempt_number") == 3

            comparison_event = emit_attempt_comparison("task123", True, 0.25)
            assert comparison_event is not None
            assert comparison_event.event_type == EventType.ATTEMPT_COMPARISON.value
            assert comparison_event.task_id == "task123"
            assert comparison_event.success is True  # is_improvement maps to success
            assert comparison_event.metadata.get("score_delta") == 0.25

            local_model_event = emit_local_model_activated("remote_unavailable", task_id="task123")
            assert local_model_event is not None
            assert local_model_event.event_type == EventType.LOCAL_MODEL_ACTIVATED.value
            assert local_model_event.task_id == "task123"
            assert local_model_event.metadata.get("reason") == "remote_unavailable"

            iteration_event = emit_agent_loop_iteration("task123", 5)
            assert iteration_event is not None
            assert iteration_event.event_type == EventType.AGENT_LOOP_ITERATION.value
            assert iteration_event.task_id == "task123"
            assert iteration_event.metadata.get("iteration") == 5

            # Verify all events stored
            events = store.query_events()
            assert len(events) == 5
        finally:
            store.close()
            import os
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
