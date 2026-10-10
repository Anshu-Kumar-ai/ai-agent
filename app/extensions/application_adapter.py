"""
Application Adapter Contracts - Stage 32 Phase 5
Defines interfaces and metadata for application adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class AdapterState(Enum):
    """Lifecycle states for application adapters."""
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    AVAILABLE = "available"
    EXECUTING = "executing"
    CLEANING_UP = "cleaning_up"
    CLEANED_UP = "cleaned_up"
    ERROR = "error"


@dataclass
class AdapterMetadata:
    """Metadata for an application adapter."""
    adapter_id: str
    application_id: str
    display_name: str
    version: str = "1.0.0"
    supported_capabilities: List[str] = field(default_factory=list)
    availability_requirements: List[str] = field(default_factory=list)
    environment_requirements: List[str] = field(default_factory=list)
    lifecycle_requirements: List[str] = field(default_factory=list)
    security_metadata: Dict[str, Any] = field(default_factory=dict)
    # Side effects and risk
    side_effect_level: str = "write"  # none, read, write, execute, network, destructive
    risk_level: str = "medium"  # low, medium, high
    requires_verification: bool = True
    # Lifecycle
    initialization_timeout: float = 30.0  # seconds
    execution_timeout: float = 60.0  # seconds
    cleanup_timeout: float = 10.0  # seconds


class ApplicationAdapterInterface(ABC):
    """
    Abstract interface for application adapters.
    
    Application adapters expose application capabilities through a standardized
    interface that integrates with the Stage 32 extension system.
    """
    
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter instance."""
        pass
    
    @property
    @abstractmethod
    def application_id(self) -> str:
        """Identifier for the application this adapter targets (e.g., 'chrome', 'notepad')."""
        pass
    
    @property
    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """Full metadata for this adapter."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the adapter is available (application running, dependencies met)."""
        pass
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the adapter (launch application, connect to existing instance).
        
        Returns:
            True if initialization succeeded, False otherwise.
        """
        pass
    
    @abstractmethod
    def execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute an action on the target application.
        
        Args:
            action: Action name (must match a supported capability)
            arguments: Action arguments
            
        Returns:
            Action result
        """
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources (close connections, stop processes if owned)."""
        pass
    
    @abstractmethod
    def get_state(self) -> AdapterState:
        """Get current lifecycle state."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """Get list of capabilities this adapter provides."""
        pass


# Base class for common adapter functionality
class BaseApplicationAdapter(ApplicationAdapterInterface):
    """Base class providing common adapter functionality."""
    
    def __init__(self, adapter_id: str, application_id: str, display_name: str):
        self._adapter_id = adapter_id
        self._application_id = application_id
        self._display_name = display_name
        self._state = AdapterState.UNREGISTERED
        self._initialized = False
        self._available = False
        self._last_error: Optional[str] = None
        self._instance_id: Optional[str] = None  # For instance isolation
    
    @property
    def adapter_id(self) -> str:
        return self._adapter_id
    
    @property
    def application_id(self) -> str:
        return self._application_id
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self._application_id,
            display_name=self._display_name,
            supported_capabilities=self.get_capabilities(),
        )
    
    def is_available(self) -> bool:
        return self._available and self._initialized
    
    def get_state(self) -> AdapterState:
        return self._state
    
    def set_state(self, state: AdapterState) -> None:
        self._state = state
    
    def get_capabilities(self) -> List[str]:
        """Override in subclass to return supported capabilities."""
        return []
    
    def get_last_error(self) -> Optional[str]:
        return self._last_error
    
    def _set_error(self, error: str) -> None:
        self._last_error = error
        self.set_state(AdapterState.ERROR)
    
    def _mark_initialized(self) -> None:
        self._initialized = True
        self._available = True
        self.set_state(AdapterState.AVAILABLE)
    
    def _mark_unavailable(self) -> None:
        self._available = False
        self.set_state(AdapterState.INITIALIZED)
    
    def _mark_cleaned_up(self) -> None:
        self._initialized = False
        self._available = False
        self.set_state(AdapterState.CLEANED_UP)
    
    def initialize(self) -> bool:
        """Default initialization - override in subclass."""
        try:
            self.set_state(AdapterState.INITIALIZING)
            success = self._do_initialize()
            if success:
                self._mark_initialized()
            else:
                self.set_state(AdapterState.ERROR)
            return success
        except Exception as e:
            self._set_error(f"Initialization failed: {e}")
            return False
    
    def _do_initialize(self) -> bool:
        """Override in subclass for actual initialization logic."""
        return True
    
    def execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute action with state management."""
        if not self.is_available():
            raise RuntimeError(f"Adapter {self._adapter_id} not available")
        
        if action not in self.get_capabilities():
            return {"success": False, "error": f"Action '{action}' not supported by {self._adapter_id}"}
        
        self.set_state(AdapterState.EXECUTING)
        try:
            result = self._do_execute(action, arguments)
            self.set_state(AdapterState.AVAILABLE)
            return result
        except Exception as e:
            self.set_state(AdapterState.ERROR)
            raise
    
    @abstractmethod
    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Override in subclass for actual execution logic."""
        pass
    
    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            self.set_state(AdapterState.CLEANING_UP)
            self._do_cleanup()
            self._mark_cleaned_up()
        except Exception as e:
            self._set_error(f"Cleanup failed: {e}")
    
    @abstractmethod
    def _do_cleanup(self) -> None:
        """Override in subclass for actual cleanup logic."""
        pass