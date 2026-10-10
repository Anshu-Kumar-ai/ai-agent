"""Advanced Browser Agent - Stage 19: Unified browser agent with perception→reasoning→action loop.

Integrates BrowserState, Observer, Planner, Executor, Verifier, and Recovery into a cohesive agent.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.tools.base import BaseTool
from app.tools.browser_executor import (
    ActionType,
    BrowserAction,
    BrowserActionExecutor,
)
from app.tools.browser_observer import BrowserObserver
from app.tools.browser_planner import (
    BrowserPlan,
    BrowserPlanner,
    BrowserVerifier,
    PlanStatus,
    PlanStep,
)
from app.tools.browser_recovery import (
    SITE_SPECIFIC_RECOVERIES,
    BrowserRecovery,
)
from app.tools.browser_state import (
    BrowserSession,
    BrowserTab,
    create_browser_session,
    get_browser_session,
    list_browser_sessions,
)


class BrowserAgentState(Enum):
    """State of the browser agent."""
    IDLE = "idle"
    OBSERVING = "observing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BrowserTask:
    """A task for the browser agent."""
    task_id: str
    goal: str
    session_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    state: BrowserAgentState = BrowserAgentState.IDLE
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    plan: BrowserPlan | None = None
    current_step: PlanStep | None = None
    result: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "session_id": self.session_id,
            "context": self.context,
            "state": self.state.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "plan": self.plan.to_dict() if self.plan else None,
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class AdvancedBrowserAgent:
    """Advanced browser agent with full perception→reasoning→action loop."""

    def __init__(
        self,
        session: BrowserSession | None = None,
        session_id: str | None = None,
        model_client=None,
        headless: bool = True,
        viewport: dict[str, int] = None,
    ):
        self.session = session or (get_browser_session(session_id) if session_id else create_browser_session(session_id))
        self.session_id = self.session.session_id

        # Core components
        self.observer = BrowserObserver(self.session)
        self.executor = BrowserActionExecutor(self.session, self.observer)
        self.planner = BrowserPlanner(self.session, self.observer, model_client)
        self.verifier = BrowserVerifier(self.session, self.observer)
        self.recovery = BrowserRecovery(self.session, self.observer, self.executor)

        # Playwright browser (set externally)
        self._browser = None
        self._context = None
        self._page = None
        self._headless = headless
        self._viewport = viewport or {"width": 1280, "height": 720}

        # Task management
        self.current_task: BrowserTask | None = None
        self.task_history: list[BrowserTask] = []

        # Configuration
        self.max_steps_per_task = 50
        self.step_timeout = 60  # seconds
        self.enable_recovery = True
        self.enable_verification = True

    async def initialize(self) -> None:
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ]
            )
            self._context = await self._browser.new_context(
                viewport=self._viewport,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self._page = await self._context.new_page()

            # Set page for components
            self.executor.set_page(self._page)
            self.observer.set_page(self._page)

            # Navigate to initial page
            await self._page.goto("about:blank")

            # Initialize session tab
            tab = self.session.get_active_tab()
            if tab:
                tab.url = "about:blank"
                tab.title = "New Tab"
                tab._playwright_page = self._page

            # Emit monitoring event
            try:
                from app.monitoring.emitter import emit_browser_session_created
                emit_browser_session_created(self.session_id)
            except Exception:
                pass

        except ImportError:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")

    async def close(self) -> None:
        """Close the browser."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, '_playwright'):
            await self._playwright.stop()

    async def execute_task(self, goal: str, context: dict[str, Any] | None = None) -> BrowserTask:
        """Execute a browser task with full perception→reasoning→action loop."""
        task = BrowserTask(
            task_id=f"task_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            goal=goal,
            session_id=self.session_id,
            context=context or {}
        )

        self.current_task = task
        task.state = BrowserAgentState.OBSERVING
        task.started_at = time.time()

        try:
            # Observe initial state
            await self.observer.observe_active_tab()

            # Add site-specific recoveries
            self._add_site_recoveries()

            # Plan
            task.state = BrowserAgentState.PLANNING
            task.plan = self.planner.create_plan(goal, context)

            # Execute plan with perception→reasoning→action loop
            task.state = BrowserAgentState.EXECUTING
            task = await self._execute_plan_with_loop(task)

            task.completed_at = time.time()
            if task.state != BrowserAgentState.FAILED:
                task.state = BrowserAgentState.COMPLETED

        except Exception as e:
            task.error = str(e)
            task.state = BrowserAgentState.FAILED
            task.completed_at = time.time()

        self.task_history.append(task)
        return task

    def _add_site_recoveries(self):
        """Add site-specific recovery strategies."""
        active_tab = self.session.get_active_tab()
        if active_tab:
            from urllib.parse import urlparse
            domain = urlparse(active_tab.url).netloc.lower()
            for key, recoveries in SITE_SPECIFIC_RECOVERIES.items():
                if key in domain:
                    for recovery in recoveries:
                        self.recovery.add_strategy(recovery)

    async def _execute_plan_with_loop(self, task: BrowserTask) -> BrowserTask:
        """Execute plan with full perception→reasoning→action→verification→recovery loop."""
        plan = task.plan
        step_count = 0

        while not plan.is_complete() and step_count < self.max_steps_per_task:
            # Get next step
            step = plan.get_next_step()
            if not step:
                if plan.has_failed():
                    task.state = BrowserAgentState.FAILED
                    task.error = "Plan has failed steps"
                break

            task.current_step = step
            step_count += 1

            # PERCEPTION: Observe current state
            task.state = BrowserAgentState.OBSERVING
            tab = self.session.get_active_tab()
            if tab:
                await self.observer.observe_tab(tab.tab_id)

            # Check if step is still relevant (page may have changed)
            if not self._is_step_still_valid(step, tab):
                # Re-plan
                task.state = BrowserAgentState.PLANNING
                task.plan = self.planner.create_plan(task.goal, {**task.context, "replan": True, "failed_step": step.step_id})
                plan = task.plan
                continue

            # EXECUTION: Execute step
            task.state = BrowserAgentState.EXECUTING
            step.status = PlanStatus.IN_PROGRESS
            step.result = await self.executor.execute(step.action)

            if not step.result.success:
                # RECOVERY
                if self.enable_recovery and step.retry_count < step.max_retries:
                    task.state = BrowserAgentState.RECOVERING
                    recovery_results = await self.recovery.attempt_recovery(
                        step.result.error or "Unknown error", step
                    )

                    # Check if recovery succeeded
                    if any(r.success for r in recovery_results):
                        # Observe after recovery
                        if tab:
                            await self.observer.observe_tab(tab.tab_id)
                        # Retry the step
                        step.retry_count += 1
                        step.status = PlanStatus.PENDING
                        continue
                    else:
                        step.status = PlanStatus.FAILED
                        if step.retry_count >= step.max_retries:
                            # Try planner-based recovery
                            task.state = BrowserAgentState.PLANNING
                            plan = self.planner.refine_plan(plan, step, step.result.error or "Unknown error")
                            continue
                else:
                    step.status = PlanStatus.FAILED
                    if step.retry_count >= step.max_retries:
                        task.error = f"Step failed after {step.max_retries} retries: {step.result.error}"
                        task.state = BrowserAgentState.FAILED
                        break
            else:
                # VERIFICATION
                if self.enable_verification:
                    task.state = BrowserAgentState.VERIFYING
                    verification = await self.verifier.verify_step(step, tab)

                    if verification["verified"]:
                        step.status = PlanStatus.COMPLETED
                    else:
                        if step.retry_count < step.max_retries:
                            task.state = BrowserAgentState.RECOVERING
                            recovery_results = await self.recovery.attempt_recovery(
                                verification["details"], step
                            )
                            if any(r.success for r in recovery_results):
                                step.retry_count += 1
                                step.status = PlanStatus.PENDING
                                continue

                        step.status = PlanStatus.FAILED
                        if step.retry_count >= step.max_retries:
                            task.error = f"Verification failed: {verification['details']}"
                            task.state = BrowserAgentState.FAILED
                            break
                else:
                    step.status = PlanStatus.COMPLETED

        # Final observation
        if tab:
            await self.observer.observe_tab(tab.tab_id)

        # Compile result
        task.result = self._compile_result(task)

        return task

    def _is_step_still_valid(self, step: PlanStep, tab: BrowserTab | None) -> bool:
        """Check if a step is still valid given current page state."""
        if not tab:
            return True

        # If step targets a specific element, check if it still exists
        if step.action.element_id:
            for element in tab.interactive_elements:
                if element.element_id == step.action.element_id:
                    return True
            return False

        if step.action.selector:
            for element in tab.interactive_elements:
                if step.action.selector in (element.selector or ""):
                    return True
            return False

        return True

    def _compile_result(self, task: BrowserTask) -> dict[str, Any]:
        """Compile final task result."""
        tab = self.session.get_active_tab()

        completed_steps = [s for s in task.plan.steps if s.status == PlanStatus.COMPLETED]
        failed_steps = [s for s in task.plan.steps if s.status == PlanStatus.FAILED]

        return {
            "goal": task.goal,
            "success": task.state == BrowserAgentState.COMPLETED,
            "final_url": tab.url if tab else None,
            "final_title": tab.title if tab else None,
            "steps_completed": len(completed_steps),
            "steps_failed": len(failed_steps),
            "total_steps": len(task.plan.steps),
            "execution_time": task.completed_at - task.started_at if task.completed_at and task.started_at else 0,
            "screenshot": tab.screenshot_path if tab else None,
            "extracted_data": self._extract_task_data(task),
        }

    def _extract_task_data(self, task: BrowserTask) -> dict[str, Any]:
        """Extract relevant data from the task execution."""
        data = {}
        tab = self.session.get_active_tab()

        if tab:
            # Collect text from completed steps
            for step in task.plan.steps:
                if step.status == PlanStatus.COMPLETED and step.result and step.result.result_data:
                    data[f"step_{step.step_id}"] = step.result.result_data

            # Add page data
            data["page_text"] = tab.visible_text[:5000] if tab.visible_text else None
            data["interactive_elements_count"] = len(tab.interactive_elements)
            data["forms_count"] = len(tab.forms)

        return data

    def get_session_info(self) -> dict[str, Any]:
        """Get current session information."""
        return {
            "session_id": self.session_id,
            "active_tab": self.session.get_active_tab().to_dict() if self.session.get_active_tab() else None,
            "tabs": self.session.list_tabs(),
            "current_task": self.current_task.to_dict() if self.current_task else None,
            "task_count": len(self.task_history),
        }


