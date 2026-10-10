"""Browser Planner - Stage 18: Computer Use Foundation.

Responsible for planning browser actions based on task goals and observed state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.tools.browser_executor import (
    ActionResult,
    ActionType,
    BrowserAction,
    BrowserActionExecutor,
)
from app.tools.browser_observer import BrowserObserver
from app.tools.browser_state import (
    BrowserSession,
    BrowserTab,
)


class PlanStatus(Enum):
    """Status of a browser plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_RECOVERY = "requires_recovery"


@dataclass
class PlanStep:
    """A single step in a browser plan."""
    step_id: str
    action: BrowserAction
    description: str
    expected_outcome: str
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on
    status: PlanStatus = PlanStatus.PENDING
    result: ActionResult | None = None
    retry_count: int = 0
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action": self.action.to_dict(),
            "description": self.description,
            "expected_outcome": self.expected_outcome,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result.to_dict() if self.result else None,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }


@dataclass
class BrowserPlan:
    """A complete plan for achieving a browser task."""
    plan_id: str
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    current_step_index: int = 0
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_step_index": self.current_step_index,
            "context": self.context,
        }

    def get_next_step(self) -> PlanStep | None:
        """Get the next executable step (dependencies met)."""
        for step in self.steps:
            if step.status == PlanStatus.PENDING:
                # Check dependencies
                deps_met = all(
                    any(s.step_id == dep and s.status == PlanStatus.COMPLETED for s in self.steps)
                    for dep in step.depends_on
                )
                if deps_met:
                    return step
        return None

    def is_complete(self) -> bool:
        """Check if all steps are completed."""
        return all(s.status == PlanStatus.COMPLETED for s in self.steps)

    def has_failed(self) -> bool:
        """Check if any step has failed permanently."""
        return any(s.status == PlanStatus.FAILED for s in self.steps)


