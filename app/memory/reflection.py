"""Reflection System - Stage 30 Phase 10.

Structured post-execution reflections for learning.
"""

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
from enum import Enum


class ReflectionType(Enum):
    """Type of reflection."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    RECOVERY = "recovery"


@dataclass
class Reflection:
    """Structured reflection on a completed or failed task."""
    task_id: str
    task_type: str  # e.g., "calculate_and_save", "browser_extract", etc.
    reflection_type: ReflectionType
    approach: str  # What strategy was used
    successful_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    failure_causes: list[str] = field(default_factory=list)
    recovery_used: list[str] = field(default_factory=list)
    better_future_strategy: str = ""
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "reflection_type": self.reflection_type.value,
            "approach": self.approach,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "failure_causes": self.failure_causes,
            "recovery_used": self.recovery_used,
            "better_future_strategy": self.better_future_strategy,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reflection":
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            reflection_type=ReflectionType(data["reflection_type"]),
            approach=data["approach"],
            successful_steps=data.get("successful_steps", []),
            failed_steps=data.get("failed_steps", []),
            failure_causes=data.get("failure_causes", []),
            recovery_used=data.get("recovery_used", []),
            better_future_strategy=data.get("better_future_strategy", ""),
            confidence=data.get("confidence", 0.5),
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"],
        )


class ReflectionGenerator:
    """Generates structured reflections from task execution."""

    def __init__(self, memory=None):
        self.memory = memory

    def generate_reflection(
        self,
        task_id: str,
        task_type: str,
        observations: list[dict],
        evaluations: list[dict],
        final_status: str,
        error: str | None = None,
    ) -> Reflection:
        """Generate a reflection from task execution data."""
        successful_steps = []
        failed_steps = []
        failure_causes = []
        recovery_used = []

        # Analyze observations
        for obs in observations:
            tool = obs.get("tool_name", "unknown")
            result = obs.get("result", {})
            if isinstance(result, dict) and result.get("success", True):
                successful_steps.append(tool)
            elif isinstance(result, dict) and not result.get("success", True):
                failed_steps.append(tool)
                failure_causes.append(result.get("error", "Unknown error"))

        # Analyze evaluations
        final_score = evaluations[-1]["score"] if evaluations else 0.0

        # Determine reflection type
        if final_status == "completed" and final_score >= 0.7:
            reflection_type = ReflectionType.SUCCESS
            confidence = 0.9
        elif final_status == "completed" and final_score >= 0.5:
            reflection_type = ReflectionType.PARTIAL
            confidence = 0.6
        elif final_status == "failed":
            reflection_type = ReflectionType.FAILURE
            confidence = 0.3
        else:
            reflection_type = ReflectionType.PARTIAL
            confidence = 0.5

        # Determine approach
        if successful_steps:
            approach = " → ".join(successful_steps)
        elif failed_steps:
            approach = f"attempted {', '.join(failed_steps)} but failed"
        else:
            approach = "direct response"

        # Generate better future strategy
        better_strategy = self._generate_better_strategy(
            successful_steps, failed_steps, failure_causes, task_type
        )

        return Reflection(
            task_id=task_id,
            task_type=task_type,
            reflection_type=reflection_type,
            approach=approach,
            successful_steps=successful_steps,
            failed_steps=failed_steps,
            failure_causes=failure_causes,
            recovery_used=recovery_used,
            better_future_strategy=better_strategy,
            confidence=confidence,
        )

    def _generate_better_strategy(
        self,
        successful_steps: list[str],
        failed_steps: list[str],
        failure_causes: list[str],
        task_type: str,
    ) -> str:
        """Generate a better future strategy based on what happened."""
        if not failed_steps:
            return "Strategy worked well; continue using this approach."

        strategies = []

        for step, cause in zip(failed_steps, failure_causes):
            cause_lower = cause.lower()

            if "selector" in cause_lower or "element not found" in cause_lower:
                if "browser" in step or "browser_agent" in step:
                    strategies.append("Use accessibility-based lookup instead of CSS selectors")
            elif "timeout" in cause_lower:
                strategies.append("Increase timeout or add explicit wait for page load")
            elif "permission" in cause_lower:
                strategies.append("Request appropriate permissions before execution")
            elif "network" in cause_lower or "connection" in cause_lower:
                strategies.append("Add network retry with backoff")
            elif "invalid argument" in cause_lower:
                strategies.append("Validate arguments before tool invocation")
            elif "file" in cause_lower and "not found" in cause_lower:
                strategies.append("Check file existence before read operations")
            else:
                strategies.append(f"Investigate {step} failure: {cause}")

        if successful_steps and failed_steps:
            strategies.insert(0, f"Preserve working steps: {', '.join(successful_steps)}")

        return "; ".join(strategies) if strategies else "Review failure causes and adjust approach."


def create_reflection(
    task_id: str,
    task_type: str,
    observations: list[dict],
    evaluations: list[dict],
    final_status: str,
    error: str | None = None,
) -> Reflection:
    """Convenience function to create a reflection."""
    generator = ReflectionGenerator()
    return generator.generate_reflection(
        task_id=task_id,
        task_type=task_type,
        observations=observations,
        evaluations=evaluations,
        final_status=final_status,
        error=error,
    )