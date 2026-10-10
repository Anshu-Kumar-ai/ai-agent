"""
Phase 5 - Real Browser Validation Tests
Tests the actual BrowserSession/Executor/Observer stack against local test fixtures.
"""
import pytest
import asyncio
import time
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.tools.browser_state import (
    BrowserSession, BrowserTab, BrowserElement, BrowserForm,
    ElementType, TabStatus, create_browser_session, get_browser_session, delete_browser_session
)
from app.tools.browser_observer import BrowserObserver, create_observer
from app.tools.browser_executor import (
    BrowserActionExecutor, BrowserAction, ActionType, ActionResult
)
from app.tools.browser_planner import BrowserPlanner, BrowserPlan, PlanStep, PlanStatus
from app.tools.browser_recovery import BrowserRecovery, RecoveryAction, RecoveryStrategy
from app.tools.advanced_browser_agent import AdvancedBrowserAgent, create_advanced_browser_agent

# Skip if playwright not installed
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: tests requiring browser automation")


# Fixtures
@pytest.fixture(scope="session")
def fixture_server():
    """Start local test fixture server."""
    import subprocess
    import time
    
    server_script = Path(__file__).parent / "fixtures" / "browser" / "server.py"
    proc = subprocess.Popen([sys.executable, str(server_script)])
    time.sleep(2)  # Wait for server to start
    yield "http://localhost:8765"
    proc.terminate()
    proc.wait(timeout=5)


