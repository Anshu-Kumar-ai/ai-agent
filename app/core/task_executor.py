"""Task Executor - Stage 29: Autonomous Execution Orchestration.

Orchestrates multi-step task execution using the Task state model,
integrating with existing AgentLoop, Planner, Evaluator, and monitoring.
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.evaluation import Evaluation
from app.core.evaluator import Evaluator
from app.core.planner import LLMPlanner, Plan, Planner
from app.core.plan_evaluation import PlanEvaluator, ExecutionEvaluator
from app.core.state.task import (
    FailureCategory,
    PlanVersion,
    StepExecution,
    Task,
    TaskCheckpoint,
    TaskStatus,
    validate_transition,
)
from app.memory.enhanced import EnhancedMemory
from app.memory.planning_context import PlanningMemoryRetriever
from app.memory.reflection import ReflectionGenerator
from app.memory.skills import SkillRegistry, get_all_skills
from app.monitoring.emitter import (
    emit_agent_loop_iteration,
    emit_browser_action,
    emit_browser_error,
    emit_browser_navigation,
    emit_browser_session_created,
    emit_browser_tab_closed,
    emit_browser_tab_opened,
    emit_desktop_action,
    emit_desktop_application_opened,
    emit_desktop_error,
    emit_desktop_window_changed,
    emit_memory_write,
    emit_permission_denied,
    emit_permission_granted,
    emit_permission_requested,
    emit_provider_fallback,
    emit_provider_failure,
    emit_provider_request,
    emit_provider_success,
    emit_task_completed,
    emit_task_failed,
    emit_task_started,
    emit_tool_completed,
    emit_tool_failed,
    emit_tool_started,
)
from app.monitoring.emitter import get_emitter
from app.monitoring.events import sanitize_metadata
from app.tools.capabilities import CapabilityCategory
from app.tools.executor import ToolExecutor


class TaskExecutor:
    """Executes multi-step tasks with full lifecycle management."""

    def __init__(
        self,
        planner: Planner | LLMPlanner,
        tool_executor: ToolExecutor,
        evaluator: Evaluator | None = None,
        memory: EnhancedMemory | None = None,
        max_steps: int = 10,
        max_retries_per_step: int = 2,
        max_replans: int = 3,
        max_task_duration_seconds: int = 300,
        permission_manager=None,
        permission_callback: Callable[[str, str, dict], bool] | None = None,
    ):
        self.planner = planner
        self.tool_executor = tool_executor
        self.evaluator = evaluator
        self.memory = memory
        self.max_steps = max_steps
        self.max_retries_per_step = max_retries_per_step
        self.max_replans = max_replans
        self.max_task_duration_seconds = max_task_duration_seconds
        self.permission_manager = permission_manager
        self.permission_callback = permission_callback

        # Monitoring
        self._emitter = get_emitter()

        # Adaptive replanning components
        self._plan_evaluator = PlanEvaluator(None)  # Will set capability_planner when needed
        self._execution_evaluator = ExecutionEvaluator()
        self._reflection_generator = ReflectionGenerator(memory)
        self._skill_registry = SkillRegistry()
        for skill in get_all_skills():
            self._skill_registry.register(skill)
        self._memory_retriever = PlanningMemoryRetriever(memory) if memory is not None else None

        # Runtime state
        self._current_task: Task | None = None
        self._task_history: list[Task] = []

    def create_task(
        self,
        user_goal: str,
        task_id: str | None = None,
        available_tools: list[dict] | None = None,
    ) -> Task:
        """Create a new task with initial state."""
        task = Task(
            task_id=task_id or str(uuid4())[:8],
            user_goal=user_goal,
            max_steps=self.max_steps,
            max_retries_per_step=self.max_retries_per_step,
            max_replans=self.max_replans,
            max_task_duration_seconds=self.max_task_duration_seconds,
        )

        # Emit task created event
        self._emit_task_event("task.created", task, {"user_goal": user_goal})

        return task

    def execute_task(
        self,
        task: Task,
        available_tools: list[dict],
        responder: Callable[[list[dict]], str],
        reflection_callback: Callable[[str, Any], None] | None = None,
    ) -> Task:
        """Execute a task to completion."""
        self._current_task = task
        task.start()

        # Emit task started
        self._emit_task_event("task.started", task, {"user_goal": task.user_goal})

        # Build initial context from memory
        initial_context = self._build_context(task) if self.memory else None

        # Execution loop
        step_count = 0
        replan_count = 0

        # Context that may be updated during replanning
        current_context = initial_context

        while not task.is_terminal() and step_count < task.max_steps:
            # Check duration limit
            if task.has_exceeded_duration():
                task.fail(f"Task exceeded maximum duration of {task.max_task_duration_seconds} seconds")
                break

            # Check for replan limit
            if replan_count >= task.max_replans:
                task.fail(f"Exceeded maximum replans ({task.max_replans})")
                break

            # Emit step started
            self._emit_task_event("task.step_started", task, {
                "step_number": step_count + 1,
                "max_steps": task.max_steps,
            })

            try:
                # Get next plan using current context (which may be updated by replanning)
                plan = self.planner.plan(
                    message=task.user_goal,
                    available_tools=available_tools,
                    observations=task.observations if task.observations else None,
                    context=current_context,
                )

                # Wrap plan in PlanVersion if needed
                if not task.current_plan:
                    task.set_plan(PlanVersion(
                        version=1,
                        plan_id=f"plan_{task.task_id}_v1",
                        goal=task.user_goal,
                    ))

                # Check if task was cancelled during planning
                if task.is_terminal():
                    break

                # Call responder with the plan for user confirmation/cancellation
                responder_response = responder([plan.to_dict()])
                if responder_response == "cancel":
                    task.cancel()
                    break
                elif responder_response != "continue":
                    # Handle other responder responses if needed
                    pass

                # Check if task was cancelled during planning or responder
                if task.is_terminal():
                    break

                if plan.action == "respond":
                    # Planner wants to respond - use the planner's response
                    response = plan.response

                    # Evaluate if evaluator available
                    if self.evaluator:
                        evaluation = self.evaluator.evaluate(
                            task=task,
                            plan=plan,
                            response=response,
                            available_tools=available_tools,
                        )
                        if evaluation.success:
                            task.complete(evaluation.output)
                            self._emit_task_event("task.completed", task, {
                                "final_result": evaluation.output[:200] if isinstance(evaluation.output, str) else str(evaluation.output)[:200],
                                "evaluation_score": evaluation.score,
                            })
                        else:
                            task.fail(evaluation.output)
                    else:
                        # No evaluator, just use the planner's response
                        # Check if response contains an error (e.g., from unknown capability)
                        if isinstance(response, str) and "Error:" in response:
                            task.fail(response)
                        else:
                            task.complete(response)
                            self._emit_task_event("task.completed", task, {
                                "final_result": response[:200] if isinstance(response, str) else str(response)[:200],
                            })
                    break

                else:  # use_tool
                    # Start step tracking
                    step_execution = StepExecution(
                        step_id=plan.tool_name,  # Use tool_name as step_id for now
                        action="use_tool",
                        tool_name=plan.tool_name,
                        arguments=plan.arguments,
                        reason=plan.reason,
                        started_at=datetime.utcnow().timestamp(),
                    )
                    task.start_step(step_execution)

                    # Execute tool with permission check
                    result = self._execute_tool_step(task, plan, available_tools)

                    if result.get("permission_denied"):
                        task.wait_for_approval(plan.tool_name, plan.arguments)
                        # If we get here, permission was granted (or denied and we continued)
                        if task.status == TaskStatus.FAILED:
                            break
                        continue

                    if result.get("success"):
                        # Verify step
                        if self._verify_step(task, plan, result):
                            task.verify_step(True, "Step verification passed")
                            task.complete_step(True, result.get("result"))
                            self._emit_task_event("task.step_completed", task, {
                                "step_id": plan.tool_name,
                                "tool_name": plan.tool_name,
                            })
                        else:
                            task.verify_step(False, "Step verification failed")
                            # Handle verification failure
                            self._handle_verification_failure(task, plan, result)
                    else:
                        # Tool execution failed
                        task.complete_step(False, error=result.get("error"))
                        replan_success, replan_plan, replan_context = self._handle_tool_failure(task, plan, result, available_tools, current_context)
                        if replan_success:
                            replan_count += 1
                            # Execute the replan step directly instead of going through the loop again
                            # Update context with the improved replanning context
                            current_context = replan_context
                            # Execute the replan step directly
                            step_execution = StepExecution(
                                step_id=replan_plan.tool_name,
                                action="use_tool",
                                tool_name=replan_plan.tool_name,
                                arguments=replan_plan.arguments,
                                reason=replan_plan.reason,
                                started_at=datetime.utcnow().timestamp(),
                            )
                            task.start_step(step_execution)
                            result = self._execute_tool_step(task, replan_plan, available_tools)
                            if result.get("success"):
                                if self._verify_step(task, replan_plan, result):
                                    task.verify_step(True, "Step verification passed")
                                    task.complete_step(True, result.get("result"))
                                    self._emit_task_event("task.step_completed", task, {
                                        "step_id": replan_plan.tool_name,
                                        "tool_name": replan_plan.tool_name,
                                    })
                                else:
                                    task.verify_step(False, "Step verification failed")
                                    self._handle_verification_failure(task, replan_plan, result)
                            else:
                                task.complete_step(False, error=result.get("error"))
                        continue

                    # Update context with new observations
                    if self.memory:
                        current_context = self._build_context(task)

            except Exception as e:
                # Handle unexpected errors
                self._handle_exception(task, e)
                if task.is_terminal():
                    break

            step_count += 1
            emit_agent_loop_iteration(task.task_id, step_count)

        # Handle terminal states
        if task.status == TaskStatus.RUNNING and step_count >= task.max_steps:
            task.fail(f"Maximum steps ({task.max_steps}) reached")

        if task.status == TaskStatus.FAILED:
            self._emit_task_event("task.failed", task, {"error": task.error})
        elif task.status == TaskStatus.CANCELLED:
            self._emit_task_event("task.cancelled", task, {})

        # Save to history
        self._task_history.append(task)

        return task

    def _execute_tool_step(
        self,
        task: Task,
        plan: Plan,
        available_tools: list[dict],
    ) -> dict[str, Any]:
        """Execute a single tool step with permission handling."""
        tool_name = plan.tool_name
        arguments = plan.arguments

        # Permission check
        if self.permission_manager:
            allowed, reason = self.permission_manager.check_permission(tool_name, arguments)

            self._emit_task_event("permission_requested", task, {
                "tool": tool_name,
                "reason": reason,
            })

            if not allowed:
                # Request approval via callback
                approved = False
                if self.permission_callback:
                    try:
                        approved = self.permission_callback(tool_name, reason, arguments)
                    except Exception:
                        approved = False

                if approved:
                    self.permission_manager.grant_permission(
                        tool_name=tool_name,
                        arguments=arguments,
                        scope=self._describe_scope(arguments),
                        duration="session",
                    )
                    self._emit_task_event("permission_granted", task, {"tool": tool_name})
                else:
                    self._emit_task_event("permission_denied", task, {"tool": tool_name})
                    task.permissions_denied.append(tool_name)
                    return {"permission_denied": True, "error": f"Permission denied: {reason}"}

        # Execute tool
        self._emit_task_event("tool_started", task, {"tool": tool_name})
        start_time = time.time()

        try:
            result = self.tool_executor.execute(tool_name, **arguments)
            duration_ms = (time.time() - start_time) * 1000

            # Record in memory
            if self.memory:
                self.memory.add_tool_observation(tool_name, result)
                self._emit_task_event("memory_write", task, {
                    "memory_type": "tool_observation",
                    "tool": tool_name,
                })

            # Emit tool completed
            self._emit_task_event("tool_completed", task, {
                "tool": tool_name,
                "duration_ms": duration_ms,
            })

            return {"success": True, "result": result}

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_type = type(e).__name__

            self._emit_task_event("tool_failed", task, {
                "tool": tool_name,
                "duration_ms": duration_ms,
                "error_type": error_type,
            })

            return {"success": False, "error": f"{error_type}: {str(e)}"}

    def _verify_step(self, task: Task, plan: Plan, result: dict) -> bool:
        """Verify that a tool step achieved its intended result."""
        tool_name = plan.tool_name

        # For now, basic verification - can be extended
        if tool_name == "calculator":
            # Calculator should return a number
            return isinstance(result.get("result"), (int, float))
        elif tool_name in ("fs.write", "fs.read", "fs.list", "fs.move", "filesystem_write"):
            # File operations should return success dict
            return result.get("success", False)
        elif tool_name == "terminal.run":
            return result.get("success", False)
        elif tool_name in ("browser_agent.execute", "browser_session.manage", "browser.observe", "browser.action"):
            return result.get("success", False)
        elif tool_name in ("desktop.list_windows", "desktop.focus_window", "desktop.click", "desktop.type", "desktop.key_press", "desktop.screenshot"):
            return result.get("success", False)
        elif tool_name in ("rag.add", "rag.query", "rag.stats"):
            return result.get("success", False)

        # Default: if tool returned without exception, assume success
        return True

    def _handle_verification_failure(self, task: Task, plan: Plan, result: dict) -> None:
        """Handle step verification failure with adaptive replanning."""
        # Check if we can retry
        if task._current_step and task._current_step.retry_count < task.max_retries_per_step:
            task._current_step.retry_count += 1
            self._emit_task_event("task.retry", task, {
                "step_id": plan.tool_name,
                "retry_count": task._current_step.retry_count,
                "reason": "Verification failed",
            })
        else:
                    # Move to recovery with adaptive replan
                    task.enter_recovery()
                    self._emit_task_event("task.recovery", task, {
                        "step_id": plan.tool_name,
                        "reason": "Verification failed, max retries exceeded",
                    })

                    # Build context for replanning
                    current_context = self._build_context(task) if self.memory else None

                    # Attempt adaptive replan
                    replan_result = self._replan(
                        task=task,
                        available_tools=available_tools,  # Pass the actual available tools
                        failure_category=FailureCategory.STATE_CHANGED,  # Verification failure = state changed
                        failed_step=plan.tool_name,
                        error="Step verification failed",
                        context=current_context,
                    )

                    if replan_result and replan_result[0] and replan_result[0].action == "use_tool":
                        task.exit_recovery(success=True)
                        return
                    else:
                        task.fail(f"Unable to recover from verification failure")
                        self._emit_task_event("task.failed", task, {
                            "error": "Verification failed",
                            "failure_category": "STATE_CHANGED",
                            "replan_attempted": replan_result is not None and replan_result[0] is not None,
                        })

    def _replan(
            self,
            task: Task,
            available_tools: list[dict],
            failure_category: FailureCategory,
            failed_step: str,
            error: str,
            context: str | None,
        ) -> tuple[Plan | None, str]:
        """Generate a revised plan using memory, reflections, skills, and failure analysis.

        This is the core adaptive replanning logic that:
        1. Preserves completed work (completed_step_ids)
        2. Analyzes failure category to determine strategy
        3. Retrieves relevant memory/reflections/skills
        4. Generates revised plan with updated context
        """
        # Get completed steps to preserve
        completed_steps = task.completed_step_ids
        # Retrieve relevant memory for the failure
        planning_context = None
        if self._memory_retriever:
            # Map failure category to required capabilities
            failure_to_capability = {
                FailureCategory.TIMEOUT: [CapabilityCategory.BROWSER, CapabilityCategory.NETWORK],
                FailureCategory.BROWSER_FAILURE: [CapabilityCategory.BROWSER],
                FailureCategory.STATE_CHANGED: [CapabilityCategory.BROWSER, CapabilityCategory.DESKTOP, CapabilityCategory.FILESYSTEM],
                FailureCategory.RESOURCE_UNAVAILABLE: [CapabilityCategory.BROWSER, CapabilityCategory.NETWORK],
                FailureCategory.TRANSIENT_PROVIDER_FAILURE: [CapabilityCategory.COMPUTATION],
                FailureCategory.ENVIRONMENT_FAILURE: [CapabilityCategory.BROWSER, CapabilityCategory.DESKTOP, CapabilityCategory.NETWORK],
                FailureCategory.INVALID_ARGUMENT: [CapabilityCategory.FILESYSTEM],
                FailureCategory.PERMISSION_DENIED: [CapabilityCategory.FILESYSTEM],
            }
            required_capabilities = failure_to_capability.get(failure_category, [])
            planning_context = self._memory_retriever.retrieve_context(
                goal=task.user_goal,
                available_tools=[t["name"] for t in available_tools],
                required_capabilities=required_capabilities,
            )
        # Find relevant skills for this failure
        relevant_skills = []
        if self._skill_registry:
            # Map failure category to capability categories
            failure_to_capability = {
                FailureCategory.TIMEOUT: ["browser", "network"],
                FailureCategory.BROWSER_FAILURE: ["browser"],
                FailureCategory.STATE_CHANGED: ["browser", "desktop", "filesystem"],
                FailureCategory.RESOURCE_UNAVAILABLE: ["browser", "network"],
                FailureCategory.TRANSIENT_PROVIDER_FAILURE: ["computation"],
                FailureCategory.ENVIRONMENT_FAILURE: ["browser", "desktop", "network"],
            }
            capability_names = failure_to_capability.get(failure_category, [])
            # This is simplified - in practice would map to CapabilityCategory enums
            relevant_skills = self._skill_registry.find_relevant(
                goal=task.user_goal,
                required_capabilities=[],  # Would need proper mapping
                available_tools=[t["name"] for t in available_tools],
                current_permissions=task.permissions_granted,
            environment={"is_windows": True, "network_required": True},
                    )
        # Generate improved context for replanning
        improved_context_parts = []
        if context:
            improved_context_parts.append(context)
        # Add failure analysis
        improved_context_parts.append(f"\n=== REPLAN TRIGGERED ===")
        improved_context_parts.append(f"Failed step: {failed_step}")
        improved_context_parts.append(f"Failure category: {failure_category.value}")
        improved_context_parts.append(f"Error: {error}")
        improved_context_parts.append(f"Completed steps (preserve these): {', '.join(completed_steps)}")

        # Add reflection guidance
        if planning_context and planning_context.useful_reflections:
            improved_context_parts.append(f"\nRelevant reflections:")
            for r in planning_context.useful_reflections[:3]:
                improved_context_parts.append(f"  - {r}")

        # Add skill guidance
        if relevant_skills:
            improved_context_parts.append(f"\nRelevant skills:")
            for skill in relevant_skills[:2]:
                improved_context_parts.append(f"  - {skill.name}: {skill.intent}")
                if skill.workflow:
                    for step in skill.workflow:
                        improved_context_parts.append(f"    * {step.get('tool', 'unknown')}: {step.get('produces', [])}")

        # Add memory guidance
        if planning_context:
            if planning_context.relevant_failures:
                improved_context_parts.append(f"\nSimilar past failures:")
                for f in planning_context.relevant_failures[:2]:
                    improved_context_parts.append(f"  - {f.get('tool', 'unknown')}: {f.get('error', 'unknown')}")
            if planning_context.tool_reliability:
                improved_context_parts.append(f"\nTool reliability:")
                for tool, rel in list(planning_context.tool_reliability.items())[:3]:
                    improved_context_parts.append(f"  - {tool}: {rel.success_rate:.0%} success ({rel.total_attempts} attempts)")

        improved_context_parts.append(f"\nPlease generate a revised plan that:")
        improved_context_parts.append(f"1. Preserves completed steps: {completed_steps}")
        improved_context_parts.append(f"2. Addresses the {failure_category.value} failure")
        improved_context_parts.append(f"3. Uses alternative strategies if needed")
        improved_context_parts.append(f"4. Still achieves the original goal: {task.user_goal}")

        improved_context = "\n".join(improved_context_parts)

        # Get new plan from planner with improved context
        new_plan = self.planner.plan(
            message=task.user_goal,
            available_tools=available_tools,
            observations=task.observations if task.observations else None,
            context=improved_context,
        )

        # Create new plan version
        new_version = task.current_plan.version + 1 if task.current_plan else 1
        parent_version = task.current_plan.version if task.current_plan else None
        new_plan_version = PlanVersion(
            version=new_version,
            plan_id=f"plan_{task.task_id}_v{new_version}",
            goal=task.user_goal,
            parent_version=parent_version,
        )
        task.replan(new_plan_version)

        # Emit replan event with full metadata
        self._emit_task_event("planning.replan", task, {
            "new_plan_version": new_version,
            "parent_plan_version": parent_version,
            "failed_step": failed_step,
            "failure_category": failure_category.value,
            "reason": error[:200],
            "preserved_steps": list(completed_steps),
            "skills_considered": [s.name for s in relevant_skills[:3]],
            "reflections_used": len(planning_context.useful_reflections) if planning_context else 0,
        })

        # Return both the new plan AND the improved context so the main loop can use it
        return new_plan, improved_context

    def _handle_tool_failure(self, task: Task, plan: Plan, result: dict, available_tools: list[dict], current_context: str | None) -> tuple[bool, Plan, str | None]:
        """Handle tool execution failure with categorization and adaptive replanning.

        Returns (True, replan_plan, new_context) if a replan happened and execution should continue, (False, None, None) otherwise.
        """
        error = result.get("error", "Unknown error")

        # Categorize failure
        failure_category = self._categorize_failure(error, plan.tool_name)

        if task._current_step:
            task._current_step.failure_category = failure_category

        # Check if retryable
        retryable = failure_category in (
            FailureCategory.TIMEOUT,
            FailureCategory.TRANSIENT_PROVIDER_FAILURE,
            FailureCategory.BROWSER_FAILURE,
            FailureCategory.ENVIRONMENT_FAILURE,
        )

        if retryable and task._current_step and task._current_step.retry_count < task.max_retries_per_step:
            task._current_step.retry_count += 1
            self._emit_task_event("task.retry", task, {
                "step_id": plan.tool_name,
                "retry_count": task._current_step.retry_count,
                "failure_category": failure_category.value,
            })
            return False, None, current_context
        else:
            # Non-retryable or max retries exceeded - attempt adaptive replan
            if failure_category == FailureCategory.PERMISSION_DENIED:
                task.deny_permission(plan.tool_name)
                self._emit_task_event("permission_denied", task, {"tool": plan.tool_name})
                self._emit_task_event("task.failed", task, {
                    "error": f"Permission denied: {error}",
                    "failure_category": failure_category.value,
                })
                return False, None, None

            # Build context for replanning
            new_context = self._build_context(task) if self.memory else None

            # Attempt adaptive replan
            replan_result = self._replan(
                task=task,
                available_tools=available_tools,  # Pass the actual available tools
                failure_category=failure_category,
                failed_step=plan.tool_name,
                error=error,
                context=new_context,
            )

            if replan_result and replan_result[0] and replan_result[0].action == "use_tool":
                # New plan generated, continue execution
                task.status = TaskStatus.RUNNING
                return True, replan_result[0], replan_result[1]  # Use the improved context
            else:
                # No valid replan, mark as failed
                task.fail(f"Unable to recover from {failure_category.value}: {error}")
                self._emit_task_event("task.failed", task, {
                    "error": error,
                    "failure_category": failure_category.value,
                    "replan_attempted": replan_result is not None and replan_result[0] is not None,
                })
                return False, None, None

    def _categorize_failure(self, error: str, tool_name: str) -> FailureCategory:
        """Categorize a failure for recovery decisions."""
        error_lower = error.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return FailureCategory.TIMEOUT
        elif "permission" in error_lower and "denied" in error_lower:
            return FailureCategory.PERMISSION_DENIED
        elif "provider" in error_lower and ("unavailable" in error_lower or "failed" in error_lower):
            return FailureCategory.TRANSIENT_PROVIDER_FAILURE
        elif "invalid" in error_lower and "argument" in error_lower:
            return FailureCategory.INVALID_ARGUMENT
        elif "resource" in error_lower and "unavailable" in error_lower:
            return FailureCategory.RESOURCE_UNAVAILABLE
        elif "state" in error_lower and "changed" in error_lower:
            return FailureCategory.STATE_CHANGED
        elif "browser" in error_lower or "playwright" in error_lower:
            return FailureCategory.BROWSER_FAILURE
        elif "connection" in error_lower or "network" in error_lower:
            return FailureCategory.ENVIRONMENT_FAILURE
        else:
            return FailureCategory.UNKNOWN

    def _handle_exception(self, task: Task, exception: Exception) -> None:
        """Handle unexpected exceptions during execution."""
        error_type = type(exception).__name__
        error_msg = str(exception)

        self._emit_task_event("task.error", task, {
            "error_type": error_type,
            "error_message": error_msg,
        })

        if not task.is_terminal():
            task.fail(f"{error_type}: {error_msg}")

    def _verify_final_goal(self, task: Task, response: str, evaluation: Evaluation) -> bool:
        """Verify that the user's original goal has been satisfied."""
        # Use evaluator's completeness check
        # For now, rely on evaluation score and criteria
        if evaluation.score >= 0.7:
            # Check if critical criteria are met
            critical_criteria = {"tool_executions_successful", "no_hallucination", "response_addresses_request"}
            critical_met = critical_criteria.issubset(set(evaluation.criteria_met))
            return critical_met
        return False

    def _record_attempt(self, task: Task, plan: Plan, evaluation: Evaluation) -> None:
        """Record an attempt in EnhancedMemory."""
        if not self.memory:
            return

        observation = task.observations[-1]["result"] if task.observations else None

        self.memory.add_attempt(
            task_id=task.task_id,
            plan=plan,
            tool_name=plan.tool_name,
            arguments=plan.arguments,
            observation=observation,
            evaluation=evaluation,
        )

        task.attempts.append({
            "plan": plan.to_dict(),
            "tool_name": plan.tool_name,
            "arguments": plan.arguments,
            "observation": observation,
            "evaluation_score": evaluation.score,
            "evaluation_feedback": evaluation.feedback,
        })

        # Emit attempt created
        attempt_count = len(self.memory.attempts.get(task.task_id, []))
        self._emit_task_event("attempt_created", task, {
            "attempt_number": attempt_count,
        })

        # Emit attempt comparison
        comparison = self.memory.compare_attempts(task.task_id, evaluation.score)
        self._emit_task_event("attempt_comparison", task, {
            "is_improvement": comparison.is_improvement,
            "score_delta": comparison.score_delta,
        })

    def _build_context(self, task: Task) -> str:
        """Build context for planner from memory."""
        if not self.memory:
            return ""

        context_parts = []

        # Add tool observations
        if task.observations:
            context_parts.append("Recent tool observations:")
            for obs in task.observations[-5:]:  # Last 5
                context_parts.append(f"  {obs.get('tool_name', 'unknown')}: {obs.get('result', 'N/A')}")

        # Add attempts summary
        if task.attempts:
            context_parts.append("Previous attempts:")
            for attempt in task.attempts[-3:]:
                context_parts.append(f"  Score: {attempt.get('evaluation_score', 0):.2f}, Feedback: {attempt.get('evaluation_feedback', 'N/A')}")

        return "\n".join(context_parts) if context_parts else ""

    def _build_retry_context(self, original_context: str | None, feedback: str) -> str:
        """Build enhanced context with evaluation feedback for retry."""
        parts = []
        if original_context:
            parts.append(original_context)
        parts.append(f"\nPREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n")
        parts.append("Please improve your response based on this feedback.")
        return "\n".join(parts)

    def _describe_scope(self, arguments: dict) -> str:
        """Describe the scope of a tool invocation for permission."""
        for val in arguments.values():
            if isinstance(val, str) and ("/" in val or "\\" in val):
                return f"path: {val}"
        return "no file paths detected"

    def _emit_task_event(self, event_type: str, task: Task, metadata: dict) -> None:
        """Emit a monitoring event for task lifecycle."""
        if not self._emitter.enabled:
            return

        try:
            sanitized = sanitize_metadata(metadata)
            self._emitter.emit(
                event_type=event_type,
                task_id=task.task_id,
                session_id=getattr(self, '_session_id', None),
                metadata={
                    "task_status": task.status.value,
                    "step_count": len(task.completed_step_ids) + len(task.failed_step_ids),
                    **sanitized,
                },
            )
        except Exception:
            # Monitoring failure must not break execution
            pass

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        if self._current_task and self._current_task.task_id == task_id:
            return self._current_task
        for task in self._task_history:
            if task.task_id == task_id:
                return task
        return None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        task = self.get_task(task_id)
        if task and not task.is_terminal():
            task.cancel()
            self._emit_task_event("task.cancelled", task, {})
            return True
        return False

    def create_checkpoint(self, task_id: str) -> TaskCheckpoint | None:
        """Create a checkpoint for a task."""
        task = self.get_task(task_id)
        if task:
            return task.create_checkpoint()
        return None

    def restore_from_checkpoint(self, checkpoint: TaskCheckpoint) -> Task:
        """Restore a task from checkpoint (simulated restart)."""
        task = Task.from_dict({
            "task_id": checkpoint.task_id,
            "user_goal": "",  # Would need to be stored in checkpoint
            "status": TaskStatus.PENDING.value,
            "completed_step_ids": checkpoint.completed_step_ids,
            "observations": checkpoint.observations_summary,
            "attempts": [],
            "permissions_granted": [],
            "permissions_denied": [],
        })

        # Mark completed steps as verified (don't re-execute)
        task.status = TaskStatus.RUNNING

        self._emit_task_event("task.restored", task, {
            "checkpoint_plan_version": checkpoint.plan_version,
            "completed_steps": len(checkpoint.completed_step_ids),
        })

        return task


def create_task_executor(
    planner: Planner | LLMPlanner,
    tool_executor: ToolExecutor,
    **kwargs,
) -> TaskExecutor:
    """Factory function to create a TaskExecutor."""
    return TaskExecutor(planner, tool_executor, **kwargs)
