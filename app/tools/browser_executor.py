"""Browser Action Executor - Stage 18: Computer Use Foundation.

Responsible for executing actions on the browser (click, type, navigate, scroll, etc.).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.tools.browser_observer import BrowserObserver
from app.tools.browser_state import (
    BrowserSession,
)


class ActionType(Enum):
    """Types of browser actions."""
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    HOVER = "hover"
    SELECT = "select"
    WAIT = "wait"
    KEY_PRESS = "key_press"
    SCREENSHOT = "screenshot"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    REFRESH = "refresh"
    CLOSE_TAB = "close_tab"
    NEW_TAB = "new_tab"
    SWITCH_TAB = "switch_tab"
    FILL_FORM = "fill_form"
    SUBMIT_FORM = "submit_form"
    DRAG_DROP = "drag_drop"
    FILE_UPLOAD = "file_upload"


@dataclass
class BrowserAction:
    """Represents a browser action to execute."""
    action_type: ActionType
    # Target
    tab_id: str | None = None
    element_id: str | None = None
    selector: str | None = None
    # Parameters
    url: str | None = None
    text: str | None = None
    key: str | None = None
    direction: str = "down"  # for scroll
    amount: int = 500  # for scroll
    timeout: int = 30000  # milliseconds
    wait_until: str = "networkidle"  # for navigate
    # Options
    force: bool = False
    no_wait_after: bool = False
    # Verification
    verify: bool = True
    expected_result: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "tab_id": self.tab_id,
            "element_id": self.element_id,
            "selector": self.selector,
            "url": self.url,
            "text": self.text,
            "key": self.key,
            "direction": self.direction,
            "amount": self.amount,
            "timeout": self.timeout,
            "wait_until": self.wait_until,
            "force": self.force,
            "no_wait_after": self.no_wait_after,
            "verify": self.verify,
            "expected_result": self.expected_result,
        }


@dataclass
class ActionResult:
    """Result of an executed action."""
    success: bool
    action: BrowserAction
    result_data: dict[str, Any] = None
    error: str | None = None
    execution_time: float = 0.0
    verified: bool = False
    verification_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action.to_dict(),
            "result_data": self.result_data,
            "error": self.error,
            "execution_time": self.execution_time,
            "verified": self.verified,
            "verification_details": self.verification_details,
        }


class BrowserActionExecutor:
    """Executes browser actions using Playwright."""

    def __init__(self, session: BrowserSession, observer: BrowserObserver):
        self.session = session
        self.observer = observer
        self._playwright_pages: dict[str, Any] = {}  # tab_id -> page
        self._default_page = None

    def set_page(self, page, tab_id: str | None = None):
        """Set the Playwright page for a tab."""
        if tab_id:
            self._playwright_pages[tab_id] = page
        else:
            self._default_page = page
        self.observer.set_page(page)

    def _get_page(self, tab_id: str | None = None):
        """Get the Playwright page for a tab."""
        # Try to get page for specific tab
        if tab_id and tab_id in self._playwright_pages:
            return self._playwright_pages[tab_id]
        
        # Try active tab's stored page
        active_tab = self.session.get_active_tab()
        if active_tab and active_tab._playwright_page:
            return active_tab._playwright_page
        
        # Fallback to default page
        if self._default_page:
            return self._default_page
            
        raise RuntimeError("Playwright page not set")

    def _get_or_create_page(self, tab_id: str | None = None):
        """Get or create a page for the given tab, switching if necessary."""
        if tab_id:
            tab = self.session.get_tab(tab_id)
        else:
            tab = self.session.get_active_tab()
            
        if tab and tab._playwright_page:
            return tab._playwright_page
            
        if self._default_page:
            # Store reference in tab
            if tab:
                tab._playwright_page = self._default_page
            return self._default_page
            
        raise RuntimeError("Playwright page not set")

    def _get_element(self, page, action: BrowserAction):
        """Get the element to interact with."""
        if action.element_id:
            # Try to find by element_id from observer
            tab = self.session.get_active_tab()
            if tab:
                for element in tab.interactive_elements:
                    if element.element_id == action.element_id:
                        # Return a locator for this element
                        if action.selector:
                            return page.locator(action.selector).first
                        # Fallback: use text/label
                        if element.text:
                            return page.get_by_text(element.text, exact=False).first
                        if element.label:
                            return page.get_by_label(element.label, exact=False).first
                        if element.role:
                            return page.get_by_role(element.role, name=element.label).first

        # Fallback to selector
        if action.selector:
            return page.locator(action.selector).first

        return None

    async def execute(self, action: BrowserAction) -> ActionResult:
        """Execute a browser action."""
        start_time = time.time()
        session_id = self.session.session_id
        tab_id = action.tab_id or (self.session.get_active_tab().tab_id if self.session.get_active_tab() else None)

        try:
            page = self._get_or_create_page(action.tab_id)

            # Execute based on action type
            if action.action_type == ActionType.NAVIGATE:
                result = await self._navigate(page, action)
            elif action.action_type == ActionType.CLICK:
                result = await self._click(page, action)
            elif action.action_type == ActionType.TYPE:
                result = await self._type(page, action)
            elif action.action_type == ActionType.SCROLL:
                result = await self._scroll(page, action)
            elif action.action_type == ActionType.HOVER:
                result = await self._hover(page, action)
            elif action.action_type == ActionType.SELECT:
                result = await self._select(page, action)
            elif action.action_type == ActionType.WAIT:
                result = await self._wait(page, action)
            elif action.action_type == ActionType.KEY_PRESS:
                result = await self._key_press(page, action)
            elif action.action_type == ActionType.SCREENSHOT:
                result = await self._screenshot(page, action)
            elif action.action_type == ActionType.GO_BACK:
                result = await self._go_back(page, action)
            elif action.action_type == ActionType.GO_FORWARD:
                result = await self._go_forward(page, action)
            elif action.action_type == ActionType.REFRESH:
                result = await self._refresh(page, action)
            elif action.action_type == ActionType.NEW_TAB:
                result = await self._new_tab(page, action)
            elif action.action_type == ActionType.SWITCH_TAB:
                result = await self._switch_tab(action)
            elif action.action_type == ActionType.CLOSE_TAB:
                result = await self._close_tab(action)
            elif action.action_type == ActionType.FILL_FORM:
                result = await self._fill_form(page, action)
            elif action.action_type == ActionType.SUBMIT_FORM:
                result = await self._submit_form(page, action)
            elif action.action_type == ActionType.FILE_UPLOAD:
                result = await self._file_upload(page, action)
            else:
                return ActionResult(
                    success=False,
                    action=action,
                    error=f"Unknown action type: {action.action_type}",
                    execution_time=time.time() - start_time
                )

            execution_time = time.time() - start_time
            result.execution_time = execution_time

            # Emit monitoring event for browser action
            try:
                from app.monitoring.emitter import emit_browser_action
                emit_browser_action(
                    session_id=session_id,
                    tab_id=tab_id or "unknown",
                    action_type=action.action_type.value,
                    success=result.success,
                    duration_ms=execution_time * 1000,
                )
            except Exception:
                pass

            # Verify if requested
            if action.verify and result.success:
                await self.observer.observe_active_tab()
                result.verified = True
                result.verification_details = "State observed after action"

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            
            # Emit browser error event
            try:
                from app.monitoring.emitter import emit_browser_error
                emit_browser_error(
                    session_id=session_id,
                    tab_id=tab_id or "unknown",
                    error_type=type(e).__name__,
                )
            except Exception:
                pass

            return ActionResult(
                success=False,
                action=action,
                error=f"{type(e).__name__}: {str(e)}",
                execution_time=execution_time
            )

    async def _navigate(self, page, action: BrowserAction) -> ActionResult:
        """Navigate to a URL."""
        if not action.url:
            return ActionResult(
                success=False,
                action=action,
                error="No URL provided for navigate action"
            )

        response = await page.goto(action.url, wait_until=action.wait_until, timeout=action.timeout)

        # Update tab info
        tab = self.session.get_active_tab()
        if tab:
            tab.url = page.url
            tab.title = await page.title()
            tab.navigation_history.append(action.url)
            tab._playwright_page = page

        return ActionResult(
            success=response.ok if response else True,
            action=action,
            result_data={
                "url": page.url,
                "title": await page.title(),
                "status": response.status if response else None,
            }
        )

    async def _click(self, page, action: BrowserAction) -> ActionResult:
        """Click an element."""
        element = self._get_element(page, action)
        if not element:
            return ActionResult(
                success=False,
                action=action,
                error="Element not found for click"
            )

        # Scroll into view if needed
        await element.scroll_into_view_if_needed()

        await element.click(
            force=action.force,
            no_wait_after=action.no_wait_after,
            timeout=action.timeout
        )

        return ActionResult(
            success=True,
            action=action,
            result_data={"clicked": True}
        )

    async def _type(self, page, action: BrowserAction) -> ActionResult:
        """Type text into an element."""
        if not action.text:
            return ActionResult(
                success=False,
                action=action,
                error="No text provided for type action"
            )

        element = self._get_element(page, action)
        if not element:
            return ActionResult(
                success=False,
                action=action,
                error="Element not found for type"
            )

        await element.scroll_into_view_if_needed()
        await element.fill(action.text)

        return ActionResult(
            success=True,
            action=action,
            result_data={"typed": True, "text_length": len(action.text)}
        )

    async def _scroll(self, page, action: BrowserAction) -> ActionResult:
        """Scroll the page."""
        direction = action.direction.lower()
        amount = action.amount

        if direction == "down":
            await page.mouse.wheel(0, amount)
        elif direction == "up":
            await page.mouse.wheel(0, -amount)
        elif direction == "left":
            await page.mouse.wheel(-amount, 0)
        elif direction == "right":
            await page.mouse.wheel(amount, 0)
        else:
            return ActionResult(
                success=False,
                action=action,
                error=f"Invalid scroll direction: {direction}"
            )

        return ActionResult(
            success=True,
            action=action,
            result_data={"scrolled": direction, "amount": amount}
        )

    async def _hover(self, page, action: BrowserAction) -> ActionResult:
        """Hover over an element."""
        element = self._get_element(page, action)
        if not element:
            return ActionResult(
                success=False,
                action=action,
                error="Element not found for hover"
            )

        await element.hover()

        return ActionResult(
            success=True,
            action=action,
            result_data={"hovered": True}
        )

    async def _select(self, page, action: BrowserAction) -> ActionResult:
        """Select an option in a dropdown."""
        if not action.text:
            return ActionResult(
                success=False,
                action=action,
                error="No option text/value provided for select"
            )

        element = self._get_element(page, action)
        if not element:
            return ActionResult(
                success=False,
                action=action,
                error="Element not found for select"
            )

        await element.select_option(label=action.text)

        return ActionResult(
            success=True,
            action=action,
            result_data={"selected": action.text}
        )

    async def _wait(self, page, action: BrowserAction) -> ActionResult:
        """Wait for a condition."""
        wait_time = action.timeout / 1000.0

        if action.selector:
            # Wait for element
            await page.wait_for_selector(action.selector, timeout=action.timeout)
        elif action.url:
            # Wait for navigation
            await page.wait_for_url(action.url, timeout=action.timeout)
        else:
            # Just wait
            await asyncio.sleep(wait_time)

        return ActionResult(
            success=True,
            action=action,
            result_data={"waited": True, "duration": wait_time}
        )

    async def _key_press(self, page, action: BrowserAction) -> ActionResult:
        """Press a key."""
        if not action.key:
            return ActionResult(
                success=False,
                action=action,
                error="No key provided for key_press"
            )

        await page.keyboard.press(action.key)

        return ActionResult(
            success=True,
            action=action,
            result_data={"key_pressed": action.key}
        )

    async def _screenshot(self, page, action: BrowserAction) -> ActionResult:
        """Take a screenshot."""
        path = await self.observer.take_screenshot(
            action.tab_id or self.session.active_tab_id
        )

        return ActionResult(
            success=True,
            action=action,
            result_data={"screenshot_path": path}
        )

    async def _go_back(self, page, action: BrowserAction) -> ActionResult:
        """Go back in history."""
        await page.go_back(timeout=action.timeout)

        tab = self.session.get_active_tab()
        if tab:
            tab.url = page.url

        return ActionResult(
            success=True,
            action=action,
            result_data={"url": page.url}
        )

    async def _go_forward(self, page, action: BrowserAction) -> ActionResult:
        """Go forward in history."""
        await page.go_forward(timeout=action.timeout)

        tab = self.session.get_active_tab()
        if tab:
            tab.url = page.url

        return ActionResult(
            success=True,
            action=action,
            result_data={"url": page.url}
        )

    async def _refresh(self, page, action: BrowserAction) -> ActionResult:
        """Refresh the page."""
        await page.reload(wait_until=action.wait_until, timeout=action.timeout)

        return ActionResult(
            success=True,
            action=action,
            result_data={"refreshed": True}
        )

    async def _new_tab(self, page, action: BrowserAction) -> ActionResult:
        """Create a new tab (browser context level)."""
        context = page.context
        new_page = await context.new_page()
        
        tab = self.session.create_tab(
            action.url or "about:blank",
            action.text or "New Tab"
        )
        
        tab._playwright_page = new_page
        self._playwright_pages[tab.tab_id] = new_page
        
        if action.url and action.url != "about:blank":
            await new_page.goto(action.url, wait_until=action.wait_until, timeout=action.timeout)
            tab.url = new_page.url
            tab.title = await new_page.title()
            tab.navigation_history.append(action.url)
        else:
            await new_page.goto("about:blank")

        return ActionResult(
            success=True,
            action=action,
            result_data={"tab_id": tab.tab_id, "url": tab.url}
        )

    async def _switch_tab(self, action: BrowserAction) -> ActionResult:
        """Switch to a different tab."""
        if not action.tab_id:
            return ActionResult(
                success=False,
                action=action,
                error="No tab_id provided for switch_tab"
            )

        tab = self.session.switch_tab(action.tab_id)
        if not tab:
            return ActionResult(
                success=False,
                action=action,
                error=f"Tab {action.tab_id} not found"
            )
            
        # Update observer and executor to use the switched tab's page
        if tab._playwright_page:
            self.observer.set_page(tab._playwright_page)
            self._playwright_pages[tab.tab_id] = tab._playwright_page

        return ActionResult(
            success=True,
            action=action,
            result_data={"tab_id": tab.tab_id, "url": tab.url}
        )

    async def _close_tab(self, action: BrowserAction) -> ActionResult:
        """Close a tab."""
        tab_id = action.tab_id or self.session.active_tab_id
        if not tab_id:
            return ActionResult(
                success=False,
                action=action,
                error="No tab to close"
            )

        # Close Playwright page if exists
        if tab_id in self._playwright_pages:
            try:
                await self._playwright_pages[tab_id].close()
            except Exception:
                pass
            del self._playwright_pages[tab_id]

        success = self.session.close_tab(tab_id)

        return ActionResult(
            success=success,
            action=action,
            result_data={"closed": success}
        )

    async def _fill_form(self, page, action: BrowserAction) -> ActionResult:
        """Fill a form with provided data."""
        if not action.selector:
            return ActionResult(
                success=False,
                action=action,
                error="No form selector provided"
            )

        form = page.locator(action.selector)

        # If text contains JSON data for fields
        if action.text:
            try:
                import json
                fields = json.loads(action.text)
                for field_name, field_value in fields.items():
                    input_locator = form.locator(f'input[name="{field_name}"], textarea[name="{field_name}"], select[name="{field_name}"]').first
                    if await input_locator.count() > 0:
                        await input_locator.fill(str(field_value))
            except json.JSONDecodeError:
                return ActionResult(
                    success=False,
                    action=action,
                    error="Invalid JSON in text field for form data"
                )

        return ActionResult(
            success=True,
            action=action,
            result_data={"form_filled": True}
        )

    async def _submit_form(self, page, action: BrowserAction) -> ActionResult:
        """Submit a form."""
        if not action.selector:
            return ActionResult(
                success=False,
                action=action,
                error="No form selector provided"
            )

        form = page.locator(action.selector)
        await form.evaluate("form => form.submit()")

        return ActionResult(
            success=True,
            action=action,
            result_data={"form_submitted": True}
        )

    async def _file_upload(self, page, action: BrowserAction) -> ActionResult:
        """Upload a file."""
        if not action.selector or not action.text:
            return ActionResult(
                success=False,
                action=action,
                error="selector and file path (text) required for file_upload"
            )

        input_locator = page.locator(action.selector).first
        await input_locator.set_input_files(action.text)

        return ActionResult(
            success=True,
            action=action,
            result_data={"file_uploaded": action.text}
        )


async def execute_action(session: BrowserSession, observer: BrowserObserver, action: BrowserAction) -> ActionResult:
    """Convenience function to execute a single action."""
    executor = BrowserActionExecutor(session, observer)
    # Page must be set externally
    return await executor.execute(action)
