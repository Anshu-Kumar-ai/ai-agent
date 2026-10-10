"""Capability-Based Multi-Tool Planning - Stage 30 Phase 5-7.

Structured planning with capability requirements, dependencies, and explainable ranking.
"""

from dataclasses import dataclass, field
from typing import Any

from app.tools.capabilities import (
    ToolCapability,
    get_capability,
    get_capabilities_by_category,
    CapabilityCategory,
    SideEffectLevel,
)


@dataclass
class CapabilityRequirement:
    """A capability requirement derived from a user goal."""
    category: CapabilityCategory
    operation: str
    required_inputs: list[str] = field(default_factory=list)
    produces: list[str] = field(default_factory=list)
    risk: str = "medium"
    verification_needed: bool = True
    priority: int = 0  # Higher = more critical to goal

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "operation": self.operation,
            "required_inputs": self.required_inputs,
            "produces": self.produces,
            "risk": self.risk,
            "verification_needed": self.verification_needed,
            "priority": self.priority,
        }


@dataclass
class ToolCandidate:
    """A candidate tool with ranking information."""
    tool_name: str
    capability: ToolCapability
    matched_operations: list[str]
    compatibility_score: float
    risk_score: int
    availability: bool
    ranking_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "matched_operations": self.matched_operations,
            "compatibility_score": self.compatibility_score,
            "risk_score": self.risk_score,
            "availability": self.availability,
            "ranking_reasons": self.ranking_reasons,
        }


@dataclass
class PlanStep:
    """A step in a multi-step plan with dependencies."""
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    required_capabilities: list[str]
    dependencies: list[str] = field(default_factory=list)  # step_ids this step depends on
    produces: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "required_capabilities": self.required_capabilities,
            "dependencies": self.dependencies,
            "produces": self.produces,
            "reason": self.reason,
        }