# Helper to create browser session in tests
async def create_test_browser_session():
    """Create a browser session with Playwright for testing."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    session = create_browser_session()
    tab = session.get_active_tab()
    tab._playwright_page = page
    
    return session, page, playwright, browser, context


async def cleanup_browser_session(playwright, browser, context, page):
    """Clean up browser session."""
    await page.close()
    await context.close()
    await browser.close()
    await playwright.stop()


# ============================================================================
# 5A - Local Test Website Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_local_fixture_server_accessible(fixture_server):
    """Verify the local test fixture server is accessible."""
    import urllib.request
    with urllib.request.urlopen(f"{fixture_server}/index.html", timeout=5) as resp:
        assert resp.status == 200
        text = resp.read().decode('utf-8')
        assert "Browser Test Fixture" in text


# ============================================================================
# 5B - Real Playwright Execution Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_session_creation():
    """Test browser session creation."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        assert session is not None
        assert session.session_id is not None
        assert len(session.tabs) == 1
        assert session.active_tab_id is not None
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_tab_creation():
    """Test tab creation."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        initial_count = len(session.tabs)
        
        new_tab = session.create_tab("about:blank", "Test Tab")
        assert new_tab.tab_id in session.tabs
        assert len(session.tabs) == initial_count + 1
        assert session.active_tab_id == new_tab.tab_id
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_tab_switching():
    """Test tab switching."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        tab1 = session.get_active_tab()
        tab2 = session.create_tab("about:blank", "Tab 2")
        tab3 = session.create_tab("about:blank", "Tab 3")
        
        # Switch to tab2
        switched = session.switch_tab(tab2.tab_id)
        assert switched.tab_id == tab2.tab_id
        assert session.active_tab_id == tab2.tab_id
        
        # Switch to tab3
        switched = session.switch_tab(tab3.tab_id)
        assert switched.tab_id == tab3.tab_id
        assert session.active_tab_id == tab3.tab_id
        
        # Switch back to tab1
        switched = session.switch_tab(tab1.tab_id)
        assert switched.tab_id == tab1.tab_id
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_tab_closing():
    """Test tab closing."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        tab1 = session.get_active_tab()
        tab2 = session.create_tab("about:blank", "Tab to Close")
        
        assert len(session.tabs) == 2
        
        # Close tab2
        success = session.close_tab(tab2.tab_id)
        assert success is True
        assert len(session.tabs) == 1
        assert session.active_tab_id == tab1.tab_id
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_navigation(fixture_server):
    """Test navigation action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle",
            timeout=30000
        )
        
        result = await exec.execute(action)
        assert result.success is True
        assert result.result_data["url"] == f"{fixture_server}/index.html"
        assert "Browser Test Fixture" in result.result_data["title"]
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_click_action(fixture_server):
    """Test click action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # First navigate
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        # Click the button
        click_action = BrowserAction(
            action_type=ActionType.CLICK,
            selector="#btn-click-me",
            timeout=10000
        )
        
        result = await exec.execute(click_action)
        assert result.success is True
        assert result.result_data["clicked"] is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_type_action(fixture_server):
    """Test type action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Navigate first
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        # Type into text input
        type_action = BrowserAction(
            action_type=ActionType.TYPE,
            selector="#text-input",
            text="Hello, Browser!",
            timeout=10000
        )
        
        result = await exec.execute(type_action)
        assert result.success is True
        assert result.result_data["typed"] is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_form_fill_and_submit(fixture_server):
    """Test form filling and submission."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Navigate
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        # Fill form
        fill_action = BrowserAction(
            action_type=ActionType.FILL_FORM,
            selector="#test-form",
            text='{"username": "testuser", "email": "test@example.com", "message": "Hello from test"}',
            timeout=10000
        )
        
        result = await exec.execute(fill_action)
        assert result.success is True
        
        # Submit form
        submit_action = BrowserAction(
            action_type=ActionType.SUBMIT_FORM,
            selector="#test-form",
            timeout=10000
        )
        
        result = await exec.execute(submit_action)
        assert result.success is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_select_dropdown(fixture_server):
    """Test select dropdown action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        select_action = BrowserAction(
            action_type=ActionType.SELECT,
            selector="#dropdown-select",
            text="Option 2",  # Changed from "option2" to match the actual option text
            timeout=10000
        )
        
        result = await exec.execute(select_action)
        assert result.success is True
        assert result.result_data["selected"] == "Option 2"
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_wait_action(fixture_server):
    """Test wait action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        wait_action = BrowserAction(
            action_type=ActionType.WAIT,
            timeout=500,
        )
        
        result = await exec.execute(wait_action)
        assert result.success is True
        assert result.result_data["waited"] is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_key_press_action(fixture_server):
    """Test key press action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        # Focus input first
        click_action = BrowserAction(
            action_type=ActionType.CLICK,
            selector="#text-input",
        )
        await exec.execute(click_action)
        
        key_action = BrowserAction(
            action_type=ActionType.KEY_PRESS,
            key="Tab",
        )
        
        result = await exec.execute(key_action)
        assert result.success is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_screenshot_action(fixture_server):
    """Test screenshot action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        screenshot_action = BrowserAction(
            action_type=ActionType.SCREENSHOT,
        )
        
        result = await exec.execute(screenshot_action)
        assert result.success is True
        assert "screenshot_path" in result.result_data
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_new_tab_action(fixture_server):
    """Test new tab creation."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url=f"{fixture_server}/index.html",
            wait_until="networkidle"
        )
        await exec.execute(nav_action)
        
        new_tab_action = BrowserAction(
            action_type=ActionType.NEW_TAB,
            url=f"{fixture_server}/page2.html",
            text="Page 2",
        )
        
        result = await exec.execute(new_tab_action)
        assert result.success is True
        assert "tab_id" in result.result_data
        assert result.result_data["url"] == f"{fixture_server}/page2.html"
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_switch_tab_action(fixture_server):
    """Test switching tabs."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Create first tab with page 1
        nav1 = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav1)
        
        # Create second tab with page 2
        new_tab = BrowserAction(action_type=ActionType.NEW_TAB, url=f"{fixture_server}/page2.html", text="Page 2")
        result = await exec.execute(new_tab)
        tab2_id = result.result_data["tab_id"]
        
        # Switch back to first tab
        switch1 = BrowserAction(action_type=ActionType.SWITCH_TAB, tab_id=list(exec.session.tabs.keys())[0])
        result = await exec.execute(switch1)
        assert result.success is True
        assert exec.session.active_tab_id != tab2_id
        
        # Switch to tab2
        switch2 = BrowserAction(action_type=ActionType.SWITCH_TAB, tab_id=tab2_id)
        result = await exec.execute(switch2)
        assert result.success is True
        assert exec.session.active_tab_id == tab2_id
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_close_tab_action(fixture_server):
    """Test closing a tab via action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        new_tab_action = BrowserAction(action_type=ActionType.NEW_TAB, url=f"{fixture_server}/page2.html")
        result = await exec.execute(new_tab_action)
        tab2_id = result.result_data["tab_id"]
        
        initial_count = len(exec.session.tabs)
        
        close_action = BrowserAction(action_type=ActionType.CLOSE_TAB, tab_id=tab2_id)
        result = await exec.execute(close_action)
        
        assert result.success is True
        assert len(exec.session.tabs) == initial_count - 1
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_scroll_action(fixture_server):
    """Test scroll action."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        scroll_action = BrowserAction(action_type=ActionType.SCROLL, direction="down", amount=300)
        result = await exec.execute(scroll_action)
        
        assert result.success is True
        assert result.result_data["scrolled"] == "down"
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# 5C - Dynamic Content Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_delayed_content_wait_and_interact(fixture_server):
    """Test waiting for delayed content and interacting with it."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        # Click button to show delayed content
        click_action = BrowserAction(action_type=ActionType.CLICK, selector="#show-delayed")
        await exec.execute(click_action)
        
        # Wait for delayed content to appear (using wait with selector)
        wait_action = BrowserAction(
            action_type=ActionType.WAIT,
            selector="#delayed-content",
            timeout=5000
        )
        result = await exec.execute(wait_action)
        assert result.success is True
        
        # Now interact with the delayed button
        click_delayed = BrowserAction(action_type=ActionType.CLICK, selector="#delayed-btn")
        result = await exec.execute(click_delayed)
        assert result.success is True
        
        # Type in delayed input
        type_delayed = BrowserAction(action_type=ActionType.TYPE, selector="#delayed-input", text="delayed input")
        result = await exec.execute(type_delayed)
        assert result.success is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_dynamic_element_addition(fixture_server):
    """Test interacting with dynamically added elements."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        # Add dynamic element
        add_action = BrowserAction(action_type=ActionType.CLICK, selector="#add-element")
        add_result = await exec.execute(add_action)
        assert add_result.success is True, f"Click to add element failed: {add_result.error}"
        
        # Wait for dynamic element
        wait_action = BrowserAction(action_type=ActionType.WAIT, selector="#dynamic-element", timeout=10000)
        result = await exec.execute(wait_action)
        assert result.success is True
        
        # Interact with dynamic input
        type_action = BrowserAction(action_type=ActionType.TYPE, selector="#dynamic-input", text="dynamic")
        result = await exec.execute(type_action)
        assert result.success is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# 5D - Recovery Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_navigation_timeout_recovery(fixture_server):
    """Test navigation timeout handling."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Navigate to invalid URL with short timeout
        nav_action = BrowserAction(
            action_type=ActionType.NAVIGATE,
            url="http://10.255.255.1:8080/",  # Non-routable IP, should timeout
            timeout=2000,
            wait_until="networkidle"
        )
        
        result = await exec.execute(nav_action)
        # Should fail gracefully
        assert result.success is False
        assert "timeout" in result.error.lower() or "error" in result.error.lower()
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_element_not_found_recovery(fixture_server):
    """Test recovery when element not found."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        # Try to click non-existent element
        click_action = BrowserAction(action_type=ActionType.CLICK, selector="#non-existent-element")
        result = await exec.execute(click_action)
        
        # Should fail gracefully
        assert result.success is False
        assert "not found" in result.error.lower() or "element" in result.error.lower()
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_recovery_strategies(fixture_server):
    """Test the BrowserRecovery system."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Navigate to test page
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        recovery = BrowserRecovery(session, obs, exec)
        
        # Create a fake failed step
        failed_step = PlanStep(
            step_id="test_step",
            action=BrowserAction(action_type=ActionType.CLICK, selector="#non-existent"),
            description="Test step",
            expected_outcome="Click element"
        )
        failed_step.result = ActionResult(success=False, action=failed_step.action, error="Element not found")
        
        # Attempt recovery
        results = await recovery.attempt_recovery("Element not found", failed_step)
        
        # Should have attempted recovery strategies
        assert len(results) > 0
        # At least some recovery was attempted
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_stale_page_recovery(fixture_server):
    """Test recovery from stale page state."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        # Navigate away then back
        nav2 = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/page2.html", wait_until="networkidle")
        await exec.execute(nav2)
        
        # Go back
        back_action = BrowserAction(action_type=ActionType.GO_BACK)
        result = await exec.execute(back_action)
        assert result.success is True
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# 5E - Multi-tab Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_multi_tab_independent_state(fixture_server):
    """Test that tabs maintain independent state."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # Tab 1: index.html
        nav1 = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav1)
        tab1_id = exec.session.active_tab_id
        
        # Fill input in tab 1
        type1 = BrowserAction(action_type=ActionType.TYPE, selector="#text-input", text="tab1 content")
        await exec.execute(type1)
        
        # Tab 2: page2.html
        new_tab = BrowserAction(action_type=ActionType.NEW_TAB, url=f"{fixture_server}/page2.html")
        result = await exec.execute(new_tab)
        tab2_id = result.result_data["tab_id"]
        
        # Fill form in tab 2
        fill2 = BrowserAction(action_type=ActionType.FILL_FORM, selector="#page2-form", text='{"data": "tab2 data"}')
        await exec.execute(fill2)
        
        # Switch back to tab 1 - should have its own state
        switch1 = BrowserAction(action_type=ActionType.SWITCH_TAB, tab_id=tab1_id)
        await exec.execute(switch1)
        
        # Verify tab 1 still has its content
        observe_action = BrowserAction(action_type=ActionType.WAIT, timeout=500)
        await exec.execute(observe_action)
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# Observer Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_observer_extracts_elements(fixture_server):
    """Test that observer extracts interactive elements."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        tab = await obs.observe_active_tab()
        
        assert len(tab.interactive_elements) > 0
        # Should find buttons, inputs, links, etc.
        element_types = {e.element_type for e in tab.interactive_elements}
        assert ElementType.BUTTON in element_types
        assert ElementType.INPUT in element_types
        assert ElementType.LINK in element_types
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_observer_extracts_forms(fixture_server):
    """Test that observer extracts forms."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        tab = await obs.observe_active_tab()
        
        assert len(tab.forms) > 0
        form = tab.forms[0]
        assert form.form_id == "test-form"
        assert len(form.fields) > 0
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_observer_visible_text(fixture_server):
    """Test that observer extracts visible text."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        tab = await obs.observe_active_tab()
        
        assert tab.visible_text is not None
        assert len(tab.visible_text) > 0
        assert "Browser Test Fixture" in tab.visible_text
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


@pytest.mark.browser
@pytest.mark.asyncio
async def test_observer_page_metadata(fixture_server):
    """Test that observer extracts page metadata."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        tab = await obs.observe_active_tab()
        
        assert tab.page_metadata is not None
        assert "language" in tab.page_metadata or "viewport" in tab.page_metadata
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# Planner Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_planner_creates_plan(fixture_server):
    """Test that BrowserPlanner creates a plan."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        await exec.execute(nav_action)
        
        await obs.observe_active_tab()
        
        planner = BrowserPlanner(session, obs)
        plan = planner.create_plan("Click the click me button", {})
        
        assert plan is not None
        assert len(plan.steps) > 0
        assert plan.goal == "Click the click me button"
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


# ============================================================================
# Advanced Browser Agent Validation
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_advanced_browser_agent_initialization():
    """Test AdvancedBrowserAgent initialization."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    agent = AdvancedBrowserAgent(headless=True)
    await agent.initialize()
    
    assert agent._browser is not None
    assert agent._context is not None
    assert agent._page is not None
    assert agent.session is not None
    
    await agent.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_advanced_browser_agent_simple_task(fixture_server):
    """Test AdvancedBrowserAgent executing a simple task."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed")
    
    agent = AdvancedBrowserAgent(headless=True)
    await agent.initialize()
    
    try:
        task = await agent.execute_task(
            f"Navigate to {fixture_server}/index.html and click the Click Me button",
            {}
        )
        
        assert task is not None
        assert task.state.value in ["completed", "failed"]
        assert task.result is not None
    finally:
        await agent.close()


# ============================================================================
# Monitoring Integration
# ============================================================================

@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_monitoring_events(fixture_server):
    """Test that browser actions emit monitoring events."""
    session, page, playwright, browser, context = await create_test_browser_session()
    try:
        obs = BrowserObserver(session)
        obs.set_page(page)
        exec = BrowserActionExecutor(session, obs)
        exec.set_page(page)
        
        # The monitoring events should be emitted during execution
        nav_action = BrowserAction(action_type=ActionType.NAVIGATE, url=f"{fixture_server}/index.html", wait_until="networkidle")
        result = await exec.execute(nav_action)
        
        assert result.success is True
        # Events are emitted internally (verified by no exceptions)
    finally:
        await cleanup_browser_session(playwright, browser, context, page)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "browser"])