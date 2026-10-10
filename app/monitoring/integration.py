"""Monitoring integration - instrument existing components with observability."""

import time
import uuid
from contextlib import contextmanager
from typing import Any, Optional

from app.monitoring.emitter import (
    EventEmitter,
    get_emitter,
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
from app.monitoring.events import sanitize_metadata


def configure_agent_monitoring(agent, session_id: Optional[str] = None) -> EventEmitter:
    """Configure monitoring for an Agent instance."""
    emitter = get_emitter()
    emitter.session_id = session_id or str(uuid.uuid4())[:8]
    emitter.enabled = True

    # Store original methods
    original_run = agent.run

    def monitored_run(message: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        emit_task_started(task_id, message, session_id=emitter.session_id)

        try:
            result = original_run(message)
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_task_completed(task_id, duration_ms, session_id=emitter.session_id)
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_task_failed(task_id, duration_ms, type(e).__name__, session_id=emitter.session_id)
            raise

    agent.run = monitored_run
    return emitter


def configure_planner_monitoring(planner) -> None:
    """Configure monitoring for LLMPlanner."""
    original_plan = planner.plan

    def monitored_plan(message: str, available_tools: list[dict], observations: list = None, context: str = None):
        task_id = getattr(planner, '_current_task_id', None)
        start_time = time.perf_counter()

        try:
            plan = original_plan(message, available_tools, observations, context)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Emit provider request/success based on router type
            if hasattr(planner, 'router') and hasattr(planner.router, 'select_provider'):
                # Using OmniRoute
                pass  # Provider events emitted by OmniRoute
            elif hasattr(planner, 'router'):
                provider = getattr(planner.router, '__class__', type('X',(),{'__name__':'SmartRouter'})).__name__
                emit_provider_request(provider, "unknown", task_id=task_id)

            return plan
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(planner, 'router') and hasattr(planner.router, 'select_provider'):
                pass  # Handled by OmniRoute
            elif hasattr(planner, 'router'):
                provider = getattr(planner.router, '__class__', type('X',(),{'__name__':'SmartRouter'})).__name__
                emit_provider_failure(provider, "unknown", duration_ms, type(e).__name__, task_id=task_id)
            raise

    planner.plan = monitored_plan


def configure_omniroute_monitoring(omniroute) -> None:
    """Configure monitoring for OmniRoute."""
    original_select_provider = omniroute.select_provider
    original_ask = omniroute.ask

    def monitored_select_provider(provider_type_hint=None, message=""):
        task_id = getattr(omniroute, '_current_task_id', None)
        provider = original_select_provider(provider_type_hint, message)

        # Emit provider request event
        emit_provider_request(provider.value, "default", task_id=task_id)

        return provider

    def monitored_ask(provider_type, message):
        task_id = getattr(omniroute, '_current_task_id', None)
        start_time = time.perf_counter()

        try:
            result = original_ask(provider_type, message)
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_provider_success(provider_type.value, "default", duration_ms, task_id=task_id)
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_provider_failure(provider_type.value, "default", duration_ms, type(e).__name__, task_id=task_id)
            raise

    def monitored_fallback_ask(message, fallback_gateway):
        """Wrapper for fallback chain."""
        task_id = getattr(omniroute, '_current_task_id', None)
        emit_local_model_activated("remote_providers_unavailable", task_id=task_id)
        return fallback_gateway.ask("local", message)

    omniroute.select_provider = monitored_select_provider
    omniroute.ask = monitored_ask

    # Also monitor fallback - this is called from LLMPlanner when remote fails
    if hasattr(omniroute, 'fallback_gateway') and omniroute.fallback_gateway:
        original_fallback_ask = omniroute.fallback_gateway.ask
        def monitored_fallback(provider, message):
            task_id = getattr(omniroute, '_current_task_id', None)
            emit_local_model_activated("fallback_to_local", task_id=task_id)
            return original_fallback_ask(provider, message)
        omniroute.fallback_gateway.ask = monitored_fallback


def configure_tool_executor_monitoring(executor) -> None:
    """Configure monitoring for ToolExecutor."""
    original_execute = executor.execute

    def monitored_execute(tool_name: str, **kwargs) -> Any:
        task_id = getattr(executor, '_current_task_id', None)
        start_time = time.perf_counter()

        emit_tool_started(tool_name, task_id=task_id)

        try:
            result = original_execute(tool_name, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_tool_completed(tool_name, duration_ms, task_id=task_id)
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            emit_tool_failed(tool_name, duration_ms, type(e).__name__, task_id=task_id)
            raise

    executor.execute = monitored_execute


def configure_permission_manager_monitoring(permission_manager) -> None:
    """Configure monitoring for PermissionManager."""
    original_check_permission = permission_manager.check_permission
    original_grant_permission = permission_manager.grant_permission
    original_deny_permission = permission_manager.deny_permission

    def monitored_check_permission(tool_name: str, arguments: dict, risk_level=None):
        task_id = getattr(permission_manager, '_current_task_id', None)
        risk = risk_level or permission_manager.classify_risk(tool_name, arguments)

        emit_permission_requested(tool_name, risk.name, task_id=task_id)

        allowed, reason = original_check_permission(tool_name, arguments, risk_level)

        if allowed:
            emit_permission_granted(tool_name, task_id=task_id, metadata={"reason": reason})
        else:
            emit_permission_denied(tool_name, task_id=task_id, metadata={"reason": reason})

        return allowed, reason

    def monitored_grant_permission(tool_name, arguments, scope, duration="session", **kwargs):
        task_id = getattr(permission_manager, '_current_task_id', None)
        emit_permission_granted(tool_name, task_id=task_id, metadata={"scope": scope, "duration": duration})
        return original_grant_permission(tool_name, arguments, scope, duration, **kwargs)

    def monitored_deny_permission(tool_name, arguments, reason=""):
        task_id = getattr(permission_manager, '_current_task_id', None)
        emit_permission_denied(tool_name, task_id=task_id, metadata={"reason": reason})
        return original_deny_permission(tool_name, arguments, reason)

    permission_manager.check_permission = monitored_check_permission
    permission_manager.grant_permission = monitored_grant_permission
    permission_manager.deny_permission = monitored_deny_permission


def configure_enhanced_memory_monitoring(memory) -> None:
    """Configure monitoring for EnhancedMemory."""
    original_add_tool_observation = memory.add_tool_observation
    original_add_attempt = memory.add_attempt
    original_compare_attempts = memory.compare_attempts

    def monitored_add_tool_observation(tool: str, result: Any):
        task_id = getattr(memory, '_current_task_id', None)
        emit_memory_write("tool_observation", task_id=task_id, metadata={"tool": tool})
        return original_add_tool_observation(tool, result)

    def monitored_add_attempt(task_id: str, plan, tool_name: str, arguments: dict, observation: Any, evaluation):
        emit_attempt_created(task_id, len(memory.attempts.get(task_id, [])) + 1)
        return original_add_attempt(task_id, plan, tool_name, arguments, observation, evaluation)

    def monitored_compare_attempts(task_id: str, current_evaluation: float, success_threshold: float = 0.8):
        result = original_compare_attempts(task_id, current_evaluation, success_threshold)
        emit_attempt_comparison(task_id, result.is_improvement, result.score_delta)
        return result

    memory.add_tool_observation = monitored_add_tool_observation
    memory.add_attempt = monitored_add_attempt
    memory.compare_attempts = monitored_compare_attempts


def configure_agent_loop_monitoring(agent_loop) -> None:
    """Configure monitoring for AgentLoop."""
    original_run = agent_loop.run

    def monitored_run(message, available_tools, responder, reflection_callback, context):
        task_id = getattr(agent_loop, '_current_task_id', None)
        iteration = 0

        # Wrap the iteration callback
        original_reflection_callback = reflection_callback

        def monitored_reflection_callback(tool_name, result):
            nonlocal iteration
            iteration += 1
            emit_agent_loop_iteration(task_id, iteration)
            return original_reflection_callback(tool_name, result)

        return original_run(message, available_tools, responder, monitored_reflection_callback, context)

    agent_loop.run = monitored_run


def instrument_agent(agent, session_id: Optional[str] = None) -> EventEmitter:
    """Fully instrument an Agent with monitoring."""
    emitter = configure_agent_monitoring(agent, session_id)

    # Instrument all components
    configure_planner_monitoring(agent.planner)
    configure_omniroute_monitoring(agent.omniroute)
    configure_tool_executor_monitoring(agent.tool_executor)
    configure_permission_manager_monitoring(agent.permission_manager)
    configure_enhanced_memory_monitoring(agent.memory)
    configure_agent_loop_monitoring(agent.agent_loop)

    # Set task_id on all components for correlation
    def set_task_id(task_id: str):
        for component in [agent.planner, agent.omniroute, agent.tool_executor,
                          agent.permission_manager, agent.memory, agent.agent_loop]:
            component._current_task_id = task_id

    # Wrap agent.run to set task_id
    original_run = agent.run

    def monitored_run(message: str) -> str:
        task_id = str(uuid.uuid4())[:8]
        set_task_id(task_id)
        return original_run(message)

    agent.run = monitored_run

    return emitter


def create_monitored_agent(*args, **kwargs):
    """Create an Agent with monitoring enabled."""
    from app.core.agent import Agent

    agent = Agent(*args, **kwargs)
    instrument_agent(agent)
    return agent