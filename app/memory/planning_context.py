"""Memory-Assisted Planning - Stage 30 Phase 8.

Structured memory context for planning without duplicating memory store.
"""

from dataclasses import dataclass, field
from typing import Any

from app.memory.enhanced import EnhancedMemory
from app.tools.capabilities import CapabilityCategory


@dataclass
class ToolReliability:
    """Reliability statistics for a tool."""
    tool_name: str
    total_attempts: int = 0
    successful_attempts: int = 0
    last_success: bool | None = None
    recent_failures: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_attempts == 0:
            return 1.0  # Unknown = optimistic
        return self.successful_attempts / self.total_attempts

    def record_attempt(self, success: bool, error: str | None = None) -> None:
        self.total_attempts += 1
        if success:
            self.successful_attempts += 1
            self.last_success = True
        else:
            self.last_success = False
            if error:
                self.recent_failures.append(error)
                self.recent_failures = self.recent_failures[-5:]  # Keep last 5


@dataclass
class PlanningMemoryContext:
    """Structured memory context for planning - advisory only."""
    relevant_successes: list[dict] = field(default_factory=list)
    relevant_failures: list[dict] = field(default_factory=list)
    tool_reliability: dict[str, ToolReliability] = field(default_factory=dict)
    useful_reflections: list[str] = field(default_factory=list)
    relevant_skills: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant_successes": self.relevant_successes,
            "relevant_failures": self.relevant_failures,
            "tool_reliability": {k: {
                "tool_name": v.tool_name,
                "total_attempts": v.total_attempts,
                "successful_attempts": v.successful_attempts,
                "success_rate": v.success_rate,
                "last_success": v.last_success,
                "recent_failures": v.recent_failures,
            } for k, v in self.tool_reliability.items()},
            "useful_reflections": self.useful_reflections,
            "relevant_skills": self.relevant_skills,
        }


