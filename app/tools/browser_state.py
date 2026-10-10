"""Browser State Management - Stage 18: Computer Use Foundation.

Core data structures for browser perception, session management, and state tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TabStatus(Enum):
    """Status of a browser tab."""
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    CLOSED = "closed"


class ElementType(Enum):
    """Types of interactive elements."""
    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    IMAGE = "image"
    TABLE = "table"
    FORM = "form"
    IFRAME = "iframe"
    GENERIC = "generic"


@dataclass
class BrowserElement:
    """Represents an interactive element on the page."""
    element_id: str  # Playwright locator or reference
    element_type: ElementType
    role: str | None = None  # ARIA role
    label: str | None = None  # Accessible name/label
    placeholder: str | None = None
    text: str | None = None  # Visible text
    value: str | None = None  # Current value (for inputs)
    href: str | None = None  # For links
    selector: str | None = None  # CSS/XPath selector
    bounding_box: dict[str, float] | None = None  # x, y, width, height
    is_visible: bool = True
    is_enabled: bool = True
    is_editable: bool = False
    attributes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "type": self.element_type.value,
            "role": self.role,
            "label": self.label,
            "placeholder": self.placeholder,
            "text": self.text,
            "value": self.value,
            "href": self.href,
            "selector": self.selector,
            "bounding_box": self.bounding_box,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "is_editable": self.is_editable,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserElement:
        # Accept both "element_type" (from observer) and "type" (legacy) for compatibility
        element_type_key = data.get("element_type", data.get("type"))
        return cls(
            element_id=data["element_id"],
            element_type=ElementType(element_type_key),
            role=data.get("role"),
            label=data.get("label"),
            placeholder=data.get("placeholder"),
            text=data.get("text"),
            value=data.get("value"),
            href=data.get("href"),
            selector=data.get("selector"),
            bounding_box=data.get("bounding_box"),
            is_visible=data.get("is_visible", True),
            is_enabled=data.get("is_enabled", True),
            is_editable=data.get("is_editable", False),
            attributes=data.get("attributes", {}),
        )


@dataclass
class BrowserForm:
    """Represents a form on the page."""
    form_id: str
    action: str | None = None
    method: str = "GET"
    fields: list[BrowserElement] = field(default_factory=list)
    submit_button: BrowserElement | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "form_id": self.form_id,
            "action": self.action,
            "method": self.method,
            "fields": [f.to_dict() for f in self.fields],
            "submit_button": self.submit_button.to_dict() if self.submit_button else None,
        }


@dataclass
class BrowserTab:
    """Represents a single browser tab."""
    tab_id: str
    url: str
    title: str
    status: TabStatus = TabStatus.READY
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    # Perception data (updated by Observer)
    accessibility_tree: str | None = None
    visible_text: str | None = None
    screenshot_path: str | None = None
    interactive_elements: list[BrowserElement] = field(default_factory=list)
    forms: list[BrowserForm] = field(default_factory=list)
    page_metadata: dict[str, Any] = field(default_factory=dict)

    # Task context
    task_context: str | None = None
    tab_metadata: dict[str, Any] = field(default_factory=dict)

    # History
    navigation_history: list[str] = field(default_factory=list)
    
    # Playwright page reference (set by executor)
    _playwright_page: Any = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "url": self.url,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "accessibility_tree": self.accessibility_tree,
            "visible_text": self.visible_text,
            "screenshot_path": self.screenshot_path,
            "interactive_elements": [e.to_dict() for e in self.interactive_elements],
            "forms": [f.to_dict() for f in self.forms],
            "page_metadata": self.page_metadata,
            "task_context": self.task_context,
            "tab_metadata": self.tab_metadata,
            "navigation_history": self.navigation_history,
        }

    def get_elements_by_type(self, element_type: ElementType) -> list[BrowserElement]:
        """Get all elements of a specific type."""
        return [e for e in self.interactive_elements if e.element_type == element_type]

    def get_clickable_elements(self) -> list[BrowserElement]:
        """Get all clickable elements (buttons, links)."""
        return [e for e in self.interactive_elements
                if e.element_type in (ElementType.BUTTON, ElementType.LINK)
                and e.is_visible and e.is_enabled]

    def get_editable_elements(self) -> list[BrowserElement]:
        """Get all editable elements (inputs, textareas)."""
        return [e for e in self.interactive_elements
                if e.is_editable and e.is_visible and e.is_enabled]

    def find_element_by_label(self, label: str) -> BrowserElement | None:
        """Find element by accessible label (fuzzy match)."""
        label_lower = label.lower()
        for element in self.interactive_elements:
            if element.label and label_lower in element.label.lower():
                return element
            if element.text and label_lower in element.text.lower():
                return element
            if element.placeholder and label_lower in element.placeholder.lower():
                return element
        return None

    def find_element_by_text(self, text: str) -> BrowserElement | None:
        """Find element by visible text."""
        text_lower = text.lower()
        for element in self.interactive_elements:
            if element.text and text_lower in element.text.lower():
                return element
        return None


@dataclass
class BrowserSession:
    """Manages a browser session with multiple tabs."""
    session_id: str
    tabs: dict[str, BrowserTab] = field(default_factory=dict)
    active_tab_id: str | None = None
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # Persistent state
    cookies: dict[str, Any] = field(default_factory=dict)
    local_storage: dict[str, Any] = field(default_factory=dict)
    session_storage: dict[str, Any] = field(default_factory=dict)

    # Task context
    current_task: str | None = None
    task_history: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.tabs:
            self.create_tab("about:blank", "New Tab")

    def create_tab(self, url: str = "about:blank", title: str = "New Tab") -> BrowserTab:
        """Create a new tab."""
        tab_id = str(uuid.uuid4())[:8]
        tab = BrowserTab(tab_id=tab_id, url=url, title=title)
        tab.navigation_history.append(url)
        self.tabs[tab_id] = tab
        self.active_tab_id = tab_id
        self.last_activity = time.time()
        
        # Emit monitoring event
        try:
            from app.monitoring.emitter import emit_browser_tab_opened
            emit_browser_tab_opened(self.session_id, tab_id, url)
        except Exception:
            pass
        
        return tab

    def close_tab(self, tab_id: str) -> bool:
        """Close a tab."""
        if tab_id in self.tabs:
            self.tabs[tab_id].status = TabStatus.CLOSED
            del self.tabs[tab_id]
            if self.active_tab_id == tab_id:
                # Switch to another tab if available
                remaining = list(self.tabs.keys())
                self.active_tab_id = remaining[0] if remaining else None
            self.last_activity = time.time()
            
            # Emit monitoring event
            try:
                from app.monitoring.emitter import emit_browser_tab_closed
                emit_browser_tab_closed(self.session_id, tab_id)
            except Exception:
                pass
            
            return True
        return False

    def switch_tab(self, tab_id: str) -> BrowserTab | None:
        """Switch to a different tab."""
        if tab_id in self.tabs:
            self.active_tab_id = tab_id
            self.tabs[tab_id].last_accessed = time.time()
            self.last_activity = time.time()
            return self.tabs[tab_id]
        return None

    def get_active_tab(self) -> BrowserTab | None:
        """Get the currently active tab."""
        if self.active_tab_id and self.active_tab_id in self.tabs:
            return self.tabs[self.active_tab_id]
        # Fallback to first available tab
        if self.tabs:
            first_tab = next(iter(self.tabs.values()))
            self.active_tab_id = first_tab.tab_id
            return first_tab
        return None

    def get_tab(self, tab_id: str) -> BrowserTab | None:
        """Get a tab by ID."""
        return self.tabs.get(tab_id)

    def list_tabs(self) -> list[dict[str, Any]]:
        """List all tabs with summary info."""
        return [
            {
                "tab_id": tab.tab_id,
                "url": tab.url,
                "title": tab.title,
                "status": tab.status.value,
                "is_active": tab.tab_id == self.active_tab_id,
                "element_count": len(tab.interactive_elements),
            }
            for tab in self.tabs.values()
            if tab.status != TabStatus.CLOSED
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "active_tab_id": self.active_tab_id,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "current_task": self.current_task,
            "tabs": {tid: tab.to_dict() for tid, tab in self.tabs.items()},
            "cookies": self.cookies,
            "task_history": self.task_history,
        }


# Global session registry
_browser_sessions: dict[str, BrowserSession] = {}


def get_browser_session(session_id: str) -> BrowserSession | None:
    """Get a browser session by ID."""
    return _browser_sessions.get(session_id)


def create_browser_session(session_id: str | None = None) -> BrowserSession:
    """Create a new browser session."""
    if session_id is None:
        session_id = str(uuid.uuid4())[:12]
    session = BrowserSession(session_id=session_id)
    _browser_sessions[session_id] = session
    return session


def delete_browser_session(session_id: str) -> bool:
    """Delete a browser session."""
    if session_id in _browser_sessions:
        del _browser_sessions[session_id]
        return True
    return False


def list_browser_sessions() -> list[dict[str, Any]]:
    """List all browser sessions."""
    return [
        {
            "session_id": s.session_id,
            "active_tab_id": s.active_tab_id,
            "tab_count": len(s.tabs),
            "current_task": s.current_task,
            "created_at": s.created_at,
            "last_activity": s.last_activity,
        }
        for s in _browser_sessions.values()
    ]
