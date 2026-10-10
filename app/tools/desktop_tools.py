"""Windows Desktop Automation Tools - Stage 20: Windows Desktop Agent.

Provides UI Automation for Windows applications using pywinauto.
If pywinauto is not available, tools return informative error messages.

Tools:
- desktop.list_windows: List top-level windows with titles and process info
- desktop.focus_window: Focus a window by title or process
- desktop.get_window_info: Get detailed info about a window (controls, etc.)
- desktop.click: Click a control within a window
- desktop.type: Type text into a control
- desktop.key_press: Send key presses to a window
- desktop.screenshot: Take screenshot of a window or region
- desktop.menu_select: Select a menu item
- desktop.drag_drop: Drag and drop between coordinates or controls
"""

from dataclasses import dataclass
from typing import Any

from app.tools.base import BaseTool

# Try to import pywinauto
try:
    import pywinauto
    from pywinauto import Application, Desktop, findwindows
    from pywinauto.findwindows import ElementNotFoundError
    from pywinauto.timings import TimeoutError
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False
    pywinauto = None  # type: ignore
    Application = None  # type: ignore
    Desktop = None  # type: ignore
    findwindows = None  # type: ignore
    ElementNotFoundError = Exception  # type: ignore
    TimeoutError = Exception  # type: ignore

# Optional: for screenshots
try:
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    ImageGrab = None  # type: ignore


class DesktopActionError(Exception):
    """Custom error for desktop automation failures."""


def _ensure_pywinauto():
    """Check if pywinauto is available, raise error if not."""
    if not PYWINAUTO_AVAILABLE:
        raise DesktopActionError(
            "pywinauto is not installed. Install with: pip install pywinauto"
        )


def _ensure_pil():
    """Check if PIL is available for screenshots."""
    if not PIL_AVAILABLE:
        raise DesktopActionError(
            "PIL (Pillow) is not installed for screenshots. Install with: pip install pillow"
        )


@dataclass
class WindowInfo:
    """Information about a window."""
    handle: int
    title: str
    class_name: str
    process_id: int
    executable: str
    is_visible: bool
    is_enabled: bool
    rectangle: dict[str, int]  # left, top, right, bottom
    child_controls: list[dict[str, Any]] = None


def _window_to_dict(window) -> dict[str, Any]:
    """Convert a pywinauto window object to a dictionary."""
    try:
        rect = window.rectangle()
        return {
            "handle": window.handle,
            "title": window.window_text(),
            "class_name": window.class_name(),
            "process_id": window.process_id(),
            "executable": getattr(window, 'executable', lambda: 'unknown')(),
            "is_visible": window.is_visible(),
            "is_enabled": window.is_enabled(),
            "rectangle": {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom,
                "width": rect.width(),
                "height": rect.height(),
            },
        }
    except Exception as e:
        return {
            "error": f"Failed to get window info: {e}",
            "handle": getattr(window, 'handle', -1),
        }


def _get_control_dict(control) -> dict[str, Any]:
    """Convert a pywinauto control to a dictionary."""
    try:
        # Try to get the element_info for more reliable properties (pywinauto 0.6.9+)
        if hasattr(control, 'element_info'):
            elem = control.element_info
            rect = control.rectangle()
            return {
                "handle": control.handle,
                "title": control.window_text(),
                "class_name": elem.class_name,
                "control_type": elem.control_type,
                "automation_id": elem.automation_id,
                "rectangle": {
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                    "width": rect.width(),
                    "height": rect.height(),
                },
                "is_visible": control.is_visible(),
                "is_enabled": control.is_enabled(),
            }
        else:
            # Fallback to the original method
            rect = control.rectangle()
            return {
                "handle": control.handle,
                "title": control.window_text(),
                "class_name": control.class_name(),
                "control_type": control.control_type(),
                "automation_id": control.automation_id(),
                "rectangle": {
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                    "width": rect.width(),
                    "height": rect.height(),
                },
                "is_visible": control.is_visible(),
                "is_enabled": control.is_enabled(),
            }
    except Exception as e:
        return {
            "error": f"Failed to get control info: {e}",
            "handle": getattr(control, 'handle', -1),
        }