class PlanningMemoryRetriever:
    """Retrieves relevant memory for planning without exposing full store."""

    def __init__(self, memory: EnhancedMemory):
        self.memory = memory

    def retrieve_context(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None = None,
        available_tools: list[str] | None = None,
    ) -> PlanningMemoryContext:
        """Retrieve relevant memory for a planning task."""
        context = PlanningMemoryContext()

        # Get relevant tool observations
        context.relevant_successes = self._get_relevant_successes(goal, required_capabilities)
        context.relevant_failures = self._get_relevant_failures(goal, required_capabilities)

        # Get tool reliability from attempts
        context.tool_reliability = self._get_tool_reliability(available_tools)

        # Get useful reflections
        context.useful_reflections = self._get_relevant_reflections(goal, required_capabilities)

        # Get relevant skills
        context.relevant_skills = self._get_relevant_skills(goal, required_capabilities)

        return context

    def _get_relevant_successes(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None,
    ) -> list[dict]:
        """Find successful attempts relevant to the goal."""
        # Use tool observations and evaluations
        successes = []
        for obs in self.memory.tool_observations[-20:]:  # Recent observations
            # Simple relevance: tool mentioned in goal or matches capability
            if self._is_relevant_to_goal(obs.get("tool", ""), goal, required_capabilities):
                successes.append({
                    "tool": obs["tool"],
                    "result": obs["result"],
                    "type": "observation",
                })
        return successes[:5]  # Limit

    def _get_relevant_failures(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None,
    ) -> list[dict]:
        """Find relevant failures from attempts."""
        failures = []
        for task_id, attempts in self.memory.attempts.items():
            for attempt in attempts[-3:]:  # Recent attempts per task
                if attempt.evaluation_score < 0.5:  # Failed attempt
                    if self._is_relevant_to_goal(attempt.tool_name or "", goal, required_capabilities):
                        failures.append({
                            "tool": attempt.tool_name,
                            "arguments": attempt.arguments,
                            "error": attempt.observation,
                            "score": attempt.evaluation_score,
                            "type": "failed_attempt",
                        })
        return failures[:3]  # Limit

    def _get_tool_reliability(self, available_tools: list[str] | None) -> dict[str, ToolReliability]:
        """Compute reliability statistics for available tools."""
        reliability = {}

        tools_to_check = available_tools or []
        # Add tools from attempts
        for task_id, attempts in self.memory.attempts.items():
            for attempt in attempts:
                if attempt.tool_name:
                    tools_to_check.append(attempt.tool_name)

        # Also add tools from observations
        for obs in self.memory.tool_observations:
            tools_to_check.append(obs["tool"])

        for tool_name in set(tools_to_check):
            rel = ToolReliability(tool_name=tool_name)
            for task_id, attempts in self.memory.attempts.items():
                for attempt in attempts:
                    if attempt.tool_name == tool_name:
                        success = attempt.evaluation_score >= 0.7
                        error = None if success else str(attempt.observation)
                        rel.record_attempt(success, error)
            reliability[tool_name] = rel

        return reliability

    def _get_relevant_reflections(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None,
    ) -> list[str]:
        """Get reflections relevant to the goal."""
        relevant = []
        goal_lower = goal.lower()

        for reflection in self.memory.reflections[-10:]:
            # Use reflection's task_type for relevance
            # Reflection is an object with better_future_strategy field
            if hasattr(reflection, 'better_future_strategy'):
                reflection_text = reflection.better_future_strategy.lower()
            elif isinstance(reflection, str):
                reflection_text = reflection.lower()
            else:
                reflection_text = str(reflection).lower()
                
            # Check if reflection relates to any required capability
            is_relevant = False
            if required_capabilities and hasattr(reflection, 'task_type'):
                # Check if reflection's task_type matches required capabilities
                for cap in required_capabilities:
                    if cap.value in reflection.task_type.lower():
                        is_relevant = True
                        break
            
            # Fallback to keyword overlap
            if not is_relevant:
                is_relevant = self._has_keyword_overlap(goal_lower, reflection_text)
                
            if is_relevant:
                relevant.append(reflection.better_future_strategy if hasattr(reflection, 'better_future_strategy') else str(reflection))

        return relevant[:5]  # Limit

    def _get_relevant_skills(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None,
    ) -> list[dict]:
        """Get skills relevant to the goal."""
        relevant = []
        goal_lower = goal.lower()

        for skill in self.memory.skills:
            skill_name = skill.get("name", "").lower()
            skill_desc = skill.get("description", "").lower()

            # Check if skill relates to goal or required capabilities
            if (any(kw in goal_lower for kw in [skill_name]) or
                self._has_keyword_overlap(goal_lower, skill_desc) or
                (required_capabilities and any(cat.value in skill_desc for cat in required_capabilities))):
                relevant.append(skill)

        return relevant[:5]  # Limit

    def _is_relevant_to_goal(
        self,
        tool_name: str,
        goal: str,
        required_capabilities: list[CapabilityCategory] | None,
    ) -> bool:
        """Check if a tool/observation is relevant to the goal."""
        if not tool_name:
            return False

        goal_lower = goal.lower()
        tool_lower = tool_name.lower()

        # Direct name match
        if tool_lower in goal_lower:
            return True

        # Category match
        if required_capabilities:
            from app.tools.capabilities import get_capability
            cap = get_capability(tool_name)
            if cap and any(cat in cap.categories for cat in required_capabilities):
                return True

        # Operation keywords in goal
        operation_keywords = {
            "calculator": ["calculate", "compute", "math", "arithmetic", "average", "percent"],
            "fs.read": ["read", "cat", "view", "show", "open"],
            "fs.write": ["write", "save", "create", "put", "store"],
            "fs.list": ["list", "ls", "dir", "show files"],
            "browser": ["browse", "navigate", "website", "page", "url", "web"],
            "web.search": ["search", "find", "look", "google"],
            "rag": ["knowledge", "ask", "query", "search", "find"],
            "terminal": ["run", "execute", "command", "shell"],
            "python": ["python", "code", "script", "execute"],
            "desktop": ["desktop", "window", "click", "type", "app"],
        }

        for tool_pattern, keywords in operation_keywords.items():
            if tool_pattern in tool_lower:
                if any(kw in goal_lower for kw in keywords):
                    return True

        return False

    def _has_keyword_overlap(self, text1: str, text2: str) -> bool:
        """Check for meaningful keyword overlap."""
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "should", "could", "may", "might", "must", "can", "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them", "what", "how", "when", "where", "why"}

        words1 = {w for w in text1.split() if len(w) > 2 and w not in stopwords}
        words2 = {w for w in text2.split() if len(w) > 2 and w not in stopwords}

        return len(words1 & words2) > 0