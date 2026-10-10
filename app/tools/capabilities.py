"""Tool Capability Metadata - Stage 30: Capability-Based Intelligence.

Structured capability descriptions for tools enabling semantic selection.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityCategory(Enum):
    """High-level capability categories."""
    COMPUTATION = "computation"
    FILESYSTEM = "filesystem"
    BROWSER = "browser"
    DESKTOP = "desktop"
    NETWORK = "network"
    KNOWLEDGE = "knowledge"
    TERMINAL = "terminal"
    CODE_EXECUTION = "code_execution"
    COMMUNICATION = "communication"
    SYSTEM = "system"


class SideEffectLevel(Enum):
    """Level of external side effects."""
    NONE = "none"           # Pure computation, no external effects
    READ = "read"           # Reads external state
    WRITE = "write"         # Modifies external state
    EXECUTE = "execute"     # Executes arbitrary code/commands
    NETWORK = "network"     # Makes network requests
    DESTRUCTIVE = "destructive"  # Irreversible changes (delete, send, etc.)


class ToolCapability:
    """Describes what a tool can do and how to use it."""
    
    def __init__(
        self,
        name: str,
        description: str,
        categories: list[CapabilityCategory] | None = None,
        operations: list[str] | None = None,
        required_parameters: list[str] | None = None,
        optional_parameters: list[str] | None = None,
        risk_level: str = "medium",
        side_effect_level: SideEffectLevel = SideEffectLevel.NONE,
        supports_verification: bool = True,
        supports_retry: bool = True,
        idempotent: bool = False,
        environment_requirements: list[str] | None = None,
        examples: list[str] | None = None,
        constraints: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.categories = categories or []
        self.operations = operations or []
        self.required_parameters = required_parameters or []
        self.optional_parameters = optional_parameters or []
        self.risk_level = risk_level
        self.side_effect_level = side_effect_level
        self.supports_verification = supports_verification
        self.supports_retry = supports_retry
        self.idempotent = idempotent
        self.environment_requirements = environment_requirements or []
        self.examples = examples or []
        self.constraints = constraints or []
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "categories": [c.value for c in self.categories],
            "operations": self.operations,
            "required_parameters": self.required_parameters,
            "optional_parameters": self.optional_parameters,
            "risk_level": self.risk_level,
            "side_effect_level": self.side_effect_level.value,
            "supports_verification": self.supports_verification,
            "supports_retry": self.supports_retry,
            "idempotent": self.idempotent,
            "environment_requirements": self.environment_requirements,
            "examples": self.examples,
            "constraints": self.constraints,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolCapability":
        return cls(
            name=data["name"],
            description=data["description"],
            categories=[CapabilityCategory(c) for c in data.get("categories", [])],
            operations=data.get("operations", []),
            required_parameters=data.get("required_parameters", []),
            optional_parameters=data.get("optional_parameters", []),
            risk_level=data.get("risk_level", "medium"),
            side_effect_level=SideEffectLevel(data.get("side_effect_level", "none")),
            supports_verification=data.get("supports_verification", True),
            supports_retry=data.get("supports_retry", True),
            idempotent=data.get("idempotent", False),
            environment_requirements=data.get("environment_requirements", []),
            examples=data.get("examples", []),
            constraints=data.get("constraints", []),
        )
    
    def matches_category(self, category: CapabilityCategory) -> bool:
        return category in self.categories
    
    def matches_operation(self, operation: str) -> bool:
        op_lower = operation.lower()
        return any(op_lower in op.lower() for op in self.operations)
    
    def has_required_params(self, params: dict[str, Any]) -> bool:
        return all(p in params for p in self.required_parameters)


# Built-in capability definitions for existing tools
BUILTIN_CAPABILITIES = {
    "calculator": ToolCapability(
        name="calculator",
        description="Evaluate arithmetic expressions including averages, percentages, and unit conversions",
        categories=[CapabilityCategory.COMPUTATION],
        operations=["arithmetic", "average", "percentage", "unit_conversion", "mean", "sum", "divide", "multiply"],
        required_parameters=["expression"],
        optional_parameters=[],
        risk_level="low",
        side_effect_level=SideEffectLevel.NONE,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=[],
        examples=[
            "Calculate 25 * 4 + 10",
            "Find the average of 10, 20, 30",
            "What is 15% of 200?",
            "Convert 5 GB to MB",
        ],
        constraints=["Expression must be valid arithmetic"],
    ),
    "time_tool": ToolCapability(
        name="time_tool",
        description="Get current date and time in ISO format",
        categories=[CapabilityCategory.SYSTEM],
        operations=["current_time", "current_date", "timestamp"],
        required_parameters=[],
        optional_parameters=[],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=[],
        examples=["What time is it?", "Get current date"],
        constraints=[],
    ),
    "fs.read": ToolCapability(
        name="fs.read",
        description="Read file contents from the workspace",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["read", "cat", "view", "display"],
        required_parameters=["path"],
        optional_parameters=[],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["workspace"],
        examples=["Read file.txt", "Show contents of config.json"],
        constraints=["Path must be within workspace"],
    ),
    "fs.write": ToolCapability(
        name="fs.write",
        description="Write content to a file in the workspace",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["write", "create", "save", "put"],
        required_parameters=["path", "content"],
        optional_parameters=[],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,  # Idempotent but retry without check could duplicate
        idempotent=True,  # Overwrite is idempotent
        environment_requirements=["workspace"],
        examples=["Save result to output.txt", "Create config.json with settings"],
        constraints=["Path must be within workspace", "Overwrites existing file"],
    ),
    "fs.list": ToolCapability(
        name="fs.list",
        description="List directory contents",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["list", "ls", "dir", "show_files"],
        required_parameters=["path"],
        optional_parameters=["recursive"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["workspace"],
        examples=["List files in workspace", "Show directory contents"],
        constraints=["Path must be within workspace"],
    ),
    "fs.move": ToolCapability(
        name="fs.move",
        description="Move or rename files",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["move", "rename", "mv"],
        required_parameters=["src", "dst"],
        optional_parameters=[],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["workspace"],
        examples=["Move file.txt to archive/", "Rename old.txt to new.txt"],
        constraints=["Both paths must be within workspace"],
    ),
    "terminal.run": ToolCapability(
        name="terminal.run",
        description="Execute shell commands",
        categories=[CapabilityCategory.TERMINAL, CapabilityCategory.SYSTEM],
        operations=["execute", "run", "shell", "command"],
        required_parameters=["cmd"],
        optional_parameters=["timeout"],
        risk_level="high",
        side_effect_level=SideEffectLevel.EXECUTE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["shell"],
        examples=["Run ls -la", "Execute python script.py"],
        constraints=["Command runs in sandboxed environment", "Timeout enforced"],
    ),
    "http.fetch": ToolCapability(
        name="http.fetch",
        description="Fetch content from HTTP/HTTPS URLs",
        categories=[CapabilityCategory.NETWORK],
        operations=["fetch", "download", "get", "retrieve"],
        required_parameters=["url"],
        optional_parameters=["wait_until", "timeout"],
        risk_level="medium",
        side_effect_level=SideEffectLevel.NETWORK,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["network"],
        examples=["Download https://example.com", "Fetch API data"],
        constraints=["Only HTTP/HTTPS URLs", "Timeout enforced"],
    ),
    "web.search": ToolCapability(
        name="web.search",
        description="Search the web for information",
        categories=[CapabilityCategory.NETWORK, CapabilityCategory.KNOWLEDGE],
        operations=["search", "find", "query", "lookup"],
        required_parameters=["query"],
        optional_parameters=[],
        risk_level="medium",
        side_effect_level=SideEffectLevel.NETWORK,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["network"],
        examples=["Search for Python tutorials", "Find latest AI news"],
        constraints=["Free search API may have rate limits"],
    ),
    "python.exec": ToolCapability(
        name="python.exec",
        description="Execute Python code in sandboxed environment",
        categories=[CapabilityCategory.CODE_EXECUTION, CapabilityCategory.COMPUTATION],
        operations=["execute", "run", "compute", "script"],
        required_parameters=["code"],
        optional_parameters=["timeout"],
        risk_level="high",
        side_effect_level=SideEffectLevel.EXECUTE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["python"],
        examples=["Calculate fibonacci(10)", "Process data with pandas"],
        constraints=["No network access", "Timeout enforced", "No file system outside workspace"],
    ),
    "browser_agent.execute": ToolCapability(
        name="browser_agent.execute",
        description="Execute complex browser automation tasks",
        categories=[CapabilityCategory.BROWSER],
        operations=["navigate", "click", "type", "extract", "scroll", "screenshot", "form_fill"],
        required_parameters=["goal"],
        optional_parameters=["context", "session_id", "headless"],
        risk_level="high",
        side_effect_level=SideEffectLevel.NETWORK,
        supports_verification=True,
        supports_retry=True,
        idempotent=False,
        environment_requirements=["playwright", "chromium"],
        examples=["Find cheapest laptop under $1000", "Login and extract dashboard data"],
        constraints=["Requires browser installation", "Headless by default"],
    ),
    "browser_session.manage": ToolCapability(
        name="browser_session.manage",
        description="Manage browser sessions and tabs",
        categories=[CapabilityCategory.BROWSER],
        operations=["create_session", "list_sessions", "create_tab", "switch_tab", "close_tab", "list_tabs"],
        required_parameters=["action"],
        optional_parameters=["session_id", "tab_id", "url"],
        risk_level="medium",
        side_effect_level=SideEffectLevel.NETWORK,
        supports_verification=True,
        supports_retry=True,
        idempotent=False,
        environment_requirements=["playwright", "chromium"],
        examples=["Create new browser tab", "Switch to tab 2"],
        constraints=[],
    ),
    "browser.observe": ToolCapability(
        name="browser.observe",
        description="Observe current browser state (URL, title, elements, forms, text)",
        categories=[CapabilityCategory.BROWSER],
        operations=["observe", "inspect", "get_state", "get_elements"],
        required_parameters=["session_id"],
        optional_parameters=["tab_id", "include_screenshot", "include_elements", "include_text", "element_types"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["playwright", "chromium"],
        examples=["What's on the current page?", "Get all buttons on page"],
        constraints=[],
    ),
    "browser.action": ToolCapability(
        name="browser.action",
        description="Execute individual browser actions",
        categories=[CapabilityCategory.BROWSER],
        operations=["navigate", "click", "type", "scroll", "hover", "select", "wait", "key_press", "screenshot", "go_back", "go_forward", "refresh", "new_tab", "switch_tab", "close_tab", "fill_form", "submit_form", "file_upload"],
        required_parameters=["action_type", "session_id"],
        optional_parameters=["tab_id", "selector", "element_id", "url", "text", "key", "direction", "amount", "timeout"],
        risk_level="high",
        side_effect_level=SideEffectLevel.NETWORK,
        supports_verification=True,
        supports_retry=True,
        idempotent=False,
        environment_requirements=["playwright", "chromium"],
        examples=["Click button.submit", "Type in search box", "Navigate to URL"],
        constraints=["Requires active browser session"],
    ),
    "desktop.list_windows": ToolCapability(
        name="desktop.list_windows",
        description="List top-level windows with titles and process info",
        categories=[CapabilityCategory.DESKTOP, CapabilityCategory.SYSTEM],
        operations=["list", "enumerate", "show"],
        required_parameters=[],
        optional_parameters=["visible_only", "include_process_info"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["pywinauto", "windows"],
        examples=["Show all open windows", "List visible applications"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "desktop.get_window_info": ToolCapability(
        name="desktop.get_window_info",
        description="Get detailed information about a window including its controls",
        categories=[CapabilityCategory.DESKTOP, CapabilityCategory.SYSTEM],
        operations=["get_window_info", "inspect_window", "window_details", "window_hierarchy"],
        required_parameters=[],  # At least one of: title, title_contains, process_id, executable, handle
        optional_parameters=["title", "title_contains", "process_id", "executable", "handle", "include_children", "max_depth", "timeout"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["pywinauto", "windows"],
        examples=["Get Notepad window info", "Inspect window hierarchy"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "desktop.focus_window": ToolCapability(
        name="desktop.focus_window",
        description="Focus/activate a window by title, process, or executable",
        categories=[CapabilityCategory.DESKTOP, CapabilityCategory.SYSTEM],
        operations=["focus", "activate", "bring_to_front"],
        required_parameters=[],  # At least one of: title, title_contains, process_id, executable
        optional_parameters=["title", "title_contains", "process_id", "executable", "timeout"],
        risk_level="low",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["pywinauto", "windows"],
        examples=["Focus Notepad", "Activate Chrome window"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "desktop.click": ToolCapability(
        name="desktop.click",
        description="Click a control within a window",
        categories=[CapabilityCategory.DESKTOP],
        operations=["click", "press"],
        required_parameters=[],  # Window + control identification
        optional_parameters=["title", "title_contains", "process_id", "executable", "automation_id", "control_title", "control_type", "found_index", "click_type", "timeout"],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["pywinauto", "windows"],
        examples=["Click OK button", "Click save dialog"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "desktop.type": ToolCapability(
        name="desktop.type",
        description="Type text into a control",
        categories=[CapabilityCategory.DESKTOP],
        operations=["type", "enter_text", "fill"],
        required_parameters=["text"],
        optional_parameters=["title", "title_contains", "process_id", "executable", "automation_id", "control_title", "control_type", "found_index", "clear_first", "timeout"],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["pywinauto", "windows"],
        examples=["Type in notepad", "Fill login form"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "rag.add": ToolCapability(
        name="rag.add",
        description="Add documents to knowledge base for retrieval",
        categories=[CapabilityCategory.KNOWLEDGE],
        operations=["add", "store", "index", "remember"],
        required_parameters=["text"],
        optional_parameters=["collection"],
        risk_level="low",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=True,
        idempotent=False,
        environment_requirements=["faiss", "sentence_transformers"],
        examples=["Store documentation in knowledge base", "Add research notes"],
        constraints=["Uses local vector store (FAISS)"],
    ),
    "desktop.key_press": ToolCapability(
        name="desktop.key_press",
        description="Send key presses to a window",
        categories=[CapabilityCategory.DESKTOP],
        operations=["key_press", "send_keys", "press_key"],
        required_parameters=["keys"],
        optional_parameters=["title", "title_contains", "process_id", "executable", "timeout"],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,
        idempotent=False,
        environment_requirements=["pywinauto", "windows"],
        examples=["Press Enter", "Send Ctrl+A"],
        constraints=["Windows only, requires pywinauto"],
    ),
    "desktop.screenshot": ToolCapability(
        name="desktop.screenshot",
        description="Take a screenshot of a window or region",
        categories=[CapabilityCategory.DESKTOP, CapabilityCategory.SYSTEM],
        operations=["screenshot", "capture", "screen_capture"],
        required_parameters=[],
        optional_parameters=["title", "title_contains", "process_id", "executable", "left", "top", "width", "height", "save_path", "timeout"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["pywinauto", "windows", "pillow"],
        examples=["Screenshot Notepad", "Capture screen region"],
        constraints=["Windows only, requires pywinauto and pillow"],
    ),
    "rag.add": ToolCapability(
        name="rag.add",
        description="Add documents to knowledge base for retrieval",
        categories=[CapabilityCategory.KNOWLEDGE],
        operations=["add", "store", "index", "remember"],
        required_parameters=["text"],
        optional_parameters=["collection"],
        risk_level="low",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=True,
        idempotent=False,
        environment_requirements=["faiss", "sentence_transformers"],
        examples=["Store documentation in knowledge base", "Add research notes"],
        constraints=["Uses local vector store (FAISS)"],
    ),
    "rag.query": ToolCapability(
        name="rag.query",
        description="Query knowledge base for relevant information",
        categories=[CapabilityCategory.KNOWLEDGE],
        operations=["query", "search", "ask", "find", "retrieve"],
        required_parameters=["query"],
        optional_parameters=["collection"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["faiss", "sentence_transformers"],
        examples=["Ask about stored documentation", "Search knowledge base"],
        constraints=["Uses local vector store (FAISS)"],
    ),
    "rag.stats": ToolCapability(
        name="rag.stats",
        description="Get statistics about knowledge base",
        categories=[CapabilityCategory.KNOWLEDGE],
        operations=["stats", "status", "size", "count"],
        required_parameters=[],
        optional_parameters=["collection"],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["faiss", "sentence_transformers"],
        examples=["How many documents in knowledge base?", "Show index size"],
        constraints=["Uses local vector store (FAISS)"],
    ),
    "filesystem_write": ToolCapability(
        name="filesystem_write",
        description="Write content to a file in the workspace",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["write", "create", "save", "put", "store"],
        required_parameters=["path", "content"],
        optional_parameters=[],
        risk_level="medium",
        side_effect_level=SideEffectLevel.WRITE,
        supports_verification=True,
        supports_retry=False,
        idempotent=True,
        environment_requirements=["workspace"],
        examples=["Save result to output.txt", "Create config.json with settings", "Store the result in result.txt"],
        constraints=["Path must be within workspace", "Overwrites existing file"],
    ),
    "filesystem_read": ToolCapability(
        name="filesystem_read",
        description="Read file contents from the workspace",
        categories=[CapabilityCategory.FILESYSTEM],
        operations=["read", "cat", "view", "display"],
        required_parameters=["path"],
        optional_parameters=[],
        risk_level="low",
        side_effect_level=SideEffectLevel.READ,
        supports_verification=True,
        supports_retry=True,
        idempotent=True,
        environment_requirements=["workspace"],
        examples=["Read file.txt", "Show contents of config.json"],
        constraints=["Path must be within workspace"],
    ),
}


def get_capability(name: str) -> ToolCapability | None:
    """Get a built-in capability by name."""
    return BUILTIN_CAPABILITIES.get(name)


def get_capabilities_by_category(category: CapabilityCategory) -> list[ToolCapability]:
    """Get all capabilities matching a category."""
    return [c for c in BUILTIN_CAPABILITIES.values() if c.matches_category(category)]


def get_capabilities_by_operation(operation: str) -> list[ToolCapability]:
    """Get all capabilities matching an operation."""
    return [c for c in BUILTIN_CAPABILITIES.values() if c.matches_operation(operation)]


def get_all_capabilities() -> list[ToolCapability]:
    """Get all built-in capabilities."""
    return list(BUILTIN_CAPABILITIES.values())