class DesktopTool(BaseTool):
    """Base class for desktop tools with common error handling."""

    def _execute(self, func, *args, **kwargs):
        """Execute a function with error handling."""
        if not PYWINAUTO_AVAILABLE:
            return {
                "error": "pywinauto not installed. Install with: pip install pywinauto",
                "tool": self.name,
                "success": False,
            }

        try:
            return func(*args, **kwargs)
        except ElementNotFoundError as e:
            return {
                "error": f"Element not found: {e}",
                "tool": self.name,
                "success": False,
            }
        except TimeoutError as e:
            return {
                "error": f"Operation timed out: {e}",
                "tool": self.name,
                "success": False,
            }
        except Exception as e:
            return {
                "error": f"{type(e).__name__}: {e}",
                "tool": self.name,
                "success": False,
            }

    def _find_window(self, title="", title_contains="", process_id=0, executable="", handle=None, timeout=5000):
        """Find a window by various criteria. Returns a pywinauto window wrapper (UIAWrapper) ready for interaction."""
        # Try to find by handle first
        if handle is not None and handle != 0:
            try:
                return Desktop(backend="uia").window(handle=handle).wrapper_object()
            except Exception:
                pass
        # Try to find by criteria (title, title_contains, process_id, executable)
        criteria = {}
        if title:
            criteria["title"] = title
        if title_contains:
            criteria["title_re"] = f".*{title_contains}.*"
        if process_id:
            criteria["process"] = process_id
        if executable:
            criteria["exe"] = executable
        if criteria:
            try:
                app = Application(backend="uia").connect(**criteria)
                return app.window().wrapper_object()
            except Exception:
                pass
        # Fallback: iterate through desktop windows and try to match by criteria
        try:
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            for w in windows:
                try:
                    match = True
                    if title and w.window_text() != title:
                        match = False
                    if title_contains and title_contains not in w.window_text():
                        match = False
                    if process_id and w.process_id() != process_id:
                        match = False
                    if executable:
                        try:
                            if w.executable() != executable:
                                match = False
                        except:
                            match = False
                    if match:
                        return w
                except Exception:
                    continue
        except Exception:
            pass
        return None


