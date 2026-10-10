"""
Desktop Compatibility Adapter - Stage 32 Phase 5
Wraps existing Stage 31 pywinauto desktop tools into Application Adapter interface.
"""

from typing import Any, Dict, List, Optional
import uuid

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    BaseApplicationAdapter,
    AdapterMetadata,
    AdapterState,
)
from app.tools.desktop_tools import (
    DesktopListWindowsTool,
    DesktopFocusWindowTool,
    DesktopGetWindowInfoTool,
    DesktopClickTool,
    DesktopTypeTool,
    DesktopKeyPressTool,
    DesktopScreenshotTool,
    create_desktop_tools,
    PYWINAUTO_AVAILABLE,
    DesktopActionError,
)


class DesktopAdapter(BaseApplicationAdapter):
    """
    Compatibility adapter for the existing Stage 31 desktop automation system.
    
    Wraps the desktop tools (DesktopListWindowsTool, DesktopClickTool, etc.)
    into the ApplicationAdapterInterface.
    """
    
    def __init__(
        self,
        adapter_id: str = "desktop_adapter",
        instance_id: Optional[str] = None
    ):
        display_name = "Desktop Adapter (pywinauto)"
        super().__init__(adapter_id, "windows", display_name)
        
        self._instance_id = instance_id or str(uuid.uuid4())[:8]
        self._tools: Dict[str, Any] = {}
        self._pywinauto_available = PYWINAUTO_AVAILABLE
    
    def get_capabilities(self) -> List[str]:
        return [
            "desktop.list_windows",
            "desktop.focus_window",
            "desktop.get_window_info",
            "desktop.click",
            "desktop.type",
            "desktop.key_press",
            "desktop.screenshot",
        ]
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self.application_id,
            display_name=self._display_name,
            version="1.0.0",
            supported_capabilities=self.get_capabilities(),
            availability_requirements=["pywinauto", "windows"],
            environment_requirements=["pywinauto", "windows"],
            lifecycle_requirements=["windows_desktop"],
            security_metadata={
                "side_effect_level": "write",
                "risk_level": "medium",
                "requires_verification": True,
                "permission_required": "desktop.click",
            },
            side_effect_level="write",
            risk_level="medium",
            requires_verification=True,
            initialization_timeout=10.0,
            execution_timeout=30.0,
            cleanup_timeout=5.0,
        )
    
    def _do_initialize(self) -> bool:
        """Initialize the desktop tools."""
        try:
            if not self._pywinauto_available:
                self._set_error("pywinauto is not installed. Install with: pip install pywinauto")
                return False
            
            # Create the desktop tools
            tools = create_desktop_tools()
            self._tools = {tool.name: tool for tool in tools}
            
            return True
        except Exception as e:
            self._set_error(f"Failed to initialize desktop adapter: {e}")
            return False
    
    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute a desktop action through the appropriate tool."""
        if action not in self._tools:
            raise ValueError(f"Action '{action}' not found in desktop tools")
        
        tool = self._tools[action]
        
        # Validate arguments if the tool has validate_arguments
        if hasattr(tool, 'validate_arguments'):
            try:
                tool.validate_arguments(arguments)
            except ValueError as e:
                return {"success": False, "error": f"Validation failed: {e}"}
        
        # Execute the tool
        try:
            result = tool.execute(**arguments)
            return result
        except DesktopActionError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    
    def _do_cleanup(self) -> None:
        """Clean up desktop resources."""
        # Desktop tools don't typically hold persistent connections
        # but we clear the tool references
        self._tools.clear()


class DesktopAdapterFactory:
    """Factory for creating isolated desktop adapter instances."""
    
    _instances: Dict[str, DesktopAdapter] = {}
    
    @classmethod
    def create_adapter(cls, adapter_id: str = None) -> DesktopAdapter:
        """Create a new isolated desktop adapter instance."""
        if adapter_id is None:
            adapter_id = f"desktop_adapter_{str(uuid.uuid4())[:8]}"
        
        if adapter_id in cls._instances:
            # Return existing instance
            return cls._instances[adapter_id]
        
        adapter = DesktopAdapter(adapter_id=adapter_id)
        cls._instances[adapter_id] = adapter
        return adapter
    
    @classmethod
    def get_adapter(cls, adapter_id: str) -> Optional[DesktopAdapter]:
        """Get an existing adapter instance."""
        return cls._instances.get(adapter_id)
    
    @classmethod
    def remove_adapter(cls, adapter_id: str) -> bool:
        """Remove and cleanup an adapter instance."""
        adapter = cls._instances.pop(adapter_id, None)
        if adapter:
            adapter.cleanup()
            return True
        return False
    
    @classmethod
    def list_instances(cls) -> List[str]:
        """List all adapter instance IDs."""
        return list(cls._instances.keys())
    
    @classmethod
    def cleanup_all(cls) -> None:
        """Cleanup all adapter instances."""
        for adapter in cls._instances.values():
            try:
                adapter.cleanup()
            except Exception:
                pass
        cls._instances.clear()


# Convenience function for creating and registering a desktop adapter
def create_desktop_adapter(adapter_id: str = None) -> DesktopAdapter:
    """Create and initialize a desktop adapter."""
    adapter = DesktopAdapterFactory.create_adapter(adapter_id)
    if adapter.initialize():
        return adapter
    else:
        DesktopAdapterFactory.remove_adapter(adapter.adapter_id)
        raise RuntimeError(f"Failed to initialize desktop adapter: {adapter.get_last_error()}")