# Tool wrappers for the agent tool system

class BrowserAgentTool(BaseTool):
    """Tool for executing browser agent tasks."""

    name = "browser_agent.execute"
    description = "Execute a complex browser task with full perception-reasoning-action loop"
    selection_phrases = (
        "browser agent", "automate browser", "web automation", "browse and",
        "search and extract", "navigate and click", "fill form"
    )
    parameters = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "The goal to achieve (e.g., 'Find the cheapest RTX 5070 laptop under ₹1 lakh and compare five models')"
            },
            "context": {
                "type": "object",
                "description": "Additional context for the task",
                "default": {}
            },
            "session_id": {
                "type": "string",
                "description": "Optional existing session ID",
                "default": ""
            },
            "headless": {
                "type": "boolean",
                "description": "Run browser headless",
                "default": True
            }
        },
        "required": ["goal"],
        "additionalProperties": False,
    }

    def __init__(self):
        self._agent = None

    def validate_arguments(self, arguments: dict) -> None:
        if "goal" not in arguments:
            raise ValueError("Missing required argument: 'goal'")
        if not isinstance(arguments["goal"], str) or not arguments["goal"].strip():
            raise ValueError("'goal' must be a non-empty string")

    def execute(self, **kwargs) -> dict[str, Any]:

        goal = kwargs["goal"]
        context = kwargs.get("context", {})
        session_id = kwargs.get("session_id") or None
        headless = kwargs.get("headless", True)

        async def _run():
            agent = AdvancedBrowserAgent(session_id=session_id, headless=headless)
            await agent.initialize()
            try:
                task = await agent.execute_task(goal, context)
                return task.result
            finally:
                await agent.close()

        return asyncio.run(_run())