class DesktopListWindowsTool(DesktopTool):
    """List top-level windows."""

    name = "desktop.list_windows"
    description = "List top-level windows with titles, process IDs, and executables"
    selection_phrases = ("list windows", "get windows", "window list", "show windows")
    parameters = {
        "type": "object",
        "properties": {
            "visible_only": {
                "type": "boolean",
                "description": "Only return visible windows",
                "default": True,
            },
            "include_process_info": {
                "type": "boolean",
                "description": "Include process executable path",
                "default": True,
            },
        },
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        visible_only = kwargs.get("visible_only", True)
        include_process_info = kwargs.get("include_process_info", True)

        def _list_windows():
            windows = Desktop(backend="uia").windows() if visible_only else Desktop(backend="uia").windows()
            result = []
            for w in windows:
                try:
                    info = _window_to_dict(w)
                    if not include_process_info:
                        info.pop("executable", None)
                        info.pop("process_id", None)
                    result.append(info)
                except Exception:
                    # Skip windows that cause errors
                    continue
            return {"windows": result, "count": len(result)}

        return self._execute(_list_windows)


class DesktopFocusWindowTool(DesktopTool):
    """Focus a window by title or process."""

    name = "desktop.focus_window"
    description = "Focus a window by title, process ID, or executable"
    selection_phrases = ("focus window", "activate window", "bring window to front")
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Window title (exact match)",
                "default": "",
            },
            "title_contains": {
                "type": "string",
                "description": "Window title substring match",
                "default": "",
            },
            "process_id": {
                "type": "integer",
                "description": "Process ID",
                "default": 0,
            },
            "executable": {
                "type": "string",
                "description": "Executable name (e.g., 'notepad.exe')",
                "default": "",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "anyOf": [
            {"required": ["title"]},
            {"required": ["title_contains"]},
            {"required": ["process_id"]},
            {"required": ["executable"]},
        ],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        title = kwargs.get("title", "")
        title_contains = kwargs.get("title_contains", "")
        process_id = kwargs.get("process_id", 0)
        executable = kwargs.get("executable", "")
        timeout = kwargs.get("timeout", 5000)

        if not any([title, title_contains, process_id, executable]):
            return {"success": False, "error": "Must specify title, title_contains, process_id, or executable"}

        window = self._find_window(title, title_contains, process_id, executable, timeout)
        if window is None:
            return {"success": False, "error": "No matching window found", "criteria": {"title": title, "title_contains": title_contains, "process_id": process_id, "executable": executable}}

        try:
            window.set_focus()
            info = _window_to_dict(window)
            return {
                "success": True,
                "focused": True,
                "window": info,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to focus window: {e}"}


class DesktopGetWindowInfoTool(DesktopTool):
    """Get detailed information about a window."""

    name = "desktop.get_window_info"
    description = "Get detailed information about a window including its controls"
    selection_phrases = ("get window info", "inspect window", "window details", "window hierarchy")
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Window title (exact match)",
                "default": "",
            },
            "title_contains": {
                "type": "string",
                "description": "Window title substring match",
                "default": "",
            },
            "process_id": {
                "type": "integer",
                "description": "Process ID",
                "default": 0,
            },
            "executable": {
                "type": "string",
                "description": "Executable name",
                "default": "",
            },
            "handle": {
                "type": "integer",
                "description": "Window handle",
                "default": 0,
            },
            "include_children": {
                "type": "boolean",
                "description": "Include child controls in the output",
                "default": True,
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to traverse for child controls",
                "default": 3,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "anyOf": [
            {"required": ["title"]},
            {"required": ["title_contains"]},
            {"required": ["process_id"]},
            {"required": ["executable"]},
            {"required": ["handle"]},
        ],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        title = kwargs.get("title", "")
        title_contains = kwargs.get("title_contains", "")
        process_id = kwargs.get("process_id", 0)
        executable = kwargs.get("executable", "")
        handle = kwargs.get("handle", 0)
        include_children = kwargs.get("include_children", True)
        max_depth = kwargs.get("max_depth", 3)
        timeout = kwargs.get("timeout", 5000)

        if not any([title, title_contains, process_id, executable, handle]):
            return {"success": False, "error": "Must specify title, title_contains, process_id, executable, or handle"}

        window = self._find_window(title, title_contains, process_id, executable, handle, timeout)
        if window is None:
            return {"success": False, "error": "No matching window found", "criteria": {"title": title, "title_contains": title_contains, "process_id": process_id, "executable": executable, "handle": handle}}

        try:
            info = _window_to_dict(window)

            if include_children:
                def _get_children(control, depth=0):
                    if depth >= max_depth:
                        return []
                    children = []
                    try:
                        for child in control.children():
                            child_info = _get_control_dict(child)
                            child_info["children"] = _get_children(child, depth+1)
                            children.append(child_info)
                    except Exception:
                        pass
                    return children

                info["children"] = _get_children(window)

            return {
                "success": True,
                "window": info,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to get window info: {e}"}


class DesktopClickTool(DesktopTool):
    """Click a control within a window."""

    name = "desktop.click"
    description = "Click a control within a window by automation_id, title, or control_type"
    selection_phrases = ("click", "click button", "click link", "press button")
    parameters = {
        "type": "object",
        "properties": {
            # Window identification (same as get_window_info)
            "title": {"type": "string", "default": ""},
            "title_contains": {"type": "string", "default": ""},
            "process_id": {"type": "integer", "default": 0},
            "executable": {"type": "string", "default": ""},
            # Control identification
            "automation_id": {"type": "string", "default": ""},
            "control_title": {"type": "string", "default": ""},  # control title
            "control_type": {"type": "string", "default": ""},
            "found_index": {"type": "integer", "default": 0, "description": "If multiple matches, which one (0-based)"},
            "click_type": {
                "type": "string",
                "enum": ["left", "right", "double"],
                "default": "left",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "required": [],  # At least one window and one control id needed
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        # Window params
        w_title = kwargs.get("title", "")
        w_title_contains = kwargs.get("title_contains", "")
        w_process_id = kwargs.get("process_id", 0)
        w_executable = kwargs.get("executable", "")
        # Control params
        automation_id = kwargs.get("automation_id", "")
        c_title = kwargs.get("control_title", "")
        control_type = kwargs.get("control_type", "")
        found_index = kwargs.get("found_index", 0)
        click_type = kwargs.get("click_type", "left")
        timeout = kwargs.get("timeout", 5000)

        if not any([w_title, w_title_contains, w_process_id, w_executable]):
            return {"success": False, "error": "Must specify window via title, title_contains, process_id, or executable"}
        if not any([automation_id, c_title, control_type]):
            return {"success": False, "error": "Must specify control via automation_id, title, or control_type"}

        # Find window
        window = self._find_window(w_title, w_title_contains, w_process_id, w_executable, timeout)
        if window is None:
            return {"success": False, "error": "No matching window found", "criteria": {"title": w_title, "title_contains": w_title_contains, "process_id": w_process_id, "executable": w_executable}}

        try:
            # Find control by iterating through descendants
            def matches_criteria(control):
                try:
                    if automation_id and control.automation_id() != automation_id:
                        return False
                    if c_title and control.window_text() != c_title:
                        return False
                    if control_type:
                        # Use element_info for control_type on UIAWrapper
                        if hasattr(control, 'element_info'):
                            if control.element_info.control_type != control_type:
                                return False
                        else:
                            if control.control_type() != control_type:
                                return False
                    return True
                except Exception:
                    return False

            # Get all descendants (since UIAWrapper uses descendants() not child_window())
            try:
                descendants = window.descendants()
            except Exception:
                # Fallback to children() if descendants() fails
                descendants = window.children()
            
            matching_controls = [c for c in descendants if matches_criteria(c)]
            
            if not matching_controls:
                return {"success": False, "error": "No matching control found"}
                
            if found_index >= len(matching_controls):
                return {"success": False, "error": f"found_index {found_index} out of range for {len(matching_controls)} matches"}
                
            control = matching_controls[found_index]

            # Click using click_input (works on UIAWrapper)
            if click_type == "left":
                control.click_input()
            elif click_type == "right":
                control.right_click_input()
            elif click_type == "double":
                control.double_click_input()

            return {
                "success": True,
                "clicked": True,
                "click_type": click_type,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to click: {e}"}


class DesktopTypeTool(DesktopTool):
    """Type text into a control."""

    name = "desktop.type"
    description = "Type text into a control (edit box)"
    selection_phrases = ("type", "type text", "enter text", "fill field")
    parameters = {
        "type": "object",
        "properties": {
            # Window identification
            "title": {"type": "string", "default": ""},
            "title_contains": {"type": "string", "default": ""},
            "process_id": {"type": "integer", "default": 0},
            "executable": {"type": "string", "default": ""},
            # Control identification
            "automation_id": {"type": "string", "default": ""},
            "title": {"type": "string", "default": ""},  # control title
            "control_type": {"type": "string", "default": ""},
            "found_index": {"type": "integer", "default": 0},
            # Text to type
            "text": {
                "type": "string",
                "description": "Text to type",
            },
            "clear_first": {
                "type": "boolean",
                "description": "Clear the field before typing",
                "default": True,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        text = kwargs.get("text", "")
        clear_first = kwargs.get("clear_first", True)
        timeout = kwargs.get("timeout", 5000)
        # Window params
        w_title = kwargs.get("title", "")
        w_title_contains = kwargs.get("title_contains", "")
        w_process_id = kwargs.get("process_id", 0)
        w_executable = kwargs.get("executable", "")
        # Control params
        automation_id = kwargs.get("automation_id", "")
        c_title = kwargs.get("title", "")
        control_type = kwargs.get("control_type", "")
        found_index = kwargs.get("found_index", 0)

        if not text:
            return {"success": False, "error": "No text provided to type"}
        if not any([w_title, w_title_contains, w_process_id, w_executable]):
            return {"success": False, "error": "Must specify window via title, title_contains, process_id, or executable"}
        if not any([automation_id, c_title, control_type]):
            return {"success": False, "error": "Must specify control via automation_id, title, or control_type"}

        # Find window
        window = self._find_window(w_title, w_title_contains, w_process_id, w_executable, timeout)
        if window is None:
            return {"success": False, "error": "No matching window found", "criteria": {"title": w_title, "title_contains": w_title_contains, "process_id": w_process_id, "executable": w_executable}}

        try:
            # Find control by iterating through descendants
            def matches_criteria(control):
                try:
                    if automation_id and control.automation_id() != automation_id:
                        return False
                    if c_title and control.window_text() != c_title:
                        return False
                    if control_type:
                        # Use element_info for control_type on UIAWrapper
                        if hasattr(control, 'element_info'):
                            if control.element_info.control_type != control_type:
                                return False
                        else:
                            if control.control_type() != control_type:
                                return False
                    return True
                except Exception:
                    return False

            # Get all descendants (since UIAWrapper uses descendants() not child_window())
            try:
                descendants = window.descendants()
            except Exception:
                # Fallback to children() if descendants() fails
                descendants = window.children()
            
            matching_controls = [c for c in descendants if matches_criteria(c)]
            
            if not matching_controls:
                return {"success": False, "error": "No matching control found"}
                
            if found_index >= len(matching_controls):
                return {"success": False, "error": f"found_index {found_index} out of range for {len(matching_controls)} matches"}
                
            control = matching_controls[found_index]

            # Clear if requested
            if clear_first:
                try:
                    control.set_edit_text("")
                except:
                    # Try to select all and delete using type_keys
                    control.type_keys("^a{DELETE}")

            # Type text
            control.type_keys(text, with_spaces=True)

            return {
                "success": True,
                "typed": True,
                "text_length": len(text),
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to type text: {e}"}


class DesktopKeyPressTool(DesktopTool):
    """Send key presses to a window."""

    name = "desktop.key_press"
    description = "Send key presses to a window (supports special keys like {ENTER}, {TAB})"
    selection_phrases = ("send keys", "key press", "send keystrokes", "press key")
    parameters = {
        "type": "object",
        "properties": {
            # Window identification
            "title": {"type": "string", "default": ""},
            "title_contains": {"type": "string", "default": ""},
            "process_id": {"type": "integer", "default": 0},
            "executable": {"type": "string", "default": ""},
            # Keys to send
            "keys": {
                "type": "string",
                "description": "Keys to send (e.g., '{ENTER}', 'hello{TAB}world')",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "required": ["keys"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        keys = kwargs.get("keys", "")
        timeout = kwargs.get("timeout", 5000)
        # Window params
        w_title = kwargs.get("title", "")
        w_title_contains = kwargs.get("title_contains", "")
        w_process_id = kwargs.get("process_id", 0)
        w_executable = kwargs.get("executable", "")

        if not keys:
            return {"success": False, "error": "No keys provided"}
        if not any([w_title, w_title_contains, w_process_id, w_executable]):
            return {"success": False, "error": "Must specify window via title, title_contains, process_id, or executable"}

        # Find window
        window = self._find_window(w_title, w_title_contains, w_process_id, w_executable, timeout)
        if window is None:
            return {"success": False, "error": "No matching window found", "criteria": {"title": w_title, "title_contains": w_title_contains, "process_id": w_process_id, "executable": w_executable}}

        try:
            # Send keys
            window.type_keys(keys, with_spaces=True)

            return {
                "success": True,
                "keys_sent": True,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to send keys: {e}"}


class DesktopScreenshotTool(DesktopTool):
    """Take a screenshot of a window or region."""

    name = "desktop.screenshot"
    description = "Take a screenshot of a window, region, or entire screen"
    selection_phrases = ("screenshot", "take screenshot", "capture screen", "screen capture")
    parameters = {
        "type": "object",
        "properties": {
            # Window identification (optional, defaults to active window or screen)
            "title": {"type": "string", "default": ""},
            "title_contains": {"type": "string", "default": ""},
            "process_id": {"type": "integer", "default": 0},
            "executable": {"type": "string", "default": ""},
            # Region (optional, overrides window)
            "left": {"type": "integer", "description": "Left coordinate"},
            "top": {"type": "integer", "description": "Top coordinate"},
            "right": {"type": "integer", "description": "Right coordinate"},
            "bottom": {"type": "integer", "description": "Bottom coordinate"},
            "width": {"type": "integer", "description": "Width (if left/top provided)"},
            "height": {"type": "integer", "description": "Height (if left/top provided)"},
            # Output
            "save_path": {
                "type": "string",
                "description": "Path to save screenshot (PNG). If not provided, returns base64.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
            },
        },
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        save_path = kwargs.get("save_path")
        timeout = kwargs.get("timeout", 5000)
        # Window params
        w_title = kwargs.get("title", "")
        w_title_contains = kwargs.get("title_contains", "")
        w_process_id = kwargs.get("process_id", 0)
        w_executable = kwargs.get("executable", "")
        # Region params
        left = kwargs.get("left")
        top = kwargs.get("top")
        right = kwargs.get("right")
        bottom = kwargs.get("bottom")
        width = kwargs.get("width")
        height = kwargs.get("height")

        def _screenshot():
            if not PIL_AVAILABLE:
                return {"error": "PIL (Pillow) not installed for screenshots. Install with: pip install pillow"}

            # Determine region
            region = None
            if left is not None and top is not None:
                if right is not None and bottom is not None:
                    region = (left, top, right, bottom)
                elif width is not None and height is not None:
                    region = (left, top, left + width, top + height)
                else:
                    return {"error": "If left/top provided, need either right/bottom or width/height"}

            # If no region specified, try to get window
            if region is None:
                if not any([w_title, w_title_contains, w_process_id, w_executable]):
                    # No window specified, capture entire screen
                    img = ImageGrab.grab()
                else:
                    # Find window
                    window = self._find_window(w_title, w_title_contains, w_process_id, w_executable, timeout)
                    if window is not None:
                        try:
                            rect = window.rectangle()
                            region = (rect.left, rect.top, rect.right, rect.bottom)
                        except Exception:
                            # Fallback to full screen
                            img = ImageGrab.grab()
                    else:
                        # Fallback to full screen
                        img = ImageGrab.grab()
                    if region is not None:
                        img = ImageGrab.grab(bbox=region)
                    else:
                        img = ImageGrab.grab()
            else:
                img = ImageGrab.grab(bbox=region)

            # Save or return base64
            if save_path:
                img.save(save_path, format="PNG")
                return {
                    "success": True,
                    "saved": True,
                    "path": save_path,
                    "size": img.size,
                }
            else:
                import base64
                from io import BytesIO
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                return {
                    "success": True,
                    "screenshot_base64": img_str,
                    "size": img.size,
                    "format": "PNG",
                }

        return self._execute(_screenshot)


def create_desktop_tools() -> list[BaseTool]:
    """Create all desktop automation tools."""
    return [
        DesktopListWindowsTool(),
        DesktopFocusWindowTool(),
        DesktopGetWindowInfoTool(),
        DesktopClickTool(),
        DesktopTypeTool(),
        DesktopKeyPressTool(),
        DesktopScreenshotTool(),
        # TODO: Add more tools like menu_select, drag_drop, etc.
    ]


# For testing when module is run directly
if __name__ == "__main__":
    # Simple test
    tools = create_desktop_tools()
    print(f"Created {len(tools)} desktop tools:")
    for t in tools:
        print(f"  - {t.name}: {t.description[:50]}...")