class BrowserPlanner:
    """Plans browser actions to achieve goals using LLM reasoning."""

    def __init__(self, session: BrowserSession, observer: BrowserObserver, model_client=None):
        self.session = session
        self.observer = observer
        self.model_client = model_client  # LLM client for planning

    def create_plan(self, goal: str, context: dict[str, Any] | None = None) -> BrowserPlan:
        """Create a plan to achieve the goal."""
        plan = BrowserPlan(
            plan_id=f"plan_{int(time.time())}_{id(self)}",
            goal=goal,
            context=context or {}
        )

        # Observe current state
        active_tab = self.session.get_active_tab()

        # Use LLM to decompose goal into steps
        if self.model_client:
            steps = self._llm_plan(goal, active_tab, context)
        else:
            steps = self._heuristic_plan(goal, active_tab, context)

        plan.steps = steps
        return plan

    def _llm_plan(self, goal: str, tab: BrowserTab | None, context: dict | None) -> list[PlanStep]:
        """Use LLM to create a detailed plan."""
        # This would use the model client to generate a plan
        # For now, fall back to heuristic
        return self._heuristic_plan(goal, tab, context)

    def _heuristic_plan(self, goal: str, tab: BrowserTab | None, context: dict | None) -> list[PlanStep]:
        """Create a plan using heuristics."""
        steps = []
        goal_lower = goal.lower()

        # Step 1: Navigate if needed
        if "search" in goal_lower or "find" in goal_lower or "go to" in goal_lower:
            # Extract URL or search query
            query = self._extract_search_query(goal)
            if query:
                steps.append(PlanStep(
                    step_id="step_1",
                    action=BrowserAction(
                        action_type=ActionType.NAVIGATE,
                        url=f"https://www.google.com/search?q={query}",
                    ),
                    description=f"Search for: {query}",
                    expected_outcome="Search results page loaded"
                ))

        # Step 2: Click first result
        if "click" in goal_lower or "open" in goal_lower or "visit" in goal_lower:
            steps.append(PlanStep(
                step_id=f"step_{len(steps)+1}",
                action=BrowserAction(
                    action_type=ActionType.CLICK,
                    selector="a:first-of-type",  # Simplified
                ),
                description="Click first result",
                expected_outcome="Target page loaded",
                depends_on=[steps[-1].step_id] if steps else []
            ))

        # Step 3: Extract information
        if "extract" in goal_lower or "get" in goal_lower or "compare" in goal_lower:
            steps.append(PlanStep(
                step_id=f"step_{len(steps)+1}",
                action=BrowserAction(
                    action_type=ActionType.WAIT,
                    timeout=5000,
                ),
                description="Wait for page to load",
                expected_outcome="Page fully loaded",
                depends_on=[steps[-1].step_id] if steps else []
            ))

        # Step 4: Screenshot for verification
        steps.append(PlanStep(
            step_id=f"step_{len(steps)+1}",
            action=BrowserAction(
                action_type=ActionType.SCREENSHOT,
            ),
            description="Take screenshot for verification",
            expected_outcome="Screenshot captured",
            depends_on=[steps[-1].step_id] if steps else []
        ))

        return steps

    def _extract_search_query(self, goal: str) -> str | None:
        """Extract search query from goal."""
        # Simple extraction - in practice would use NLP
        import re
        # Look for quoted strings
        quotes = re.findall(r'"([^"]*)"', goal)
        if quotes:
            return quotes[0]
        # Look for "search for X" or "find X"
        patterns = [
            r'search for (.+?)(?:\.|,|$)',
            r'find (.+?)(?:\.|,|$)',
            r'look for (.+?)(?:\.|,|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, goal, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def refine_plan(self, plan: BrowserPlan, failed_step: PlanStep, error: str) -> BrowserPlan:
        """Refine a plan after a failure (recovery planning)."""
        # Add recovery steps before the failed step
        recovery_steps = self._create_recovery_steps(failed_step, error)

        # Insert recovery steps before failed step
        insert_idx = plan.steps.index(failed_step)
        plan.steps = plan.steps[:insert_idx] + recovery_steps + plan.steps[insert_idx:]

        # Mark failed step for retry
        failed_step.retry_count += 1
        if failed_step.retry_count <= failed_step.max_retries:
            failed_step.status = PlanStatus.PENDING
        else:
            failed_step.status = PlanStatus.FAILED

        return plan

    def _create_recovery_steps(self, failed_step: PlanStep, error: str) -> list[PlanStep]:
        """Create recovery steps based on the error."""
        recovery = []
        error_lower = error.lower()

        if "cookie" in error_lower or "consent" in error_lower:
            recovery.append(PlanStep(
                step_id=f"recovery_{int(time.time())}_1",
                action=BrowserAction(
                    action_type=ActionType.CLICK,
                    selector="button:has-text('Accept'), button:has-text('Allow'), [id*='accept'], [class*='accept']",
                ),
                description="Accept cookie consent dialog",
                expected_outcome="Cookie dialog dismissed",
            ))

        if "modal" in error_lower or "popup" in error_lower or "overlay" in error_lower:
            recovery.append(PlanStep(
                step_id=f"recovery_{int(time.time())}_2",
                action=BrowserAction(
                    action_type=ActionType.CLICK,
                    selector="[role='dialog'] button:has-text('Close'), [role='dialog'] [aria-label='Close'], .modal-close, .popup-close",
                ),
                description="Close modal/popup dialog",
                expected_outcome="Modal dismissed",
            ))

        if "not found" in error_lower or "element not found" in error_lower:
            recovery.append(PlanStep(
                step_id=f"recovery_{int(time.time())}_3",
                action=BrowserAction(
                    action_type=ActionType.WAIT,
                    timeout=3000,
                ),
                description="Wait for element to appear",
                expected_outcome="Element appears",
            ))
            recovery.append(PlanStep(
                step_id=f"recovery_{int(time.time())}_4",
                action=BrowserAction(
                    action_type=ActionType.SCROLL,
                    direction="down",
                    amount=500,
                ),
                description="Scroll to reveal more elements",
                expected_outcome="More content visible",
            ))

        if "timeout" in error_lower or "navigation" in error_lower:
            recovery.append(PlanStep(
                step_id=f"recovery_{int(time.time())}_5",
                action=BrowserAction(
                    action_type=ActionType.REFRESH,
                ),
                description="Refresh page",
                expected_outcome="Page reloaded",
            ))

        return recovery


class BrowserVerifier:
    """Verifies that browser actions achieved their intended results."""

    def __init__(self, session: BrowserSession, observer: BrowserObserver):
        self.session = session
        self.observer = observer

    async def verify_step(self, step: PlanStep, tab: BrowserTab) -> dict[str, Any]:
        """Verify a step's expected outcome."""
        verification = {
            "verified": False,
            "details": "",
            "checks": {}
        }

        expected = step.expected_outcome.lower()

        # Verify page loaded
        if "page loaded" in expected or "loaded" in expected:
            if tab.status.value == "ready" and tab.url:
                verification["checks"]["page_loaded"] = True
                verification["details"] += "Page loaded successfully. "
            else:
                verification["checks"]["page_loaded"] = False
                verification["details"] += "Page may not be fully loaded. "

        # Verify element clicked
        if "clicked" in expected:
            if step.result and step.result.success:
                verification["checks"]["click_executed"] = True
                verification["details"] += "Click executed. "
            else:
                verification["checks"]["click_executed"] = False

        # Verify text typed
        if "typed" in expected or "filled" in expected:
            # Check if element has the expected value
            verification["checks"]["text_entered"] = step.result.success if step.result else False

        # Verify navigation
        if "navigat" in expected:
            if tab.url and tab.url != "about:blank":
                verification["checks"]["navigated"] = True
                verification["details"] += f"Navigated to {tab.url}. "
            else:
                verification["checks"]["navigated"] = False

        # Verify specific element exists
        if step.action.selector:
            element = tab.interactive_elements
            matching = [e for e in element if step.action.selector in (e.selector or "")]
            if matching:
                verification["checks"]["element_present"] = True
                verification["details"] += f"Element found: {matching[0].element_id}. "
            else:
                verification["checks"]["element_present"] = False
                verification["details"] += "Expected element not found. "

        # Overall verification
        passed = sum(1 for v in verification["checks"].values() if v)
        total = len(verification["checks"])
        verification["verified"] = passed == total and total > 0
        verification["score"] = passed / total if total > 0 else 0

        return verification


async def create_plan(session: BrowserSession, observer: BrowserObserver, goal: str, context: dict | None = None) -> BrowserPlan:
    """Convenience function to create a plan."""
    planner = BrowserPlanner(session, observer)
    return planner.create_plan(goal, context)


async def execute_plan(session: BrowserSession, observer: BrowserObserver, executor: BrowserActionExecutor, plan: BrowserPlan) -> BrowserPlan:
    """Execute a complete plan with verification and recovery."""
    plan.status = PlanStatus.IN_PROGRESS
    plan.started_at = time.time()

    while not plan.is_complete():
        step = plan.get_next_step()
        if not step:
            if plan.has_failed():
                plan.status = PlanStatus.FAILED
            else:
                plan.status = PlanStatus.COMPLETED
            break

        step.status = PlanStatus.IN_PROGRESS

        # Execute step
        step.result = await executor.execute(step.action)

        if step.result.success:
            # Verify
            tab = session.get_active_tab()
            if tab:
                await observer.observe_tab(tab.tab_id)
                verification = await BrowserVerifier(session, observer).verify_step(step, tab)

                if verification["verified"]:
                    step.status = PlanStatus.COMPLETED
                else:
                    # Recovery
                    if step.retry_count < step.max_retries:
                        step.status = PlanStatus.REQUIRES_RECOVERY
                        plan = BrowserPlanner(session, observer).refine_plan(plan, step, verification["details"])
                    else:
                        step.status = PlanStatus.FAILED
            else:
                step.status = PlanStatus.COMPLETED
        else:
            # Handle failure
            if step.retry_count < step.max_retries:
                step.status = PlanStatus.REQUIRES_RECOVERY
                plan = BrowserPlanner(session, observer).refine_plan(plan, step, step.result.error or "Unknown error")
            else:
                step.status = PlanStatus.FAILED

    plan.completed_at = time.time()
    return plan