class BrowserSessionTool(BaseTool):
    """Tool for managing browser sessions."""

    name = "browser_session.manage"
    description = "Create, list, switch, or close browser sessions and tabs"
    selection_phrases = (
        "browser session", "new tab", "switch tab", "close tab", "list tabs"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_session", "list_sessions", "get_session", "delete_session", "create_tab", "switch_tab", "close_tab", "list_tabs", "create", "list", "get", "delete", "switch", "close"],
                "description": "Action to perform (also accepts 'action_type'). Short forms: create, list, get, delete, switch, close"
            },
            "action_type": {
                "type": "string",
                "enum": ["create_session", "list_sessions", "get_session", "delete_session", "create_tab", "switch_tab", "close_tab", "list_tabs", "create", "list", "get", "delete", "switch", "close"],
                "description": "Alias for 'action' parameter"
            },
            "session_id": {
                "type": "string",
                "description": "Session ID (optional for create)",
                "default": ""
            },
            "tab_id": {
                "type": "string",
                "description": "Tab ID for tab operations",
                "default": ""
            },
            "url": {
                "type": "string",
                "description": "URL for new tab",
                "default": "about:blank"
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "action" not in arguments:
            raise ValueError("Missing required argument: 'action'")

    def execute(self, **kwargs) -> dict[str, Any]:
        # Accept both 'action' and 'action_type' for compatibility
        action = kwargs.get("action") or kwargs.get("action_type")
        if not action:
            return {"error": "Missing required argument: 'action' or 'action_type'"}

        # Normalize short forms
        action_map = {
            "create": "create_session",
            "list": "list_sessions",
            "get": "get_session",
            "delete": "delete_session",
            "switch": "switch_tab",
            "close": "close_tab",
        }
        action = action_map.get(action, action)

        session_id = kwargs.get("session_id")
        tab_id = kwargs.get("tab_id")
        url = kwargs.get("url", "about:blank")

        if action == "create_session":
            session = create_browser_session(session_id)
            return {"session_id": session.session_id, "created": True}

        elif action == "list_sessions":
            return {"sessions": list_browser_sessions()}

        elif action == "get_session":
            if not session_id:
                return {"error": "session_id required"}
            session = get_browser_session(session_id)
            if not session:
                return {"error": f"Session {session_id} not found"}
            return session.to_dict()

        elif action == "delete_session":
            if not session_id:
                return {"error": "session_id required"}
            success = delete_browser_session(session_id)
            return {"deleted": success}

        elif action == "create_tab":
            if not session_id:
                return {"error": "session_id required"}
            session = get_browser_session(session_id)
            if not session:
                return {"error": f"Session {session_id} not found"}
            tab = session.create_tab(url)
            return {"tab_id": tab.tab_id, "url": tab.url}

        elif action == "switch_tab":
            if not session_id or not tab_id:
                return {"error": "session_id and tab_id required"}
            session = get_browser_session(session_id)
            if not session:
                return {"error": f"Session {session_id} not found"}
            tab = session.switch_tab(tab_id)
            if not tab:
                return {"error": f"Tab {tab_id} not found"}
            return {"tab_id": tab.tab_id, "url": tab.url, "switched": True}

        elif action == "close_tab":
            if not session_id or not tab_id:
                return {"error": "session_id and tab_id required"}
            session = get_browser_session(session_id)
            if not session:
                return {"error": f"Session {session_id} not found"}
            success = session.close_tab(tab_id)
            return {"closed": success}

        elif action == "list_tabs":
            if not session_id:
                return {"error": "session_id required"}
            session = get_browser_session(session_id)
            if not session:
                return {"error": f"Session {session_id} not found"}
            return {"tabs": session.list_tabs()}

        else:
            return {"error": f"Unknown action: {action}"}


class BrowserObserveTool(BaseTool):
    """Tool for observing browser state."""

    name = "browser.observe"
    description = "Observe current browser state (URL, title, elements, forms, text)"
    selection_phrases = ("observe browser", "what's on screen", "page state", "get page info")
    parameters = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session ID",
                "default": ""
            },
            "tab_id": {
                "type": "string",
                "description": "Tab ID (optional, uses active tab)",
                "default": ""
            },
            "include_screenshot": {
                "type": "boolean",
                "description": "Include screenshot",
                "default": False
            },
            "include_elements": {
                "type": "boolean",
                "description": "Include interactive elements",
                "default": True
            },
            "include_text": {
                "type": "boolean",
                "description": "Include visible text",
                "default": True
            },
            "element_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter element types",
                "default": []
            }
        },
        "required": ["session_id"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "session_id" not in arguments:
            raise ValueError("Missing required argument: 'session_id'")

    def execute(self, **kwargs) -> dict[str, Any]:

        session_id = kwargs["session_id"]
        tab_id = kwargs.get("tab_id")
        include_screenshot = kwargs.get("include_screenshot", False)
        include_elements = kwargs.get("include_elements", True)
        include_text = kwargs.get("include_text", True)
        element_types = kwargs.get("element_types", [])

        session = get_browser_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        tab = session.get_tab(tab_id) if tab_id else session.get_active_tab()
        if not tab:
            return {"error": "No tab found"}

        result = {
            "tab_id": tab.tab_id,
            "url": tab.url,
            "title": tab.title,
            "status": tab.status.value,
        }

        if include_text and tab.visible_text:
            result["visible_text"] = tab.visible_text[:10000]

        if include_elements:
            elements = tab.interactive_elements
            if element_types:
                from app.tools.browser_state import ElementType
                types = [ElementType(t) for t in element_types]
                elements = [e for e in elements if e.element_type in types]
            result["elements"] = [e.to_dict() for e in elements]
            result["element_count"] = len(elements)

        if tab.forms:
            result["forms"] = [f.to_dict() for f in tab.forms]

        if tab.page_metadata:
            result["page_metadata"] = tab.page_metadata

        if include_screenshot:
            # Screenshot would be taken by executor
            result["screenshot_path"] = tab.screenshot_path

        return result


class BrowserActionTool(BaseTool):
    """Tool for executing individual browser actions."""

    name = "browser.action"
    description = "Execute a single browser action (click, type, navigate, scroll, etc.)"
    selection_phrases = ("click", "type in browser", "navigate to", "scroll", "hover", "select option")
    parameters = {
        "type": "object",
        "properties": {
            "action_type": {
                "type": "string",
                "enum": [
                    "navigate", "click", "type", "scroll", "hover", "select",
                    "wait", "key_press", "screenshot", "go_back", "go_forward",
                    "refresh", "new_tab", "switch_tab", "close_tab",
                    "fill_form", "submit_form", "file_upload"
                ],
                "description": "Type of action to execute"
            },
            "session_id": {
                "type": "string",
                "description": "Session ID",
                "default": ""
            },
            "tab_id": {
                "type": "string",
                "description": "Tab ID (optional)",
                "default": ""
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element",
                "default": ""
            },
            "element_id": {
                "type": "string",
                "description": "Element ID from observer",
                "default": ""
            },
            "url": {
                "type": "string",
                "description": "URL for navigate",
                "default": ""
            },
            "text": {
                "type": "string",
                "description": "Text for type/fill_form",
                "default": ""
            },
            "key": {
                "type": "string",
                "description": "Key for key_press",
                "default": ""
            },
            "direction": {
                "type": "string",
                "description": "Direction for scroll",
                "default": "down"
            },
            "amount": {
                "type": "integer",
                "description": "Scroll amount",
                "default": 500
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 30000
            }
        },
        "required": ["action_type", "session_id"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "action_type" not in arguments:
            raise ValueError("Missing required argument: 'action_type'")
        if "session_id" not in arguments:
            raise ValueError("Missing required argument: 'session_id'")

    def execute(self, **kwargs) -> dict[str, Any]:

        action_type_str = kwargs["action_type"]
        session_id = kwargs["session_id"]

        # Map string to ActionType
        try:
            action_type = ActionType(action_type_str)
        except ValueError:
            return {"error": f"Invalid action_type: {action_type_str}"}

        # Build action
        action = BrowserAction(
            action_type=action_type,
            tab_id=kwargs.get("tab_id") or None,
            selector=kwargs.get("selector") or None,
            element_id=kwargs.get("element_id") or None,
            url=kwargs.get("url") or None,
            text=kwargs.get("text") or None,
            key=kwargs.get("key") or None,
            direction=kwargs.get("direction", "down"),
            amount=kwargs.get("amount", 500),
            timeout=kwargs.get("timeout", 30000),
        )

        session = get_browser_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        # Get or create the browser agent for this session
        # We need an active browser to execute actions
        from app.tools.advanced_browser_agent import AdvancedBrowserAgent
        
        # Check if there's an active agent for this session
        # If not, we need to initialize one
        # For now, use the session's page if available
        tab = session.get_tab(action.tab_id) if action.tab_id else session.get_active_tab()
        if not tab or not tab._playwright_page:
            return {"error": f"No active browser page for session {session_id}. Use browser_agent.execute to start a session first."}

        # Execute the action directly using the executor
        from app.tools.browser_observer import BrowserObserver
        observer = BrowserObserver(session)
        observer.set_page(tab._playwright_page)
        
        from app.tools.browser_executor import BrowserActionExecutor
        executor = BrowserActionExecutor(session, observer)
        executor.set_page(tab._playwright_page, action.tab_id)

        # Run the action
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(executor.execute(action))
        
        return result.to_dict()


def create_browser_agent_tools() -> list[BaseTool]:
    """Create all browser agent tools."""
    return [
        BrowserAgentTool(),
        BrowserSessionTool(),
        BrowserObserveTool(),
        BrowserActionTool(),
    ]


def create_advanced_browser_agent(
    session_id: str | None = None,
    model_client=None,
    headless: bool = True,
    viewport: dict[str, int] = None
) -> AdvancedBrowserAgent:
    """Create an advanced browser agent."""
    return AdvancedBrowserAgent(
        session_id=session_id,
        model_client=model_client,
        headless=headless,
        viewport=viewport
    )
