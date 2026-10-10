"""
Browser Compatibility Adapter - Stage 32 Phase 5
Wraps existing Stage 31 browser tools into Application Adapter interface.
"""

import asyncio
from typing import Any, Dict, List, Optional
import uuid

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    BaseApplicationAdapter,
    AdapterMetadata,
    AdapterState,
)
from app.tools.browser_tools import (
    BrowserNavigateTool,
    BrowserClickTool,
    BrowserTypeTool,
    BrowserScreenshotTool,
    BrowserContentTool,
    BrowserEvaluateTool,
    BrowserCloseTool,
    create_browser_tools,
)


class BrowserAdapter(BaseApplicationAdapter):
    """
    Compatibility adapter for the existing Stage 31 browser system.
    
    Wraps the browser tools (BrowserNavigateTool, BrowserClickTool, etc.)
    into the ApplicationAdapterInterface.
    """
    
    def __init__(
        self,
        adapter_id: str = "browser_adapter",
        headless: bool = True,
        instance_id: Optional[str] = None
    ):
        display_name = "Browser Adapter (Playwright)"
        super().__init__(adapter_id, "chromium", display_name)
        
        self._headless = headless
        self._instance_id = instance_id or str(uuid.uuid4())[:8]
        self._tools: Dict[str, Any] = {}
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialized = False
        self._available = False
    
    def get_capabilities(self) -> List[str]:
        return [
            "browser.navigate",
            "browser.click",
            "browser.type",
            "browser.screenshot",
            "browser.content",
            "browser.evaluate",
            "browser.close",
        ]
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self.application_id,
            display_name=self._display_name,
            version="1.0.0",
            supported_capabilities=self.get_capabilities(),
            availability_requirements=["playwright", "chromium"],
            environment_requirements=["playwright", "chromium"],
            lifecycle_requirements=["browser_process"],
            security_metadata={
                "side_effect_level": "network",
                "risk_level": "high",
                "requires_verification": True,
                "permission_required": "browser.navigate",
            },
            side_effect_level="network",
            risk_level="high",
            requires_verification=True,
            initialization_timeout=30.0,
            execution_timeout=60.0,
            cleanup_timeout=10.0,
        )
    
    def _do_initialize(self) -> bool:
        """Initialize the browser tools and launch browser."""
        try:
            # Create the browser tools
            tools = create_browser_tools(headless=self._headless)
            self._tools = {tool.name: tool for tool in tools}
            
            # Verify playwright is available
            from playwright.async_api import async_playwright
            # Just check import works
            return True
        except Exception as e:
            self._set_error(f"Failed to initialize browser adapter: {e}")
            return False
    
    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute a browser action through the appropriate tool."""
        if action not in self._tools:
            raise ValueError(f"Action '{action}' not found in browser tools")
        
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
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}
    
    def _do_cleanup(self) -> None:
        """Clean up browser resources."""
        # Close all tools that have browser connections
        for tool in self._tools.values():
            if hasattr(tool, '_close_browser'):
                try:
                    if hasattr(tool, '_run_async'):
                        tool._run_async(tool._close_browser())
                    else:
                        asyncio.run(tool._close_browser())
                except Exception:
                    pass
        
        self._tools.clear()
        self._playwright = None
        self._browser = None
        self._page = None


class BrowserAdapterFactory:
    """Factory for creating isolated browser adapter instances."""
    
    _instances: Dict[str, BrowserAdapter] = {}
    
    @classmethod
    def create_adapter(cls, adapter_id: str = None, headless: bool = True) -> BrowserAdapter:
        """Create a new isolated browser adapter instance."""
        if adapter_id is None:
            adapter_id = f"browser_adapter_{str(uuid.uuid4())[:8]}"
        
        if adapter_id in cls._instances:
            # Return existing instance
            return cls._instances[adapter_id]
        
        adapter = BrowserAdapter(adapter_id=adapter_id, headless=headless)
        cls._instances[adapter_id] = adapter
        return adapter
    
    @classmethod
    def get_adapter(cls, adapter_id: str) -> Optional[BrowserAdapter]:
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


# Convenience function for creating and registering a browser adapter
def create_browser_adapter(adapter_id: str = None, headless: bool = True) -> BrowserAdapter:
    """Create and initialize a browser adapter."""
    adapter = BrowserAdapterFactory.create_adapter(adapter_id, headless)
    if adapter.initialize():
        return adapter
    else:
        BrowserAdapterFactory.remove_adapter(adapter.adapter_id)
        raise RuntimeError(f"Failed to initialize browser adapter: {adapter.get_last_error()}")