"""Skill System - Stage 30 Phase 9.

Reusable capability/workflow patterns with safety boundaries.
"""

from dataclasses import dataclass, field
from typing import Any

from app.tools.capabilities import CapabilityCategory


@dataclass
class Skill:
    """A reusable skill representing a capability/workflow pattern."""
    name: str
    intent: str
    required_capabilities: list[CapabilityCategory] = field(default_factory=list)
    workflow: list[dict] = field(default_factory=list)  # Steps: tool, args_template, produces
    constraints: list[str] = field(default_factory=list)
    verification_strategy: str = "standard"  # "standard", "strict", "none"
    success_history: list[dict] = field(default_factory=list)
    usage_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "intent": self.intent,
            "required_capabilities": [c.value for c in self.required_capabilities],
            "workflow": self.workflow,
            "constraints": self.constraints,
            "verification_strategy": self.verification_strategy,
            "success_history": self.success_history,
            "usage_metadata": self.usage_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        return cls(
            name=data["name"],
            intent=data["intent"],
            required_capabilities=[CapabilityCategory(c) for c in data.get("required_capabilities", [])],
            workflow=data.get("workflow", []),
            constraints=data.get("constraints", []),
            verification_strategy=data.get("verification_strategy", "standard"),
            success_history=data.get("success_history", []),
            usage_metadata=data.get("usage_metadata", {}),
        )

    def matches_intent(self, goal: str, required_capabilities: list[CapabilityCategory]) -> float:
        """Calculate how well this skill matches the goal (0-1)."""
        score = 0.0
        goal_lower = goal.lower()

        # Intent keyword match
        intent_words = self.intent.lower().split()
        for word in intent_words:
            if len(word) > 2 and word in goal_lower:
                score += 0.2

        # Capability match
        if required_capabilities:
            matched = sum(1 for cap in required_capabilities if cap in self.required_capabilities)
            if self.required_capabilities:
                score += 0.5 * (matched / len(self.required_capabilities))

        # Success history bonus
        if self.success_history:
            recent_success = sum(1 for s in self.success_history[-5:] if s.get("success", False))
            score += 0.3 * (recent_success / min(5, len(self.success_history)))

        return min(score, 1.0)

    def is_applicable(
        self,
        goal: str,
        available_tools: list[str],
        current_permissions: list[str],
        environment: dict,
    ) -> tuple[bool, list[str]]:
        """Check if skill is applicable given current constraints."""
        reasons = []

        # Check required capabilities have available tools
        for cap in self.required_capabilities:
            # This would need a tool registry check - simplified
            pass

        # Check constraints
        for constraint in self.constraints:
            if constraint == "no_network" and environment.get("network_required", False):
                return False, [f"Constraint violated: {constraint}"]
            if constraint == "windows_only" and not environment.get("is_windows", False):
                return False, [f"Constraint violated: {constraint}"]

        # Check verification strategy doesn't bypass safety
        if self.verification_strategy == "none":
            reasons.append("Warning: skill has no verification strategy")

        return True, reasons

    def record_success(self, task_id: str, steps: list[str]) -> None:
        """Record a successful usage."""
        self.success_history.append({
            "task_id": task_id,
            "steps": steps,
            "success": True,
        })
        self.success_history = self.success_history[-20:]  # Keep last 20

    def record_failure(self, task_id: str, error: str) -> None:
        """Record a failed usage."""
        self.success_history.append({
            "task_id": task_id,
            "error": error,
            "success": False,
        })
        self.success_history = self.success_history[-20:]


