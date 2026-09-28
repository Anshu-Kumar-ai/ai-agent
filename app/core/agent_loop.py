from dataclasses import dataclass
from typing import Any, Callable, Optional
import datetime

from app.tools.executor import ToolExecutor
from app.core.evaluation import Evaluation
from app.core.evaluator import Evaluator
from app.memory.enhanced import ProviderFailure, EnhancedMemory
from app.core.permissions import PermissionManager


@dataclass
class ToolObservation:
    """The result of one registered tool execution."""

    tool_name: str
    result: Any

    def __post_init__(self):
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")

    def to_dict(self) -> dict:
        """Return a serializable representation of this tool result."""
        return {
            "tool_name": self.tool_name,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ToolObservation":
        """Build an observation from an untrusted serialized payload."""
        if not isinstance(payload, dict):
            raise TypeError("observation payload must be a dictionary")

        required_fields = {"tool_name", "result"}
        missing_fields = required_fields - payload.keys()
        if missing_fields:
            raise ValueError(
                f"observation payload is missing fields: {sorted(missing_fields)}"
            )

        return cls(
            tool_name=payload["tool_name"],
            result=payload["result"],
        )


class AgentLoop:
    """Run a bounded plan, act, observe, evaluate, and re-plan cycle.
    
    Supports evaluation-driven retry: if the evaluation score is below threshold,
    the loop will continue to re-plan with feedback from the evaluation.
    """

    def __init__(
        self,
        planner,
        tool_executor: ToolExecutor,
        max_steps: int = 3,
        reflection_callback: Optional[Callable[[str, Any], None]] = None,
        evaluator: Optional[Evaluator] = None,
        evaluation_callback: Optional[Callable[[Evaluation], None]] = None,
        evaluation_threshold: float = 0.7,
        max_retries: int = 2,  # New: max retries after evaluation failure
        memory: Optional[EnhancedMemory] = None,
        permission_manager: Optional[PermissionManager] = None,
        permission_callback: Optional[Callable[[str, str, dict], bool]] = None,
    ):
        if not isinstance(tool_executor, ToolExecutor):
            raise TypeError("tool_executor must be a ToolExecutor")

        if not isinstance(max_steps, int) or max_steps <= 0:
            raise ValueError("max_steps must be a positive integer")

        self.planner = planner
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.reflection_callback = reflection_callback
        self.evaluator = evaluator
        self.evaluation_callback = evaluation_callback
        self.evaluation_threshold = evaluation_threshold
        self.max_retries = max_retries  # New
        self.memory = memory
        self.permission_manager = permission_manager
        self.permission_callback = permission_callback
        self.provider_failures = []

    def run(
        self,
        message: str,
        available_tools: list[dict],
        responder: Callable[[list[ToolObservation]], str],
        reflection_callback: Optional[Callable[[str, Any], None]] = None,
        context: Optional[str] = None,
    ) -> str:
        """Execute tool plans until the planner responds or the limit is reached.
        After proposing a response, evaluate it. If the evaluation is below threshold,
        continue the loop to re-plan with feedback (up to max_retries times).
        """
        observations: list[ToolObservation] = []

        callback = reflection_callback or self.reflection_callback

        # Track retries for evaluation-driven retry
        retries = 0
        evaluation_feedback = None

        for step in range(self.max_steps):
            try:
                # Build enhanced context with evaluation feedback if we have it
                enhanced_context = context
                if evaluation_feedback:
                    enhanced_context = self._build_retry_context(context, evaluation_feedback)

                plan = self.planner.plan(message, available_tools, observations, enhanced_context)
            except Exception as e:
                pf = ProviderFailure(
                    provider="unknown",
                    model="unknown",
                    status_code=None,
                    error_type=type(e).__name__,
                    retry_count=0,
                    timestamp=datetime.datetime.now(),
                    recoverable=False,
                )
                self.provider_failures.append(pf)
                raise RuntimeError(f"Provider failure: {e}") from e
            print(f"[Agent] Plan: {plan}")

            if plan.action == "respond":
                response = responder(observations)
                print(f"[Agent] Responder response: {response[:200]}...")
                # Evaluate the response if an evaluator is provided.
                if self.evaluator is not None:
                    evaluation = self.evaluator.evaluate(
                        user_request=message,
                        plan=plan.to_dict(),
                        observations=[obs.to_dict() for obs in observations],
                        response=response,
                    )
                    # Store the evaluation if a callback is provided.
                    if self.evaluation_callback is not None:
                        self.evaluation_callback(evaluation)
                    # Store attempt and compare with previous attempts
                    if self.memory is not None:
                        task_id = message  # use user message as task identifier
                        observation = observations[-1].result if observations else None
                        self.memory.add_attempt(
                            task_id=task_id,
                            plan=plan,
                            tool_name=plan.tool_name,
                            arguments=plan.arguments,
                            observation=observation,
                            evaluation=evaluation,
                        )
                        comparison = self.memory.compare_attempts(task_id, evaluation.score)
                        # Optionally store comparison for debugging
                        self.last_comparison = comparison

                    # Check evaluation score - if below threshold and retries available, retry
                    if evaluation.score < self.evaluation_threshold and retries < self.max_retries:
                        retries += 1
                        # Generate feedback for retry
                        evaluation_feedback = self._generate_retry_feedback(evaluation)
                        # Clear the last observation so we can re-plan
                        # Note: we keep observations for context but will re-plan
                        print(f"[Agent] Evaluation score {evaluation.score:.2f} below threshold {self.evaluation_threshold}. Retry {retries}/{self.max_retries}")
                        print(f"[Agent] Feedback: {evaluation.feedback}")
                        continue  # Skip returning, go to next iteration to re-plan

                # Regardless of evaluation quality, return the response when we decide to respond
                return response
            else:
                if plan.action == "use_tool":
                    # Permission check
                    if self.permission_manager is not None:
                        allowed, reason = self.permission_manager.check_permission(
                            plan.tool_name, plan.arguments
                        )
                        if not allowed:
                            # Try to request approval via callback if available
                            approved = False
                            if self.permission_callback is not None:
                                try:
                                    approved = self.permission_callback(
                                        plan.tool_name, reason, plan.arguments
                                    )
                                except Exception:
                                    # If callback fails, treat as not approved
                                    approved = False
                            if approved:
                                # Grant session permission for this specific invocation
                                self.permission_manager.grant_permission(
                                    tool_name=plan.tool_name,
                                    arguments=plan.arguments,
                                    scope=self._describe_scope(plan.arguments),
                                    duration="session",
                                )
                                # Now allowed, proceed to execution
                            else:
                                # Deny execution: return a denial message as result
                                result = f"Permission denied: {reason}"
                                if callback:
                                    callback(plan.tool_name, result)
                                observations.append(
                                    ToolObservation(tool_name=plan.tool_name, result=result)
                                )
                                # Skip tool execution
                                continue
                    # Execute tool if allowed or no permission manager
                    result = self.tool_executor.execute(
                        plan.tool_name,
                        **plan.arguments,
                    )
                    if callback:
                        callback(plan.tool_name, result)
                    observations.append(
                        ToolObservation(tool_name=plan.tool_name, result=result)
                    )
                else:
                    # Unknown action, treat as respond?
                    response = responder(observations)
                    return response

        raise RuntimeError(
            f"Agent loop reached the maximum tool steps ({self.max_steps})"
        )

    def _build_retry_context(self, original_context: Optional[str], feedback: str) -> str:
        """Build enhanced context with evaluation feedback for retry."""
        parts = []
        if original_context:
            parts.append(original_context)
        parts.append(f"\nPREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n")
        parts.append("Please improve your response based on this feedback.")
        return "\n".join(parts)

    def _generate_retry_feedback(self, evaluation: Evaluation) -> str:
        """Generate actionable feedback from evaluation for retry."""
        parts = [f"Evaluation Score: {evaluation.score:.2f} (threshold: {getattr(self, 'evaluation_threshold', 0.7):.2f})"]
        
        if evaluation.criteria_not_met:
            parts.append("Criteria not met:")
            for criterion in evaluation.criteria_not_met:
                parts.append(f"  - {criterion}")
        
        if evaluation.feedback:
            parts.append(f"Feedback: {evaluation.feedback}")
        
        # Add specific guidance based on failed criteria
        guidance = []
        if "no_hallucination" in evaluation.criteria_not_met:
            guidance.append("Ensure you accurately represent tool results in your response.")
        if "tool_executions_successful" in evaluation.criteria_not_met:
            guidance.append("Check that tool executions completed successfully before responding.")
        if "response_addresses_request" in evaluation.criteria_not_met:
            guidance.append("Make sure your response directly addresses the user's question.")
        if "complete_response" in evaluation.criteria_not_met:
            guidance.append("Cover all aspects of the user's request.")
        if "appropriate_tools_used" in evaluation.criteria_not_met:
            guidance.append("Consider whether you used the most appropriate tools for the task.")
        
        if guidance:
            parts.append("Guidance for improvement:")
            for g in guidance:
                parts.append(f"  - {g}")
        
        return "\n".join(parts)

    def _describe_scope(self, arguments: dict) -> str:
        """Produces a human-readable scope description from arguments."""
        # Reuse PermissionManager's method if available, else simple fallback
        if self.permission_manager is not None:
            return self.permission_manager._describe_scope(arguments)
        # Fallback
        for val in arguments.values():
            if isinstance(val, str) and ("/" in val or "\\" in val):
                return f"path: {val}"
        return "no file paths detected"