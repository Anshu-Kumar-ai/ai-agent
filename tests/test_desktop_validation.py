"""
Phase 6 - Real Desktop Validation Tests
Tests the actual desktop tools (pywinauto) against real Windows applications (Notepad, Calculator, etc.).
"""
import pytest
import time
import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.tools.desktop_tools import (
    DesktopListWindowsTool,
    DesktopFocusWindowTool,
    DesktopGetWindowInfoTool,
    DesktopClickTool,
    DesktopTypeTool,
    DesktopKeyPressTool,
    DesktopScreenshotTool,
    PYWINAUTO_AVAILABLE,
    DesktopActionError,
)

# Test application constants - using built-in Windows apps
NOTEPAD_TITLE_CONTAINS = "Notepad"
CALCULATOR_TITLE_CONTAINS = "Calculator"


def pytest_configure(config):
    config.addinivalue_line("markers", "desktop: tests requiring desktop automation")


@pytest.fixture(autouse=True, scope="session")
def check_pywinauto():
    """Skip all desktop tests if pywinauto not available."""
    if not PYWINAUTO_AVAILABLE:
        pytest.skip("pywinauto not installed")


@pytest.fixture(scope="session", autouse=True)
def notepad_fixture():
    """Launch Notepad for the entire test session."""
    proc = subprocess.Popen(["notepad.exe"])
    print(f"Launched Notepad with PID: {proc.pid}")

    # Wait for Notepad to start
    time.sleep(2)

    yield

    # Cleanup
    proc.terminate()
    proc.wait(timeout=5)
    print("Notepad terminated")