class SkillRegistry:
    """Manages available skills."""

    def __init__(self, max_skills: int = 100):
        self.skills: dict[str, Skill] = {}
        self.max_skills = max_skills

    def register(self, skill: Skill) -> None:
        """Register a skill."""
        if not isinstance(skill, Skill):
            raise TypeError("skill must be a Skill object")

        if skill.name in self.skills:
            raise ValueError(f"Skill already registered: {skill.name}")

        if len(self.skills) >= self.max_skills:
            # Remove least recently used (simplified)
            oldest = min(self.skills.values(), key=lambda s: s.usage_metadata.get("last_used", 0))
            del self.skills[oldest.name]

        self.skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.skills.get(name)

    def find_relevant(
        self,
        goal: str,
        required_capabilities: list[CapabilityCategory],
        available_tools: list[str],
        current_permissions: list[str],
        environment: dict,
    ) -> list[Skill]:
        """Find skills relevant to the goal, ranked by match score."""
        candidates = []

        for skill in self.skills.values():
            # Check applicability
            applicable, reasons = skill.is_applicable(goal, available_tools, current_permissions, environment)
            if not applicable:
                continue

            # Calculate match score
            score = skill.matches_intent(goal, required_capabilities)
            if score > 0:
                skill.usage_metadata["last_used"] = __import__("time").time()
                candidates.append((score, skill))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: -x[0])
        return [s for _, s in candidates]


# Built-in skills
BUILTIN_SKILLS = {
    "calculate_and_save": Skill(
        name="calculate_and_save",
        intent="Calculate a value and save it to a file",
        required_capabilities=[CapabilityCategory.COMPUTATION, CapabilityCategory.FILESYSTEM],
        workflow=[
            {"tool": "calculator", "args_template": {"expression": "{expression}"}, "produces": ["result"]},
            {"tool": "fs.write", "args_template": {"path": "{path}", "content": "{result}"}, "produces": ["file"]},
        ],
        constraints=["path_within_workspace"],
        verification_strategy="standard",
    ),
    "research_and_save": Skill(
        name="research_and_save",
        intent="Search for information and save findings",
        required_capabilities=[CapabilityCategory.KNOWLEDGE, CapabilityCategory.FILESYSTEM],
        workflow=[
            {"tool": "web.search", "args_template": {"query": "{query}"}, "produces": ["results"]},
            {"tool": "fs.write", "args_template": {"path": "{path}", "content": "{results}"}, "produces": ["file"]},
        ],
        constraints=["network_required"],
        verification_strategy="standard",
    ),
    "browser_extract_and_calculate": Skill(
        name="browser_extract_and_calculate",
        intent="Extract data from webpage, calculate, and save",
        required_capabilities=[CapabilityCategory.BROWSER, CapabilityCategory.COMPUTATION, CapabilityCategory.FILESYSTEM],
        workflow=[
            {"tool": "browser_agent.execute", "args_template": {"goal": "extract {data} from {url}"}, "produces": ["extracted_data"]},
            {"tool": "calculator", "args_template": {"expression": "{calculation}"}, "produces": ["result"]},
            {"tool": "fs.write", "args_template": {"path": "{path}", "content": "{result}"}, "produces": ["file"]},
        ],
        constraints=["playwright_required", "network_required"],
        verification_strategy="strict",
    ),
    "file_read_and_process": Skill(
        name="file_read_and_process",
        intent="Read a file, process its content, and save result",
        required_capabilities=[CapabilityCategory.FILESYSTEM, CapabilityCategory.COMPUTATION],
        workflow=[
            {"tool": "fs.read", "args_template": {"path": "{path}"}, "produces": ["content"]},
            {"tool": "calculator", "args_template": {"expression": "{processing}"}, "produces": ["result"]},
            {"tool": "fs.write", "args_template": {"path": "{output_path}", "content": "{result}"}, "produces": ["file"]},
        ],
        constraints=["path_within_workspace"],
        verification_strategy="standard",
    ),
}


def get_skill(name: str) -> Skill | None:
    """Get a built-in skill by name."""
    return BUILTIN_SKILLS.get(name)


def get_all_skills() -> list[Skill]:
    """Get all built-in skills."""
    return list(BUILTIN_SKILLS.values())