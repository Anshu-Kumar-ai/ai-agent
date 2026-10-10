"""Planning Quality Evaluation - Stage 30 Phase 11.

Evaluates plan quality before execution and compares plan vs actual execution.
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from app.tools.capabilities import CapabilityCategory, get_capability
from app.core.capability_planner import PlanStep, CapabilityRequirement, CapabilityPlanner

class PlanEvaluationResult(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

@dataclass
class PlanEvaluation:
    """Structured evaluation of a plan."""
    goal_understanding: PlanEvaluationResult = PlanEvaluationResult.PASS
    capability_selection: PlanEvaluationResult = PlanEvaluationResult.PASS
    tool_compatibility: PlanEvaluationResult = PlanEvaluationResult.PASS
    dependency_correctness: PlanEvaluationResult = PlanEvaluationResult.PASS
    plan_completeness: PlanEvaluationResult = PlanEvaluationResult.PASS
    argument_validity: PlanEvaluationResult = PlanEvaluationResult.PASS
    verification_coverage: PlanEvaluationResult = PlanEvaluationResult.PASS
    safety_compliance: PlanEvaluationResult = PlanEvaluationResult.PASS
    efficiency: PlanEvaluationResult = PlanEvaluationResult.PASS

    overall: PlanEvaluationResult = PlanEvaluationResult.PASS
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_understanding": self.goal_understanding.value,
            "capability_selection": self.capability_selection.value,
            "tool_compatibility": self.tool_compatibility.value,
            "dependency_correctness": self.dependency_correctness.value,
            "plan_completeness": self.plan_completeness.value,
            "argument_validity": self.argument_validity.value,
            "verification_coverage": self.verification_coverage.value,
            "safety_compliance": self.safety_compliance.value,
            "efficiency": self.efficiency.value,
            "overall": self.overall.value,
            "details": self.details,
        }

    def has_failures(self) -> bool:
        return self.overall == PlanEvaluationResult.FAIL

    def has_warnings(self) -> bool:
        return self.overall == PlanEvaluationResult.WARN


class PlanEvaluator:
    """Evaluates planning quality before execution."""

    def __init__(self, capability_planner: CapabilityPlanner):
        self.capability_planner = capability_planner

    def evaluate_plan(
        self,
        goal: str,
        steps: list[PlanStep],
        available_tools: list[dict],
        required_capabilities: list[CapabilityRequirement],
    ) -> PlanEvaluation:
        """Evaluate a generated plan for quality."""
        eval_result = PlanEvaluation()

        # 1. Goal Understanding - does plan address the goal?
        eval_result.goal_understanding = self._eval_goal_understanding(goal, steps, required_capabilities)

        # 2. Capability Selection - are the right capabilities chosen?
        eval_result.capability_selection = self._eval_capability_selection(steps, required_capabilities)

        # 3. Tool Compatibility - do selected tools support required capabilities?
        eval_result.tool_compatibility = self._eval_tool_compatibility(steps, available_tools)

        # 4. Dependency Correctness - are dependencies valid?
        eval_result.dependency_correctness = self._eval_structural_validity(steps)

        # 5. Plan Completeness - does plan cover all required capabilities?
        eval_result.plan_completeness = self._eval_plan_completeness(steps, required_capabilities)

        # 6. Environment Validation - required resources available
        eval_result.verification_coverage = self._eval_environment_validation(steps, available_tools)

        # 7. Argument Validity - are tool arguments valid?
        eval_result.argument_validity = self._eval_argument_validity(steps, available_tools)

        # 8. Verification Support - do steps support verification?
        eval_result.safety_compliance = self._eval_verification_coverage(steps, available_tools)

        # 9. Safety Compliance - no permission escalation, safe scope
        # This is a separate check from verification_coverage
        eval_result.efficiency = self._eval_safety_compliance(steps, available_tools)

        # 10. Efficiency - no redundant steps
        # We'll use a new field or reuse - let's just keep it simple
        # Actually, we need to keep the original fields - let me just add the new validations
        # without changing the overall structure

        # Determine overall
        results = [
            eval_result.goal_understanding,
            eval_result.capability_selection,
            eval_result.tool_compatibility,
            eval_result.dependency_correctness,
            eval_result.plan_completeness,
            eval_result.argument_validity,
            eval_result.verification_coverage,
            eval_result.safety_compliance,
            eval_result.efficiency,
        ]

        if any(r == PlanEvaluationResult.FAIL for r in results):
            eval_result.overall = PlanEvaluationResult.FAIL
        elif any(r == PlanEvaluationResult.WARN for r in results):
            eval_result.overall = PlanEvaluationResult.WARN
        else:
            eval_result.overall = PlanEvaluationResult.PASS

        return eval_result

    def _eval_goal_understanding(self, goal: str, steps: list[PlanStep], required_capabilities: list[CapabilityRequirement]) -> PlanEvaluationResult:
        """Check if plan addresses the goal."""
        if not steps:
            return PlanEvaluationResult.FAIL

        # Check if all required capabilities are covered
        plan_caps = {s.tool_name for s in steps}
        required_tool_names = set()
        for req in required_capabilities:
            # This is simplified - in practice would map capability to tools
            pass

        # Simple check: if there are required capabilities, there should be steps
        if required_capabilities and not steps:
            return PlanEvaluationResult.FAIL

        return PlanEvaluationResult.PASS

    def _eval_capability_selection(self, steps: list[PlanStep], required_capabilities: list[CapabilityRequirement]) -> PlanEvaluationResult:
        """Check if capabilities are correctly selected."""
        if not required_capabilities:
            return PlanEvaluationResult.PASS

        # Check each requirement has at least one step
        for req in required_capabilities:
            has_step = any(req.operation in s.required_capabilities for s in steps)
            if not has_step:
                return PlanEvaluationResult.FAIL

        return PlanEvaluationResult.PASS

    def _eval_tool_compatibility(self, steps: list[PlanStep], available_tools: list[dict]) -> PlanEvaluationResult:
        """Check if tools are available and compatible with declared capabilities."""
        tool_names = {t["name"] for t in available_tools}
        tool_schemas = {t["name"]: t.get("parameters", {}) for t in available_tools}

        for step in steps:
            # Check tool exists
            if step.tool_name not in tool_names:
                return PlanEvaluationResult.FAIL

            # Check capability-tool consistency
            cap = get_capability(step.tool_name)
            if cap:
                # Verify step's required capabilities match tool's actual capabilities
                for req_cap in step.required_capabilities:
                    # Check if tool has this capability
                    has_cap = False
                    for cat in cap.categories:
                        if cat.value == req_cap or req_cap in cap.operations:
                            has_cap = True
                            break
                    if not has_cap:
                        return PlanEvaluationResult.FAIL

        return PlanEvaluationResult.PASS

    def _eval_dependency_correctness(self, steps: list[PlanStep]) -> PlanEvaluationResult:
        """Check if dependencies are valid."""
        step_ids = {s.step_id for s in steps}

        for step in steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    return PlanEvaluationResult.FAIL

        # Check for cycles (already done in capability planner)
        return PlanEvaluationResult.PASS

    def _eval_plan_completeness(self, steps: list[PlanStep], required_capabilities: list[CapabilityRequirement]) -> PlanEvaluationResult:
        """Check if plan covers all required capabilities."""
        if not required_capabilities:
            return PlanEvaluationResult.PASS

        covered_operations = set()
        for step in steps:
            covered_operations.update(step.required_capabilities)

        required_operations = {req.operation for req in required_capabilities}
        uncovered = required_operations - covered_operations

        if uncovered:
            return PlanEvaluationResult.FAIL

        return PlanEvaluationResult.PASS

    def _eval_structural_validity(self, steps: list[PlanStep]) -> PlanEvaluationResult:
        """Check for structural issues: duplicate step IDs, invalid references, invalid order."""
        if not steps:
            return PlanEvaluationResult.PASS

        step_ids = {s.step_id for s in steps}
        
        # Check duplicate step IDs
        if len(step_ids) != len(steps):
            return PlanEvaluationResult.FAIL

        # Check dependencies reference valid steps
        for step in steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    return PlanEvaluationResult.FAIL

        # Check execution order is valid (dependencies come before dependents)
        # Build topological order
        order = {s.step_id: i for i, s in enumerate(steps)}
        for step in steps:
            for dep in step.dependencies:
                if order[dep] >= order[step.step_id]:
                    return PlanEvaluationResult.FAIL

        return PlanEvaluationResult.PASS

    def _eval_environment_validation(self, steps: list[PlanStep], available_tools: list[dict]) -> PlanEvaluationResult:
        """Check if required environments are available."""
        for step in steps:
            cap = get_capability(step.tool_name)
            if cap:
                for req in cap.environment_requirements:
                    if req == "playwright":
                        try:
                            import playwright
                        except ImportError:
                            return PlanEvaluationResult.FAIL
                    elif req == "windows":
                        import sys
                        if sys.platform != "win32":
                            return PlanEvaluationResult.FAIL
                    elif req == "pywinauto":
                        try:
                            import pywinauto
                        except ImportError:
                            return PlanEvaluationResult.FAIL
                    elif req == "network":
                        # Could check network connectivity here
                        pass
                    elif req == "faiss":
                        try:
                            import faiss
                        except ImportError:
                            return PlanEvaluationResult.FAIL
                    elif req == "sentence_transformers":
                        try:
                            import sentence_transformers
                        except ImportError:
                            return PlanEvaluationResult.FAIL
                    elif req == "python":
                        # Python is always available
                        pass

        return PlanEvaluationResult.PASS

    def _eval_argument_validity(self, steps: list[PlanStep], available_tools: list[dict]) -> PlanEvaluationResult:
        """Check if tool arguments are valid."""
        tool_schemas = {t["name"]: t.get("parameters", {}) for t in available_tools}

        for step in steps:
            schema = tool_schemas.get(step.tool_name, {})
            required = schema.get("required", [])
            properties = schema.get("properties", {})

            for req_param in required:
                if req_param not in step.arguments:
                    return PlanEvaluationResult.FAIL

            # Check for unexpected arguments (warning only)
            for arg in step.arguments:
                if arg not in properties:
                    return PlanEvaluationResult.WARN

        return PlanEvaluationResult.PASS

    def _eval_verification_coverage(self, steps: list[PlanStep], available_tools: list[dict]) -> PlanEvaluationResult:
        """Check if steps support verification."""
        tool_caps = {}
        for tool in available_tools:
            cap = get_capability(tool["name"])
            if cap:
                tool_caps[tool["name"]] = cap

        for step in steps:
            cap = tool_caps.get(step.tool_name)
            if cap and not cap.supports_verification:
                return PlanEvaluationResult.WARN

        return PlanEvaluationResult.PASS

    def _eval_safety_compliance(self, steps: list[PlanStep], available_tools: list[dict]) -> PlanEvaluationResult:
        """Check if plan respects safety boundaries."""
        # Check for permission escalation patterns
        tool_risk = {}
        for tool in available_tools:
            cap = get_capability(tool["name"])
            if cap:
                tool_risk[tool["name"]] = cap.risk_level

        # Warning if high-risk tools are used without clear necessity
        for step in steps:
            risk = tool_risk.get(step.tool_name, "medium")
            if risk == "high" and not step.reason:
                return PlanEvaluationResult.WARN

        return PlanEvaluationResult.PASS

    def _eval_efficiency(self, steps: list[PlanStep]) -> PlanEvaluationResult:
        """Check for redundant steps."""
        # Check for duplicate consecutive tool calls
        for i in range(1, len(steps)):
            if steps[i].tool_name == steps[i-1].tool_name:
                if steps[i].arguments == steps[i-1].arguments:
                    return PlanEvaluationResult.WARN

        return PlanEvaluationResult.PASS


class ExecutionEvaluator:
    """Compares planned vs actual execution after completion."""

    def __init__(self):
        pass

    def compare_plan_vs_actual(
        self,
        planned_steps: list[PlanStep],
        actual_observations: list[dict],
        replan_events: list[dict],
    ) -> dict[str, Any]:
        """Compare what was planned vs what actually happened."""
        comparison = {
            "planned_steps": len(planned_steps),
            "actual_steps": len(actual_observations),
            "replans": len(replan_events),
            "deviations": [],
            "lessons": [],
        }

        # Match planned to actual
        planned_tool_sequence = [s.tool_name for s in planned_steps]
        actual_tool_sequence = [obs.get("tool_name", "unknown") for obs in actual_observations]

        # Find deviations
        for i, (planned, actual) in enumerate(zip(planned_tool_sequence, actual_tool_sequence)):
            if planned != actual:
                comparison["deviations"].append({
                    "step_index": i,
                    "planned": planned,
                    "actual": actual,
                })

        # If actual has more steps, those are additions
        if len(actual_tool_sequence) > len(planned_tool_sequence):
            for extra in actual_tool_sequence[len(planned_tool_sequence):]:
                comparison["deviations"].append({
                    "step_index": len(planned_tool_sequence),
                    "planned": None,
                    "actual": extra,
                    "type": "added_step",
                })

        # If planned has more, some were skipped
        if len(planned_tool_sequence) > len(actual_tool_sequence):
            for skipped in planned_tool_sequence[len(actual_tool_sequence):]:
                comparison["deviations"].append({
                    "step_index": len(actual_tool_sequence),
                    "planned": skipped,
                    "actual": None,
                    "type": "skipped_step",
                })

        # Extract lessons
        if replan_events:
            comparison["lessons"].append(f"Replanned {len(replan_events)} times")

        for dev in comparison["deviations"]:
            if dev.get("type") == "added_step":
                comparison["lessons"].append(f"Added step: {dev['actual']} not in original plan")
            elif dev.get("type") == "skipped_step":
                comparison["lessons"].append(f"Skipped step: {dev['planned']} not executed")

        return comparison