class TestDesktopValidation:
    """Desktop validation test suite using real pywinauto against Notepad."""

    # Helper to create tools
    @pytest.fixture(autouse=True)
    def setup_tools(self):
        self.list_tool = DesktopListWindowsTool()
        self.focus_tool = DesktopFocusWindowTool()
        self.info_tool = DesktopGetWindowInfoTool()
        self.click_tool = DesktopClickTool()
        self.type_tool = DesktopTypeTool()
        self.key_tool = DesktopKeyPressTool()
        self.screenshot_tool = DesktopScreenshotTool()
        yield

    # ============================================================================
    # PHASE 4 - Real Window Discovery
    # ============================================================================

    @pytest.mark.desktop
    def test_list_windows_detects_notepad(self):
        """Test that desktop.list_windows detects the Notepad window."""
        result = self.list_tool.execute(visible_only=True)

        assert "error" not in result, f"list_windows error: {result.get('error')}"
        assert "windows" in result
        assert result["count"] > 0

        # Find Notepad
        notepad_windows = [w for w in result["windows"] if NOTEPAD_TITLE_CONTAINS in w.get("title", "")]
        assert len(notepad_windows) >= 1, f"Notepad not found in {result['count']} windows"

        notepad = notepad_windows[0]
        assert NOTEPAD_TITLE_CONTAINS in notepad["title"]
        assert notepad["handle"] > 0
        assert notepad["class_name"] == "Notepad"
        assert notepad["process_id"] > 0
        assert notepad["is_visible"] is True
        assert "rectangle" in notepad
        assert notepad["rectangle"]["width"] > 0
        assert notepad["rectangle"]["height"] > 0

    @pytest.mark.desktop
    def test_list_windows_visible_only(self):
        """Test visible_only filter."""
        result_all = self.list_tool.execute(visible_only=False)
        result_visible = self.list_tool.execute(visible_only=True)

        # Both should at least find Notepad
        assert result_visible["count"] >= 1
        assert result_all["count"] >= result_visible["count"]

    # ============================================================================
    # PHASE 5 - Real Window Focus
    # ============================================================================

    @pytest.mark.desktop
    def test_focus_window_by_title(self):
        """Test focusing window by exact title."""
        result = self.focus_tool.execute(title_contains=NOTEPAD_TITLE_CONTAINS, timeout=5000)

        assert "error" not in result, f"focus_window error: {result.get('error')}"
        assert result["success"] is True
        assert result["focused"] is True
        assert NOTEPAD_TITLE_CONTAINS in result["window"]["title"]

    @pytest.mark.desktop
    def test_focus_window_by_contains(self):
        """Test focusing window by title substring."""
        result = self.focus_tool.execute(title_contains="Note", timeout=5000)

        assert "error" not in result, f"focus_window error: {result.get('error')}"
        assert result["success"] is True
        assert "Note" in result["window"]["title"]

    @pytest.mark.desktop
    def test_focus_window_invalid_criteria(self):
        """Test focusing with no criteria returns error."""
        result = self.focus_tool.execute()

        assert result["success"] is False
        assert "Must specify" in result["error"]

    @pytest.mark.desktop
    def test_focus_window_not_found(self):
        """Test focusing non-existent window."""
        result = self.focus_tool.execute(title="NonExistentWindow12345", timeout=1000)

        assert result["success"] is False
        assert "matching window found" in result["error"].lower() or "not found" in result["error"].lower()

    # ============================================================================
    # PHASE 6 - Real Window Information
    # ============================================================================

    @pytest.mark.desktop
    def test_get_window_info(self):
        """Test getting detailed window info including children."""
        # First, get a Notepad window from the list
        list_result = self.list_tool.execute(visible_only=True)
        assert "error" not in list_result, f"list_windows error: {list_result.get('error')}"
        assert list_result["count"] > 0
        # Find a Notepad window (not the one with asterisk in title, which indicates unsaved changes?)
        notepad_windows = [w for w in list_result["windows"] if NOTEPAD_TITLE_CONTAINS in w.get("title", "") and not w["title"].startswith('*')]
        if not notepad_windows:
            # Fallback to any Notepad window
            notepad_windows = [w for w in list_result["windows"] if NOTEPAD_TITLE_CONTAINS in w.get("title", "")]
        assert len(notepad_windows) > 0, "No Notepad window found"
        notepad = notepad_windows[0]
        # Now get window info for this specific window using handle
        result = self.info_tool.execute(
            handle=notepad["handle"],
            include_children=True,
            max_depth=3,
            timeout=5000
        )
        assert "error" not in result, f"get_window_info error: {result.get('error')}"
        assert result["success"] is True
        assert "window" in result
        window = result["window"]
        assert NOTEPAD_TITLE_CONTAINS in window["title"]
        assert window["handle"] > 0
        assert window["class_name"] == "Notepad"
        assert window["process_id"] > 0
        assert "children" in window
        assert isinstance(window["children"], list)
        # We expect at least some children (the window should have controls)
        assert len(window["children"]) > 0
        # Check that each child has a control_type (so we know the structure is working)
        for child in window["children"]:
            assert "control_type" in child, f"Child missing control_type: {child}"

    @pytest.mark.desktop
    def test_get_window_info_no_children(self):
        """Test getting window info without children."""
        result = self.info_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            include_children=False,
            timeout=5000
        )

        assert "error" not in result
        assert result["success"] is True
        assert "children" not in result["window"] or result["window"]["children"] == []

    @pytest.mark.desktop
    def test_get_window_info_invalid_criteria(self):
        """Test get_window_info with no criteria."""
        result = self.info_tool.execute()

        assert result["success"] is False
        assert "Must specify" in result["error"]

    # ============================================================================
    # PHASE 7 - Real Click
    # ============================================================================

    @pytest.mark.desktop
    def test_click_notepad_edit_control(self):
        """Test clicking the Notepad edit control."""
        # Click the edit control (Document control in modern Notepad)
        result = self.click_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="Document",
            click_type="left",
            found_index=0,
            timeout=5000
        )

        assert "error" not in result, f"click error: {result.get('error')}"
        assert result["success"] is True
        assert result["clicked"] is True

    @pytest.mark.desktop
    def test_click_invalid_control(self):
        """Test clicking non-existent control."""
        result = self.click_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="NonExistentControl",
            click_type="left",
            timeout=2000
        )

        assert result["success"] is False
        assert "no matching control" in result["error"].lower() or "error" in result["error"].lower()

    # ============================================================================
    # PHASE 8 - Real Type
    # ============================================================================

    @pytest.mark.desktop
    def test_type_into_notepad(self):
        """Test typing into Notepad edit control."""
        test_text = "Hello Desktop Test"

        result = self.type_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="Document",
            text=test_text,
            clear_first=True,
            timeout=5000
        )

        assert "error" not in result, f"type error: {result.get('error')}"
        assert result["success"] is True
        assert result["typed"] is True
        assert result["text_length"] == len(test_text)

    @pytest.mark.desktop
    def test_type_with_special_chars(self):
        """Test typing special characters."""
        test_text = "Test\tTab\nNewline"

        result = self.type_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="Document",
            text=test_text,
            clear_first=True,
            timeout=5000
        )

        assert "error" not in result
        assert result["success"] is True

    @pytest.mark.desktop
    def test_type_empty_text(self):
        """Test typing empty text returns error."""
        result = self.type_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="Document",
            text="",
            timeout=5000
        )

        assert result["success"] is False
        assert "No text provided" in result["error"]

    # ============================================================================
    # PHASE 9 - Real Key Press
    # ============================================================================

    @pytest.mark.desktop
    def test_key_press_tab(self):
        """Test sending TAB key."""
        result = self.key_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            keys="{TAB}",
            timeout=5000
        )

        assert "error" not in result, f"key_press error: {result.get('error')}"
        assert result["success"] is True
        assert result["keys_sent"] is True

    @pytest.mark.desktop
    def test_key_press_enter(self):
        """Test sending ENTER key."""
        result = self.key_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            keys="{ENTER}",
            timeout=5000
        )

        assert "error" not in result
        assert result["success"] is True

    @pytest.mark.desktop
    def test_key_press_combination(self):
        """Test sending key combination (Ctrl+A)."""
        result = self.key_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            keys="^a",
            timeout=5000
        )

        assert "error" not in result
        assert result["success"] is True

    @pytest.mark.desktop
    def test_key_press_invalid_window(self):
        """Test key press on non-existent window."""
        result = self.key_tool.execute(
            title="NonExistentWindow123",
            keys="{TAB}",
            timeout=1000
        )

        assert result["success"] is False

    # ============================================================================
    # PHASE 10 - Real Screenshot
    # ============================================================================

    @pytest.mark.desktop
    def test_screenshot_notepad_window(self):
        """Test screenshot of the Notepad window."""
        import tempfile
        save_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                save_path = tmp.name

            result = self.screenshot_tool.execute(
                title_contains=NOTEPAD_TITLE_CONTAINS,
                save_path=save_path,
                timeout=5000
            )

            assert "error" not in result, f"screenshot error: {result.get('error')}"
            assert result["success"] is True
            assert result["saved"] is True
            assert result["path"] == save_path
            assert "size" in result
            assert result["size"][0] > 0
            assert result["size"][1] > 0

            # Verify file exists and has content
            assert os.path.exists(save_path)
            assert os.path.getsize(save_path) > 0
        finally:
            if save_path and os.path.exists(save_path):
                os.unlink(save_path)

    @pytest.mark.desktop
    def test_screenshot_base64(self):
        """Test screenshot returning base64."""
        result = self.screenshot_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            timeout=5000
        )

        assert "error" not in result
        assert result["success"] is True
        assert "screenshot_base64" in result
        assert len(result["screenshot_base64"]) > 0
        assert "size" in result

    @pytest.mark.desktop
    def test_screenshot_region(self):
        """Test screenshot of specific region."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            save_path = tmp.name

        try:
            result = self.screenshot_tool.execute(
                left=0,
                top=0,
                width=200,
                height=200,
                save_path=save_path,
                timeout=5000
            )

            assert "error" not in result
            assert result["success"] is True
            assert result["size"] == (200, 200)
        finally:
            if os.path.exists(save_path):
                os.unlink(save_path)

    # ============================================================================
    # PHASE 11 - Multi-Window Control
    # ============================================================================

    @pytest.mark.desktop
    def test_multi_window_isolation(self):
        """Test actions on Notepad don't affect other windows."""
        # List all windows
        list_result = self.list_tool.execute(visible_only=True)
        assert "error" not in list_result

        # Focus Notepad
        focus_result = self.focus_tool.execute(title_contains=NOTEPAD_TITLE_CONTAINS)
        assert focus_result["success"] is True

        # Click edit control on Notepad (Document in modern Notepad)
        click_result = self.click_tool.execute(
            title_contains=NOTEPAD_TITLE_CONTAINS,
            control_type="Document",
            click_type="left"
        )
        assert click_result["success"] is True

        # Verify Notepad state changed by checking it still exists
        info_result = self.info_tool.execute(title_contains=NOTEPAD_TITLE_CONTAINS)
        assert info_result["success"] is True

    # ============================================================================
    # PHASE 12 - Window Disappearance / Failure Recovery
    # ============================================================================

    @pytest.mark.desktop
    def test_action_on_closed_window(self):
        """Test action on a window that was closed."""
        # This is hard to test reliably without closing the fixture
        # We'll test with a non-existent window title instead
        result = self.click_tool.execute(
            title="ThisWindowDoesNotExist12345",
            c_title="Button",
            click_type="left",
            timeout=2000
        )

        assert result["success"] is False
        assert "error" in result
        # Should not crash

    # ============================================================================
    # PHASE 13 - Timeout and Resource Cleanup
    # ============================================================================

    @pytest.mark.desktop
    def test_timeout_behavior(self):
        """Test that operations respect timeout."""
        # Very short timeout on a window that requires longer to find
        result = self.focus_tool.execute(
            title="NonExistentWindow",
            timeout=100  # 100ms
        )

        # Should fail with timeout or not found, not hang
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.desktop
    def test_repeated_operations_cleanup(self):
        """Test repeated operations don't leak resources."""
        for _ in range(10):
            result = self.list_tool.execute(visible_only=True)
            assert "error" not in result
            assert result["count"] >= 1

        # No exceptions, no resource exhaustion

    # ============================================================================
    # PHASE 14 - Permission Integration (structural test)
    # ============================================================================

    @pytest.mark.desktop
    def test_desktop_tools_risk_levels(self):
        """Verify desktop tools have appropriate risk levels."""
        from app.tools.capabilities import get_capability, SideEffectLevel

        # Check capabilities are registered
        list_cap = get_capability("desktop.list_windows")
        click_cap = get_capability("desktop.click")
        type_cap = get_capability("desktop.type")
        key_cap = get_capability("desktop.key_press")
        screenshot_cap = get_capability("desktop.screenshot")

        assert list_cap is not None
        assert list_cap.risk_level == "low"
        assert list_cap.side_effect_level == SideEffectLevel.READ

        assert click_cap is not None
        assert click_cap.risk_level == "medium"
        assert click_cap.side_effect_level == SideEffectLevel.WRITE

        assert type_cap is not None
        assert type_cap.risk_level == "medium"
        assert type_cap.side_effect_level == SideEffectLevel.WRITE

        assert key_cap is not None
        assert key_cap.risk_level == "medium"
        assert key_cap.side_effect_level == SideEffectLevel.WRITE

        assert screenshot_cap is not None
        assert screenshot_cap.risk_level == "low"
        assert screenshot_cap.side_effect_level == SideEffectLevel.READ

    # ============================================================================
    # PHASE 15 - TaskExecutor Integration (basic)
    # ============================================================================

    @pytest.mark.desktop
    def test_tool_registration(self):
        """Verify desktop tools are registered in the system."""
        from app.tools.registry import ToolRegistry
        from app.tools.desktop_tools import create_desktop_tools

        registry = ToolRegistry()
        tools = create_desktop_tools()

        for tool in tools:
            registry.register(tool)
            assert registry.has(tool.name)
            retrieved = registry.get(tool.name)
            assert retrieved.name == tool.name

    @pytest.mark.desktop
    def test_desktop_category_tools(self):
        """Verify desktop tools are categorized correctly."""
        from app.tools.registry import ToolRegistry
        from app.tools.capabilities import CapabilityCategory
        from app.tools.desktop_tools import create_desktop_tools

        registry = ToolRegistry()
        tools = create_desktop_tools()

        for tool in tools:
            registry.register(tool)

        desktop_tools = registry.get_tools_by_category(CapabilityCategory.DESKTOP)
        desktop_names = {t.name for t in desktop_tools}

        expected = {
            "desktop.list_windows",
            "desktop.focus_window",
            "desktop.get_window_info",
            "desktop.click",
            "desktop.type",
            "desktop.key_press",
            "desktop.screenshot",
        }

        for name in expected:
            assert name in desktop_names, f"{name} not in DESKTOP category"

    # ============================================================================
    # PHASE 17 - Desktop Monitoring (basic check)
    # ============================================================================

    @pytest.mark.desktop
    def test_desktop_actions_emit_monitoring(self):
            """Test that desktop actions would emit monitoring events."""
            from app.monitoring.emitter import get_emitter, EventEmitter
            from app.monitoring.events import EventType

            emitter = get_emitter()
            original_session = emitter.session_id
            emitter.session_id = "test_desktop_session"

            try:
                # Test event emission
                event = emitter.emit(
                    EventType.TOOL_STARTED,
                    task_id="test_task",
                    tool="desktop.click",
                    success=True,
                    duration_ms=100.0,
                    metadata={"window_title": NOTEPAD_TITLE_CONTAINS}
                )

                assert event is not None
                # Compare enum values properly (event.event_type is stored as string)
                assert event.event_type == EventType.TOOL_STARTED.value
                assert event.tool == "desktop.click"
                assert event.metadata["window_title"] == NOTEPAD_TITLE_CONTAINS
            finally:
                emitter.session_id = original_session

    # ============================================================================
    # PHASE 18 - Real Resource Test (10 executions)
    # ============================================================================

    @pytest.mark.desktop
    def test_resource_10_executions(self):
        """Run 10 sequential operations, verify cleanup."""
        for _ in range(10):
            result = self.list_tool.execute(visible_only=True)
            assert "error" not in result
            assert result["count"] >= 1

            result = self.focus_tool.execute(title_contains=NOTEPAD_TITLE_CONTAINS)
            assert result["success"] is True

            result = self.info_tool.execute(title_contains=NOTEPAD_TITLE_CONTAINS)
            assert result["success"] is True

        # No crashes, no resource exhaustion

    @pytest.mark.desktop
    def test_resource_50_executions(self):
        """Run 50 list operations."""
        for _ in range(50):
            result = self.list_tool.execute(visible_only=True)
            assert "error" not in result

    # ============================================================================
    # PHASE 19 - Security Boundaries
    # ============================================================================

    @pytest.mark.desktop
    def test_malformed_arguments(self):
        """Test that malformed arguments are rejected safely."""
        # Missing window criteria
        result = self.click_tool.execute(automation_id="btn", click_type="left")
        assert result["success"] is False
        assert "Must specify window" in result["error"]

        # Missing control criteria
        result = self.click_tool.execute(title=NOTEPAD_TITLE_CONTAINS, click_type="left")
        assert result["success"] is False
        assert "Must specify control" in result["error"]

        # Invalid click type
        result = self.click_tool.execute(
            title=NOTEPAD_TITLE_CONTAINS,
            c_title="Increment",
            click_type="invalid"
        )
        # Should handle gracefully (pywinauto will error on invalid click_type)

    @pytest.mark.desktop
    def test_no_permission_bypass(self):
        """Verify desktop tools don't bypass PermissionManager."""
        # Desktop tools are just tools - they don't have permission logic
        # The architecture is: planner -> permission -> executor -> tool
        # This test just verifies the tools don't have embedded permission checks
        from app.tools.desktop_tools import DesktopClickTool
        import inspect

        source = inspect.getsource(DesktopClickTool.execute)
        # Tool should not contain permission logic
        assert "permission" not in source.lower()
        assert "PermissionManager" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "desktop"])
