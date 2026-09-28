import datetime
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from app.core.evaluation import Evaluation
from app.core.planner import Plan
from app.memory.memory import ConversationMemory


@dataclass
class Attempt:
    """Record of a single attempt at solving a user request."""

    task_id: str
    plan: dict
    tool_name: str | None
    arguments: dict
    observation: Any
    evaluation_score: float

@dataclass
class ComparisonResult:
    """Result of comparing an evaluation with previous attempts."""

    task_id: str
    current_score: float
    best_previous_score: float | None
    score_delta: float
    is_improvement: bool
    meets_success_threshold: bool
    attempt_count: int

@dataclass
class ProviderFailure:
    """Record of a provider failure."""

    provider: str
    model: str
    status_code: int | None
    error_type: str
    retry_count: int
    timestamp: datetime
    recoverable: bool

class EnhancedMemory(ConversationMemory):
    """Extended memory that stores tool observations, skills, and reflections."""

    def __init__(self, max_messages: int = 10, max_observations: int = 20, max_skills: int = 50, max_reflections: int = 10, max_evaluations: int = 10, max_attempts_per_task: int = 5):
        super().__init__(max_messages)
        self.max_observations = max_observations
        self.max_skills = max_skills
        self.max_reflections = max_reflections
        self.tool_observations = []
        self.skills = []
        self.reflections = []
        self.evaluations = []
        self.max_evaluations = max_evaluations
        self.task_counter = 0
        self.attempts = defaultdict(list)
        self.max_attempts_per_task = max_attempts_per_task

    def add_tool_observation(self, tool: str, result: Any) -> None:
        """Store a tool execution result."""
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool name must be a non-empty string")

        observation = {
            "tool": tool.strip(),
            "result": result,
        }

        self.tool_observations.append(observation)
        self.tool_observations = self.tool_observations[-self.max_observations:]

    def get_tool_observations(self) -> list[dict]:
        """Return a copy of stored tool observations."""
        return list(self.tool_observations)

    def add_skill(self, skill: dict) -> None:
        """Store a learned skill."""
        if not isinstance(skill, dict):
            raise TypeError("skill must be a dictionary")

        if "name" not in skill or not isinstance(skill["name"], str) or not skill["name"].strip():
            raise ValueError("skill must have a non-empty name")

        self.skills.append(skill)
        self.skills = self.skills[-self.max_skills:]

    def get_skills(self) -> list[dict]:
        """Return a copy of stored skills."""
        return list(self.skills)

    def add_reflection(self, reflection: str) -> None:
        """Store a self-evaluation reflection."""
        if not isinstance(reflection, str) or not reflection.strip():
            raise ValueError("reflection must be a non-empty string")

        self.reflections.append(reflection.strip())
        self.reflections = self.reflections[-self.max_reflections:]

    def get_reflections(self) -> list[str]:
        """Return a copy of stored reflections."""
        return list(self.reflections)

    def add_evaluation(self, evaluation: Evaluation) -> None:
        """Store an evaluation of the agent's performance."""
        if not isinstance(evaluation, Evaluation):
            raise TypeError("evaluation must be an Evaluation object")

        self.evaluations.append(evaluation)
        self.evaluations = self.evaluations[-self.max_evaluations:]

    def get_evaluations(self) -> list[str]:
        """Return a copy of stored evaluations."""
        return list(self.evaluations)

    def add_attempt(self, task_id: str, plan: Plan, tool_name: str | None, arguments: dict, observation: Any, evaluation: Evaluation) -> None:
        """Store an attempt for a given task."""
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not isinstance(plan, Plan):
            raise TypeError("plan must be a Plan object")
        if tool_name is not None and not isinstance(tool_name, str):
            raise TypeError("tool_name must be a string or None")
        if not isinstance(arguments, dict):
            raise TypeError("arguments must be a dict")
        if not isinstance(evaluation, Evaluation):
            raise TypeError("evaluation must be an Evaluation object")

        attempt = Attempt(
            task_id=task_id,
            plan=plan.to_dict(),
            tool_name=tool_name,
            arguments=arguments,
            observation=observation,
            evaluation_score=evaluation.score,
        )
        self.attempts[task_id].append(attempt)
        # Keep only the most recent attempts up to max_attempts_per_task
        if len(self.attempts[task_id]) > self.max_attempts_per_task:
            self.attempts[task_id] = self.attempts[task_id][-self.max_attempts_per_task:]

    def get_attempts(self, task_id: str) -> list[Attempt]:
        """Get all attempts for a given task."""
        return list(self.attempts.get(task_id, []))

    def get_best_attempt(self, task_id: str) -> Attempt | None:
        """Get the attempt with the highest evaluation score for a task."""
        attempts = self.attempts.get(task_id)
        if not attempts:
            return None
        best = max(attempts, key=lambda a: a.evaluation_score)
        # Return a copy to prevent accidental mutation of historical data
        return Attempt(**asdict(best))

    def compare_attempts(self, task_id: str, current_evaluation: float, success_threshold: float = 0.8) -> ComparisonResult:
        """Compare a current evaluation with previous attempts for a task.

        Returns a ComparisonResult containing:
        - current_score: the provided evaluation score
        - best_previous_score: highest score from previous attempts, or None if no prior attempts
        - score_delta: current_score - best_previous_score (0.0 if no prior attempts)
        - is_improvement: True if current_score > best_previous_score (or False if none or equal/lower)
        - meets_success_threshold: True if current_score >= success_threshold
        - attempt_count: total number of attempts recorded for this task (including this one? we count previous attempts only)
        """
        attempts = self.attempts.get(task_id, [])
        attempt_count = len(attempts)
        if attempt_count == 0:
            best_previous_score = None
            score_delta = 0.0
            is_improvement = False
        else:
            best_previous_score = max(a.evaluation_score for a in attempts)
            score_delta = current_evaluation - best_previous_score
            is_improvement = score_delta > 0.0
        meets_success_threshold = current_evaluation >= success_threshold
        return ComparisonResult(
            task_id=task_id,
            current_score=current_evaluation,
            best_previous_score=best_previous_score,
            score_delta=score_delta,
            is_improvement=is_improvement,
            meets_success_threshold=meets_success_threshold,
            attempt_count=attempt_count,
        )

    def build_context(self, current_message: str) -> str:
        """Build context including conversation, observations, skills, and reflections."""
        if not isinstance(current_message, str):
            raise TypeError("current_message must be a string")
        current_message = current_message.strip()
        if not current_message:
            raise ValueError("current_message cannot be empty")
        lines = ["Previous conversation:"]
        for message in self.messages:
            role = message["role"].capitalize()
            content = message["content"]
            lines.append(f"{role}: {content}")
        if self.tool_observations:
            lines.append("")
            lines.append("Tool observations:")
            for obs in self.tool_observations:
                lines.append(f"  {obs['tool']}: {obs['result']}")
        if self.skills:
            lines.append("")
            lines.append("Available skills:")
            for skill in self.skills:
                name = skill.get("name", "unknown")
                desc = skill.get("description", "")
                lines.append(f"  {name}: {desc}")
        if self.reflections:
            lines.append("")
            lines.append("Self-reflections:")
            for reflection in self.reflections:
                lines.append(f"  {reflection}")
        if self.evaluations:
            lines.append("")
            lines.append("Evaluations:")
            for evaluation in self.evaluations:
                lines.append(f"  {evaluation}")
        lines.extend([
            "",
            f"User: {current_message}",
            "",
            "Answer the user's latest message while considering the previous conversation, tool observations, available skills, self-reflections, and evaluations.",
        ])
        return "\n".join(lines)