class CapabilityPlanner:
    """Multi-tool capability-based planner with dependency resolution."""

    # Configuration constants
    MAX_CANDIDATE_CAPABILITIES = 8
    MAX_CANDIDATE_TOOLS = 5

    def __init__(self, available_tools: list[dict]):
        self.available_tools = available_tools
        self.tool_metadata = {tool["name"]: tool for tool in available_tools}

    def extract_requirements(self, message: str) -> list[CapabilityRequirement]:
        """Extract capability requirements from a natural language goal."""
        message_lower = message.lower()
        requirements = []

        # Operation keyword mapping to capabilities
        operation_keywords = {
            "arithmetic": ("computation", "arithmetic", ["expression"], ["result"]),
            "average": ("computation", "average", ["expression"], ["result"]),
            "percentage": ("computation", "percentage", ["expression"], ["result"]),
            "unit_conversion": ("computation", "unit_conversion", ["expression"], ["result"]),
            "current_time": ("system", "current_time", [], ["timestamp"]),
            "read": ("filesystem", "read", ["path"], ["content"]),
            "write": ("filesystem", "write", ["path", "content"], ["file"]),
            "list": ("filesystem", "list", ["path"], ["file_list"]),
            "move": ("filesystem", "move", ["src", "dst"], ["file"]),
            "execute": ("terminal", "execute", ["cmd"], ["output"]),
            "fetch": ("network", "fetch", ["url"], ["content"]),
            "search": ("knowledge", "search", ["query"], ["results"]),
            "code": ("code_execution", "execute", ["code"], ["result"]),
            "navigate": ("browser", "navigate", ["url", "session_id"], ["page_state"]),
            "click": ("browser", "click", ["session_id", "selector"], ["page_state"]),
            "type": ("browser", "type", ["session_id", "text"], ["page_state"]),
            "observe": ("browser", "observe", ["session_id"], ["page_state"]),
            "focus": ("desktop", "focus", ["window_id"], ["window_state"]),
            "click_desktop": ("desktop", "click", ["window_id", "control"], ["result"]),
            "type_desktop": ("desktop", "type", ["window_id", "text"], ["result"]),
            "rag_add": ("knowledge", "add", ["text"], ["stored"]),
            "rag_query": ("knowledge", "query", ["query"], ["results"]),
            "rag_stats": ("knowledge", "stats", [], ["stats"]),
        }

        # Detect operations from message
        for op, (cat_str, operation, inputs, produces) in operation_keywords.items():
            keywords = self._get_keywords_for_operation(op)
            if any(kw in message_lower for kw in keywords):
                try:
                    category = CapabilityCategory(cat_str)
                    requirements.append(CapabilityRequirement(
                        category=category,
                        operation=operation,
                        required_inputs=inputs,
                        produces=produces,
                        risk="low" if cat_str in ("computation", "system", "filesystem") else "medium",
                        verification_needed=True,
                        priority=self._priority_for_operation(op),
                    ))
                except ValueError:
                    pass

        # Sort by priority (highest first)
        requirements.sort(key=lambda r: -r.priority)
        return requirements

    def _get_keywords_for_operation(self, op: str) -> list[str]:
        """Get keywords for an operation."""
        keywords = {
            "arithmetic": ["calculate", "compute", "solve", "math", "arithmetic", "what is", "evaluate"],
            "average": ["average", "mean", "avg"],
            "percentage": ["percent", "percentage", "%"],
            "unit_conversion": ["convert", "conversion", "to mb", "to gb", "to kb"],
            "current_time": ["time", "date", "clock", "when"],
            "read": ["read", "cat", "view", "show", "display", "open file"],
            "write": ["write", "create", "save", "put", "make file", "save to", "store"],
            "list": ["list", "ls", "dir", "show files", "what files"],
            "move": ["move", "rename", "mv"],
            "execute": ["run", "execute", "command", "shell", "terminal"],
            "fetch": ["fetch", "download", "get", "http", "url"],
            "search": ["search", "find", "look", "web", "google"],
            "code": ["execute", "run", "python", "code", "script"],
            "navigate": ["navigate", "go to", "visit", "open", "browse"],
            "click": ["click", "press", "tap"],
            "type": ["type", "input", "fill", "enter text"],
            "observe": ["observe", "inspect", "what's on", "page state", "get page info"],
            "focus": ["focus", "activate", "bring to front"],
            "click_desktop": ["click", "press button"],
            "type_desktop": ["type", "enter text", "fill field"],
            "rag_add": ["add", "store", "save", "knowledge", "index", "remember"],
            "rag_query": ["ask", "query", "search", "find", "knowledge", "what", "who", "where", "when", "how", "why"],
            "rag_stats": ["stats", "statistics", "status", "size", "count", "how many"],
        }
        return keywords.get(op, [])

    def _priority_for_operation(self, op: str) -> int:
        """Priority for operation (higher = more critical)."""
        priorities = {
            "arithmetic": 10,
            "average": 10,
            "percentage": 10,
            "unit_conversion": 10,
            "write": 9,
            "read": 8,
            "list": 7,
            "navigate": 9,
            "click": 8,
            "type": 8,
            "observe": 7,
            "search": 8,
            "execute": 6,
            "code": 6,
            "fetch": 7,
            "current_time": 5,
            "focus": 6,
            "click_desktop": 6,
            "type_desktop": 6,
            "rag_add": 7,
            "rag_query": 8,
            "rag_stats": 5,
            "move": 6,
        }
        return priorities.get(op, 5)

    def discover_candidates(self, requirements: list[CapabilityRequirement]) -> list[ToolCandidate]:
        """Discover and rank candidate tools for requirements."""
        all_candidates = []

        for req in requirements:
            # Get capabilities matching the requirement
            caps = get_capabilities_by_category(req.category)
            caps = [c for c in caps if c.matches_operation(req.operation)]

            for cap in caps:
                # Check if tool is available
                tool_meta = self.tool_metadata.get(cap.name)
                if not tool_meta:
                    continue

                # Check environment availability
                available = self._check_environment(cap)

                # Calculate compatibility
                compat_score = self._calculate_compatibility(req, cap)
                risk_score = {"low": 0, "medium": 1, "high": 2}.get(cap.risk_level, 1)

                reasons = self._generate_ranking_reasons(req, cap, available)

                all_candidates.append(ToolCandidate(
                    tool_name=cap.name,
                    capability=cap,
                    matched_operations=[req.operation],
                    compatibility_score=compat_score,
                    risk_score=risk_score,
                    availability=available,
                    ranking_reasons=reasons,
                ))

        # Merge candidates for same tool (multiple requirements)
        merged = {}
        for cand in all_candidates:
            if cand.tool_name in merged:
                existing = merged[cand.tool_name]
                existing.matched_operations.extend(cand.matched_operations)
                existing.compatibility_score = max(existing.compatibility_score, cand.compatibility_score)
                existing.ranking_reasons.extend(cand.ranking_reasons)
            else:
                merged[cand.tool_name] = cand

        # Sort: available first, then compatibility, then lower risk
        sorted_candidates = sorted(
            merged.values(),
            key=lambda c: (-c.availability, -c.compatibility_score, c.risk_score)
        )

        # Apply limits
        return sorted_candidates[:self.MAX_CANDIDATE_TOOLS]

    def _check_environment(self, cap: ToolCapability) -> bool:
        """Check if tool's environment requirements are met."""
        # Simple check - in production could check actual availability
        # For now, assume all are available except desktop on non-Windows
        for req in cap.environment_requirements:
            if req == "windows" and not self._is_windows():
                return False
            if req == "playwright" and not self._has_playwright():
                return False
        return True

    def _is_windows(self) -> bool:
        import sys
        return sys.platform == "win32"

    def _has_playwright(self) -> bool:
        try:
            import playwright
            return True
        except ImportError:
            return False

    def _calculate_compatibility(self, req: CapabilityRequirement, cap: ToolCapability) -> float:
        """Calculate compatibility score (0-1)."""
        score = 0.0

        # Operation match
        if cap.matches_operation(req.operation):
            score += 0.5

        # Category match
        if cap.categories and req.category in cap.categories:
            score += 0.3

        # Parameter compatibility
        if req.required_inputs:
            matched = sum(1 for inp in req.required_inputs if inp in cap.required_parameters)
            score += 0.2 * (matched / len(req.required_inputs))

        return min(score, 1.0)

    def _generate_ranking_reasons(self, req: CapabilityRequirement, cap: ToolCapability, available: bool) -> list[str]:
        """Generate human-readable ranking reasons."""
        reasons = []

        if cap.matches_operation(req.operation):
            reasons.append(f"operation '{req.operation}' matched")

        if req.category in cap.categories:
            reasons.append(f"category '{req.category.value}' matched")

        if req.required_inputs:
            matched = [inp for inp in req.required_inputs if inp in cap.required_parameters]
            if matched:
                reasons.append(f"required parameters available: {', '.join(matched)}")

        if cap.supports_verification:
            reasons.append("supports verification")

        if cap.idempotent:
            reasons.append("idempotent")

        if cap.side_effect_level == SideEffectLevel.NONE:
            reasons.append("no side effects")

        if available:
            reasons.append("environment available")
        else:
            reasons.append("environment may not be available")

        return reasons

    def build_plan(self, message: str) -> list[PlanStep]:
        """Build a multi-step plan with dependencies."""
        requirements = self.extract_requirements(message)
        if not requirements:
            return []

        candidates = self.discover_candidates(requirements)
        if not candidates:
            return []

        # Build steps from candidates
        steps = []
        step_counter = 0
        produced_outputs = set()

        for req in requirements:
            # Find best candidate for this requirement
            best_cand = None
            for cand in candidates:
                if req.operation in cand.matched_operations:
                    best_cand = cand
                    break

            if not best_cand:
                continue

            step_counter += 1
            step_id = f"step_{step_counter}"

            # Determine dependencies - which produced outputs does this need?
            deps = []
            for inp in req.required_inputs:
                for i, existing_step in enumerate(steps):
                    # Check if this step produces something that matches the required input
                    # fs.write needs "content" which could come from calculator's "result"
                    if inp in existing_step.produces:
                        deps.append(existing_step.step_id)
                    # Special case: calculator produces "result" which can be used as "content"
                    elif inp == "content" and "result" in existing_step.produces:
                        deps.append(existing_step.step_id)
                    # Special case: calculator produces "result" which can be used as "expression" for another calc
                    elif inp == "expression" and "result" in existing_step.produces:
                        deps.append(existing_step.step_id)

            # Build arguments (simplified - in practice would extract from message)
            arguments = self._build_arguments(best_cand, req, message, produced_outputs)

            step = PlanStep(
                step_id=step_id,
                tool_name=best_cand.tool_name,
                arguments=arguments,
                required_capabilities=[req.operation],
                dependencies=deps,
                produces=req.produces,
                reason=f"Execute {req.operation} using {best_cand.tool_name}",
            )

            steps.append(step)
            produced_outputs.update(req.produces)

        return steps

    def _build_arguments(self, candidate: ToolCandidate, req: CapabilityRequirement,
                         message: str, produced_outputs: set) -> dict[str, Any]:
        """Build arguments for a tool call."""
        args = {}

        # Extract values from message (simplified)
        import re

        # For calculator-like tools
        if "expression" in candidate.capability.required_parameters:
            expression = self._extract_expression(message)
            if expression:
                args["expression"] = expression

        # For file operations
        if "path" in candidate.capability.required_parameters:
            # Try to extract file path from message
            pass  # Would need more sophisticated extraction

        # For browser operations
        if "url" in candidate.capability.required_parameters:
            pass  # Would extract URL

        # For session_id, use placeholder
        if "session_id" in candidate.capability.required_parameters:
            args["session_id"] = "default"

        return args

    def _extract_expression(self, message: str) -> str | None:
        allowed = set("0123456789+-*/().% ")
        expression = "".join(c for c in message if c in allowed).strip()
        if not expression or not any(c.isdigit() for c in expression):
            return None
        return expression.rstrip(".")

    def validate_plan(self, steps: list[PlanStep]) -> tuple[bool, str]:
        """Validate a plan for correctness."""
        if not steps:
            return False, "Empty plan"

        step_ids = {s.step_id for s in steps}

        # Check for unknown tools
        for step in steps:
            if step.tool_name not in self.tool_metadata:
                return False, f"Unknown tool: {step.tool_name}"

        # Check for circular dependencies
        if self._has_circular_dependency(steps):
            return False, "Circular dependency detected"

        # Check for missing dependencies
        for step in steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    return False, f"Missing dependency: {dep}"

        # Check for disconnected steps (no dependency path to goal)
        # Simplified: every step should either have deps or be first
        pass

        return True, "Valid"

    def _has_circular_dependency(self, steps: list[PlanStep]) -> bool:
        """Detect circular dependencies using DFS."""
        graph = {s.step_id: s.dependencies for s in steps}
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if dfs(node):
                    return True
        return False


def build_multi_step_plan(message: str, available_tools: list[dict]) -> list[PlanStep]:
    """Convenience function to build a multi-step plan."""
    planner = CapabilityPlanner(available_tools)
    steps = planner.build_plan(message)
    valid, reason = planner.validate_plan(steps)
    if not valid:
        raise ValueError(f"Plan validation failed: {reason}")
    return steps