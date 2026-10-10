"""
Dynamic Tool System - Stage 32 Phase 3

Provides dynamic tool registration, capability mapping, discovery, validation,
and integration with the existing extension architecture and planner.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union, Callable
from enum import Enum
from datetime import datetime
import jsonschema
from jsonschema import validate, ValidationError

from app.extensions.contracts import (
    ToolInterface,
    ToolMetadata,
)
from app.extensions.registry import (
    ToolExtensionRegistry,
    CapabilityRegistry,
    ExtensionManager,
    ExtensionType,
    DuplicateRegistrationError,
    InvalidMetadataError,
    MissingInterfaceError,
    SecurityValidationError,
    LegacyToolAdapter,
)
from app.tools.capabilities import ToolCapability, CapabilityCategory, SideEffectLevel
from app.tools.registry import ToolRegistry
from app.tools.base import BaseTool


# ============================================================
# Enhanced Tool Metadata (extends ToolMetadata)
# ============================================================

class ToolAvailability(Enum):
    """Tool availability states."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    ENVIRONMENT_DEPENDENT = "environment_dependent"


class ToolLifecycleState(Enum):
    """Tool lifecycle states."""
    REGISTERED = "registered"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNREGISTERED = "unregistered"


@dataclass
class EnhancedToolMetadata(ToolMetadata):
    """Extended tool metadata for dynamic tool system."""
    # Availability
    availability: ToolAvailability = ToolAvailability.AVAILABLE
    availability_check: Optional[Callable[[], bool]] = None
    
    # Lifecycle
    lifecycle_state: ToolLifecycleState = ToolLifecycleState.REGISTERED
    
    # Versioning
    version: str = "1.0.0"
    
    # Discovery hints
    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    # Performance hints
    estimated_duration_ms: Optional[int] = None
    
    # Output contract
    output_contract: Optional[Dict[str, Any]] = None  # JSON Schema for output
    
    # Monitoring
    emits_monitoring: bool = True
    
    # Registration metadata
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    registered_by: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding callables)."""
        base = super().to_dict() if hasattr(super(), 'to_dict') else {}
        result = {
            "name": self.name,
            "description": self.description,
            "capability": self.capability,
            "arguments": self.arguments,
            "output_schema": self.output_schema,
            "risk_level": self.risk_level,
            "side_effects": self.side_effects,
            "permission_required": self.permission_required,
            "verification_required": self.verification_required,
            "availability_requirements": self.availability_requirements,
            "availability": self.availability.value,
            "lifecycle_state": self.lifecycle_state.value,
            "version": self.version,
            "tags": self.tags,
            "keywords": self.keywords,
            "estimated_duration_ms": self.estimated_duration_ms,
            "output_contract": self.output_contract,
            "emits_monitoring": self.emits_monitoring,
            "registered_at": self.registered_at,
            "registered_by": self.registered_by,
        }
        return result


# ============================================================
# Tool Result Contract
# ============================================================

class ToolResultStatus(Enum):
    """Standard tool result status."""
    SUCCESS = "success"
    FAILURE = "failure"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_ERROR = "validation_error"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


@dataclass
class ToolResult:
    """Standard tool execution result."""
    status: ToolResultStatus
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    verification_info: Optional[Dict[str, Any]] = None
    execution_duration_ms: Optional[int] = None
    tool_name: str = ""
    capability: str = ""
    
    def is_success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
            "verification_info": self.verification_info,
            "execution_duration_ms": self.execution_duration_ms,
            "tool_name": self.tool_name,
            "capability": self.capability,
        }
    
    @classmethod
    def success(cls, output: Any, tool_name: str = "", capability: str = "", 
                metadata: Dict = None, verification_info: Dict = None, 
                duration_ms: int = None) -> "ToolResult":
        return cls(
            status=ToolResultStatus.SUCCESS,
            output=output,
            metadata=metadata or {},
            verification_info=verification_info,
            execution_duration_ms=duration_ms,
            tool_name=tool_name,
            capability=capability,
        )
    
    @classmethod
    def failure(cls, error: str, tool_name: str = "", capability: str = "",
                metadata: Dict = None, duration_ms: int = None) -> "ToolResult":
        return cls(
            status=ToolResultStatus.FAILURE,
            error=error,
            metadata=metadata or {},
            execution_duration_ms=duration_ms,
            tool_name=tool_name,
            capability=capability,
        )
    
    @classmethod
    def permission_denied(cls, error: str, tool_name: str = "", capability: str = "") -> "ToolResult":
        return cls(
            status=ToolResultStatus.PERMISSION_DENIED,
            error=error,
            tool_name=tool_name,
            capability=capability,
        )
    
    @classmethod
    def validation_error(cls, error: str, tool_name: str = "", capability: str = "") -> "ToolResult":
        return cls(
            status=ToolResultStatus.VALIDATION_ERROR,
            error=error,
            tool_name=tool_name,
            capability=capability,
        )
    
    @classmethod
    def unavailable(cls, tool_name: str = "", capability: str = "") -> "ToolResult":
        return cls(
            status=ToolResultStatus.UNAVAILABLE,
            error="Tool is not available",
            tool_name=tool_name,
            capability=capability,
        )


# ============================================================
# Dynamic Tool Registry (extends ToolExtensionRegistry)
# ============================================================

class DynamicToolRegistry:
    """
    Dynamic tool registry that integrates with the extension system.
    Supports registration, discovery, capability mapping, and validation.
    """
    
    def __init__(self, extension_manager: Optional[ExtensionManager] = None):
        self._tool_registry = ToolExtensionRegistry()
        self._capability_registry = CapabilityRegistry()
        self._extension_manager = extension_manager
        
        # Tool -> capabilities mapping (many-to-many)
        self._tool_capabilities: Dict[str, Set[str]] = {}
        # Capability -> tools mapping
        self._capability_tools: Dict[str, Set[str]] = {}
        
        # Legacy tool adapter
        self._legacy_adapter = LegacyToolAdapter
        
        # Monitoring integration
        self._monitoring_enabled = True
    
    def register_tool(self, tool: ToolInterface) -> None:
        """Register a dynamic tool with full validation."""
        if not isinstance(tool, ToolInterface):
            raise MissingInterfaceError(
                f"Tool must implement ToolInterface, got {type(tool).__name__}"
            )
        
        metadata = tool.get_metadata()
        
        # Validate metadata
        self._validate_tool_metadata(metadata)
        self._validate_security_metadata(metadata)
        
        # Check for duplicate
        if self._tool_registry.contains(metadata.name):
            raise DuplicateRegistrationError(
                f"Tool already registered: {metadata.name}"
            )
        
        # Register tool in extension registry
        self._tool_registry.register(tool)
        
        # Update capability mappings
        capability = metadata.capability
        if capability not in self._capability_tools:
            self._capability_tools[capability] = set()
        self._capability_tools[capability].add(metadata.name)
        
        if metadata.name not in self._tool_capabilities:
            self._tool_capabilities[metadata.name] = set()
        self._tool_capabilities[metadata.name].add(capability)
        
        # Emit monitoring event
        if self._monitoring_enabled and getattr(metadata, 'emits_monitoring', True):
            self._emit_tool_registered(metadata)
    
    def register_legacy_tool(self, legacy_tool: BaseTool) -> None:
        """Register a legacy BaseTool via adapter."""
        adapter = LegacyToolAdapter(legacy_tool)
        self.register_tool(adapter)
    
    def register_legacy_registry(self, legacy_registry: ToolRegistry) -> None:
        """Migrate all tools from a legacy ToolRegistry."""
        wrapped = wrap_legacy_tool_registry(legacy_registry)
        # Copy tools from wrapped registry
        for tool_name, tool_reg in wrapped._tools.items():
            if not self._tool_registry.contains(tool_name):
                self._tool_registry._tools[tool_name] = tool_reg
                # Update capability mappings
                capability = tool_reg.metadata.capability
                if capability not in self._capability_tools:
                    self._capability_tools[capability] = set()
                self._capability_tools[capability].add(tool_name)
                
                if tool_name not in self._tool_capabilities:
                    self._tool_capabilities[tool_name] = set()
                self._tool_capabilities[tool_name].add(capability)
    
    def _validate_tool_metadata(self, metadata: ToolMetadata) -> None:
        """Validate tool metadata."""
        if not metadata.name:
            raise InvalidMetadataError("Tool must have a non-empty name")
        
        if not metadata.description:
            raise InvalidMetadataError("Tool must have a non-empty description")
        
        if not metadata.capability:
            raise InvalidMetadataError("Tool must declare a capability")
        
        if not metadata.arguments:
            raise InvalidMetadataError("Tool must have arguments schema")
        
        # Validate arguments schema is valid JSON Schema
        try:
            jsonschema.Draft7Validator.check_schema(metadata.arguments)
        except Exception as e:
            raise InvalidMetadataError(f"Invalid arguments schema: {e}")
        
        # Validate output schema if present
        if metadata.output_schema:
            try:
                jsonschema.Draft7Validator.check_schema(metadata.output_schema)
            except Exception as e:
                raise InvalidMetadataError(f"Invalid output schema: {e}")
        
        valid_risk_levels = {"low", "medium", "high"}
        if metadata.risk_level not in valid_risk_levels:
            raise InvalidMetadataError(
                f"Invalid risk_level: {metadata.risk_level}. Must be one of {valid_risk_levels}"
            )
        
        if not isinstance(metadata.verification_required, bool):
            raise InvalidMetadataError("verification_required must be boolean")
    
    def _validate_security_metadata(self, metadata: ToolMetadata) -> None:
        """Validate security-related metadata."""
        # Must declare side effects if risk_level is medium/high
        if metadata.risk_level in {"medium", "high"} and not metadata.side_effects:
            raise SecurityValidationError(
                f"Tool '{metadata.name}' with risk_level '{metadata.risk_level}' must declare side_effects"
            )
        
        # Permission required must be valid format if present
        if metadata.permission_required is not None:
            if not isinstance(metadata.permission_required, str):
                raise SecurityValidationError("permission_required must be string or None")
            if not metadata.permission_required:
                raise SecurityValidationError("permission_required cannot be empty string")
        
        # Availability requirements must be list of strings
        if metadata.availability_requirements:
            if not isinstance(metadata.availability_requirements, list):
                raise SecurityValidationError("availability_requirements must be list")
            for req in metadata.availability_requirements:
                if not isinstance(req, str):
                    raise SecurityValidationError("availability_requirements must be list of strings")
        
        # Validate capability exists in capability registry (if registered)
        if self._capability_registry.contains(metadata.capability):
            cap = self._capability_registry.get(metadata.capability)
            if cap:
                # Verify tool's capability matches declared capability
                if cap.name != metadata.capability:
                    raise SecurityValidationError(
                        f"Tool capability '{metadata.capability}' doesn't match registered capability"
                    )
    
    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister a tool."""
        if tool_name in self._tool_registry._tools:
            metadata = self._tool_registry._tools[tool_name].metadata
            
            # Remove from capability mappings
            if metadata.capability in self._capability_tools:
                self._capability_tools[metadata.capability].discard(tool_name)
                if not self._capability_tools[metadata.capability]:
                    del self._capability_tools[metadata.capability]
            
            if tool_name in self._tool_capabilities:
                del self._tool_capabilities[tool_name]
            
            # Emit monitoring event
            if self._monitoring_enabled and getattr(metadata, 'emits_monitoring', True):
                self._emit_tool_unregistered(metadata)
            
            return self._tool_registry.unregister(tool_name)
        return False
    
    def get_tool(self, tool_name: str) -> Optional[ToolInterface]:
        """Get a tool by name."""
        return self._tool_registry.get(tool_name)
    
    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name."""
        return self._tool_registry.get_metadata(tool_name)
    
    def contains(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        return self._tool_registry.contains(tool_name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        return self._tool_registry.list()
    
    def list_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """List tools providing a specific capability."""
        return self._tool_registry.list_by_capability(capability)
    
    def get_capabilities(self) -> List[str]:
        """Get all registered capability names."""
        return self._tool_registry.get_capabilities()
    
    def get_tools_for_capability(self, capability: str) -> List[str]:
        """Get tool names that provide a capability."""
        return list(self._capability_tools.get(capability, set()))
    
    def get_capabilities_for_tool(self, tool_name: str) -> List[str]:
        """Get capabilities provided by a tool."""
        return list(self._tool_capabilities.get(tool_name, set()))
    
    def discover_tools(
        self,
        capability: Optional[str] = None,
        risk_level: Optional[str] = None,
        available_only: bool = True,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Discover tools with filtering.
        
        Filters:
        - capability: specific capability to match
        - risk_level: max risk level ('low', 'medium', 'high')
        - available_only: only include available tools
        - tags: tags to match (any)
        - keywords: keywords to match in description (any)
        """
        tools = self.list_tools()
        
        if capability:
            tools = [t for t in tools if t["capability"] == capability]
        
        if risk_level:
            risk_order = {"low": 0, "medium": 1, "high": 2}
            max_risk = risk_order.get(risk_level, 2)
            tools = [t for t in tools if risk_order.get(t["risk_level"], 1) <= max_risk]
        
        if available_only:
            tools = [t for t in tools if t.get("available", True)]
        
        if tags:
            tools = [t for t in tools if any(tag in t.get("tags", []) for tag in tags)]
        
        if keywords:
            tools = [t for t in tools if any(
                kw.lower() in t.get("description", "").lower() for kw in keywords
            )]
        
        # Stable ordering: by name
        tools.sort(key=lambda x: x["name"])
        return tools
    
    def validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Validate tool arguments against schema."""
        metadata = self.get_metadata(tool_name)
        if not metadata:
            raise ValueError(f"Tool not found: {tool_name}")
        
        try:
            validate(instance=arguments, schema=metadata.arguments)
            return True
        except ValidationError as e:
            raise InvalidMetadataError(f"Argument validation failed: {e.message}")
    
    def validate_output(self, tool_name: str, output: Any) -> bool:
        """Validate tool output against schema."""
        metadata = self.get_metadata(tool_name)
        if not metadata or not metadata.output_schema:
            return True  # No schema to validate against
        
        try:
            validate(instance=output, schema=metadata.output_schema)
            return True
        except ValidationError as e:
            raise InvalidMetadataError(f"Output validation failed: {e.message}")
    
    def check_availability(self, tool_name: str) -> ToolAvailability:
        """Check tool availability."""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolAvailability.UNAVAILABLE
        
        if not tool.is_available():
            return ToolAvailability.UNAVAILABLE
        
        metadata = self.get_metadata(tool_name)
        if metadata and hasattr(metadata, 'availability_check') and metadata.availability_check:
            try:
                if not metadata.availability_check():
                    return ToolAvailability.TEMPORARILY_UNAVAILABLE
            except Exception:
                return ToolAvailability.TEMPORARILY_UNAVAILABLE
        
        if metadata and hasattr(metadata, 'availability'):
            return metadata.availability
        
        return ToolAvailability.AVAILABLE
    
    def set_lifecycle_state(self, tool_name: str, state: ToolLifecycleState) -> bool:
        """Set tool lifecycle state."""
        if tool_name in self._tool_registry._tools:
            self._tool_registry._tools[tool_name].metadata.lifecycle_state = state
            return True
        return False
    
    def get_lifecycle_state(self, tool_name: str) -> Optional[ToolLifecycleState]:
        """Get tool lifecycle state."""
        if tool_name in self._tool_registry._tools:
            return self._tool_registry._tools[tool_name].metadata.lifecycle_state
        return None
    
    def clear(self) -> None:
        """Clear all tools (for testing)."""
        self._tool_registry.clear()
        self._capability_tools.clear()
        self._tool_capabilities.clear()
    
    def _emit_tool_registered(self, metadata: ToolMetadata) -> None:
        """Emit tool registered monitoring event."""
        try:
            from app.monitoring.emitter import emit_tool_event
            emit_tool_event("tool.registered", metadata.name, {
                "capability": metadata.capability,
                "risk_level": metadata.risk_level,
            })
        except ImportError:
            pass  # Monitoring not available
    
    def _emit_tool_unregistered(self, metadata: ToolMetadata) -> None:
        """Emit tool unregistered monitoring event."""
        try:
            from app.monitoring.emitter import emit_tool_event
            emit_tool_event("tool.unregistered", metadata.name, {
                "capability": metadata.capability,
            })
        except ImportError:
            pass


# ============================================================
# Capability Registration
# ============================================================

def register_builtin_capabilities(capability_registry: CapabilityRegistry) -> None:
    """Register all built-in capabilities from Stage 31."""
    from app.tools.capabilities import BUILTIN_CAPABILITIES
    
    for cap_name, capability in BUILTIN_CAPABILITIES.items():
        try:
            capability_registry.register(capability)
        except DuplicateRegistrationError:
            pass  # Already registered
        except Exception:
            pass  # Skip invalid


# ============================================================
# Tool Discovery for Planner
# ============================================================

def get_available_tools_for_planner(dynamic_registry: DynamicToolRegistry) -> List[Dict[str, Any]]:
    """
    Get tools in format expected by Planner.
    Includes capability information for semantic selection.
    """
    tools = dynamic_registry.discover_tools(available_only=True)
    
    result = []
    for tool in tools:
        tool_info = {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool.get("arguments", {}),
            "selection_phrases": tool.get("keywords", []),
            "capability": tool["capability"],
            "risk_level": tool["risk_level"],
        }
        # Add capability details if available
        if dynamic_registry._capability_registry.contains(tool["capability"]):
            cap = dynamic_registry._capability_registry.get(tool["capability"])
            if cap:
                tool_info["capability_details"] = cap.to_dict()
        result.append(tool_info)
    
    return result


# ============================================================
# Tool Executor Integration
# ============================================================

class DynamicToolExecutor:
    """
    Tool executor that integrates with dynamic tool registry,
    permission system, and monitoring.
    """
    
    def __init__(
        self,
        dynamic_registry: DynamicToolRegistry,
        permission_manager: Any = None,
        monitoring_enabled: bool = True,
    ):
        self._registry = dynamic_registry
        self._permission_manager = permission_manager
        self._monitoring_enabled = monitoring_enabled
    
    def execute(self, tool_name: str, arguments: Dict[str, Any], 
                task_id: str = "", step_id: str = "",
                permission_mode: str = "BALANCED") -> ToolResult:
        """Execute a tool with full validation, permission, and monitoring."""
        start_time = datetime.utcnow()
        
        # 1. Check if tool exists
        tool = self._registry.get_tool(tool_name)
        if not tool:
            return ToolResult.failure(
                f"Tool not found: {tool_name}",
                tool_name=tool_name,
            )
        
        metadata = self._registry.get_metadata(tool_name)
        if not metadata:
            return ToolResult.failure(
                f"Tool metadata not found: {tool_name}",
                tool_name=tool_name,
            )
        
        capability = metadata.capability
        
        # 2. Check availability
        availability = self._registry.check_availability(tool_name)
        if availability != ToolAvailability.AVAILABLE:
            return ToolResult.unavailable(tool_name=tool_name, capability=capability)
        
        # 3. Validate arguments
        try:
            self._registry.validate_arguments(tool_name, arguments)
        except InvalidMetadataError as e:
            return ToolResult.validation_error(str(e), tool_name=tool_name, capability=capability)
        
        # 4. Check permissions
        if self._permission_manager and metadata.permission_required:
            permission_granted = self._check_permission(
                metadata.permission_required, permission_mode, tool_name
            )
            if not permission_granted:
                return ToolResult.permission_denied(
                    f"Permission denied: {metadata.permission_required}",
                    tool_name=tool_name,
                    capability=capability,
                )
        
        # 5. Execute tool
        try:
            result = tool.execute(arguments)
            
            # 6. Validate output
            if metadata.output_schema:
                try:
                    self._registry.validate_output(tool_name, result)
                except InvalidMetadataError as e:
                    return ToolResult.failure(
                        f"Output validation failed: {e}",
                        tool_name=tool_name,
                        capability=capability,
                    )
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # 7. Emit monitoring event
            if self._monitoring_enabled:
                self._emit_execution_event(
                    tool_name, capability, task_id, step_id,
                    ToolResultStatus.SUCCESS, duration_ms, arguments, result
                )
            
            return ToolResult.success(
                output=result,
                tool_name=tool_name,
                capability=capability,
                duration_ms=duration_ms,
                metadata={"arguments": self._sanitize_arguments(arguments)},
                verification_info={"status": "passed"} if metadata.verification_required else None,
            )
            
        except Exception as e:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            error_msg = str(e)
            
            # 8. Emit monitoring event for failure
            if self._monitoring_enabled:
                self._emit_execution_event(
                    tool_name, capability, task_id, step_id,
                    ToolResultStatus.FAILURE, duration_ms, arguments, None,
                    error=error_msg
                )
            
            return ToolResult.failure(
                error=error_msg,
                tool_name=tool_name,
                capability=capability,
                duration_ms=duration_ms,
            )
    
    def _check_permission(self, permission: str, mode: str, tool_name: str) -> bool:
        """Check if permission is granted."""
        if not self._permission_manager:
            return True
        
        if mode == "SAFE":
            # In SAFE mode, all permissions denied by default
            return False
        elif mode == "BALANCED":
            # In BALANCED mode, check if user has granted permission
            return self._permission_manager.check_permission(permission)
        elif mode == "FULL_AUTO":
            # In FULL_AUTO mode, permissions granted but validation still applies
            return True
        return False
    
    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize arguments for monitoring (remove secrets)."""
        sanitized = {}
        sensitive_keys = {
            "password", "secret", "token", "api_key", "apikey",
            "authorization", "auth", "credential", "private_key"
        }
        
        for key, value in arguments.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        return sanitized
    
    def _emit_execution_event(
        self,
        tool_name: str,
        capability: str,
        task_id: str,
        step_id: str,
        status: ToolResultStatus,
        duration_ms: int,
        arguments: Dict[str, Any],
        output: Any,
        error: Optional[str] = None,
    ) -> None:
        """Emit execution monitoring event with sanitized data."""
        try:
            from app.monitoring.emitter import emit_tool_event
            emit_tool_event("tool.executed", tool_name, {
                "capability": capability,
                "task_id": task_id,
                "step_id": step_id,
                "status": status.value,
                "duration_ms": duration_ms,
                "arguments": self._sanitize_arguments(arguments),
                "error": error,
            })
        except ImportError:
            pass


# ============================================================
# Mock Tools for Testing
# ============================================================

class MockCalculatorTool(ToolInterface):
    """Mock calculator tool for testing dynamic registration."""
    
    def __init__(self, tool_id: str = "mock_calculator", capability: str = "test.calculation"):
        self._tool_id = tool_id
        self._capability = capability
        self._available = True
        self._metadata = None  # Cache metadata
        self._availability_check = None  # Custom availability check
    
    @property
    def tool_id(self) -> str:
        return self._tool_id
    
    def get_metadata(self) -> EnhancedToolMetadata:
        if self._metadata is None:
            self._metadata = EnhancedToolMetadata(
                name=self._tool_id,
                description=f"Mock calculator for {self._capability}",
                capability=self._capability,
                arguments={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                        "operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]},
                    },
                    "required": ["a", "b", "operation"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "result": {"type": "number"},
                        "operation": {"type": "string"},
                    },
                    "required": ["result", "operation"],
                },
                risk_level="low",
                side_effects=[],
                permission_required=None,
                verification_required=True,
                availability_requirements=[],
                lifecycle_state=ToolLifecycleState.REGISTERED,
            )
        # Apply custom availability check if set
        if self._availability_check is not None:
            self._metadata.availability_check = self._availability_check
        return self._metadata
    
    def execute(self, arguments: Dict[str, Any]) -> Any:
        a = arguments["a"]
        b = arguments["b"]
        op = arguments["operation"]
        
        if op == "add":
            result = a + b
        elif op == "subtract":
            result = a - b
        elif op == "multiply":
            result = a * b
        elif op == "divide":
            if b == 0:
                raise ValueError("Division by zero")
            result = a / b
        else:
            raise ValueError(f"Unknown operation: {op}")
        
        return {"result": result, "operation": op}
    
    def is_available(self) -> bool:
        return self._available
    
    def set_available(self, available: bool) -> None:
        self._available = available
        
    def set_availability_check(self, check_func):
        """Set a custom availability check function"""
        self._availability_check = check_func
        # Invalidate cache so next get_metadata picks up the change
        self._metadata = None


class MockUnsafeTool(ToolInterface):
    """Mock unsafe tool for security testing."""
    
    def __init__(self):
        self._tool_id = "mock_unsafe_tool"
        self._capability = "test.unsafe"
    
    def get_metadata(self) -> EnhancedToolMetadata:
        # Claims low risk but declares unsafe behavior
        return EnhancedToolMetadata(
            name=self._tool_id,
            description="A tool that claims to be safe but isn't",
            capability=self._capability,
            arguments={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
            risk_level="low",  # LIES: claims low risk
            side_effects=["executes arbitrary commands"],  # Declares unsafe behavior
            permission_required="",  # Omitted permission metadata (empty string triggers validation)
            verification_required=False,  # No verification
            availability_requirements=[],
            lifecycle_state=ToolLifecycleState.REGISTERED,
        )
    
    def execute(self, arguments: Dict[str, Any]) -> Any:
        # This would execute arbitrary commands (unsafe!)
        return {"executed": arguments["command"]}
    
    def is_available(self) -> bool:
        return True


# ============================================================
# Integration with ExtensionManager
# ============================================================

def create_dynamic_extension_manager(
    legacy_tool_registry: Optional[ToolRegistry] = None,
) -> ExtensionManager:
    """Create ExtensionManager with dynamic tool registry."""
    manager = ExtensionManager()
    
    # Create dynamic tool registry
    dynamic_registry = DynamicToolRegistry(manager)
    
    # Register built-in capabilities
    register_builtin_capabilities(dynamic_registry._capability_registry)
    
    # Migrate legacy tools if provided
    if legacy_tool_registry:
        dynamic_registry.register_legacy_registry(legacy_tool_registry)
    
    # Replace tool registry in manager
    manager.tools = dynamic_registry
    
    return manager


def create_dynamic_tool_executor(
    dynamic_registry: DynamicToolRegistry,
    permission_manager: Any = None,
) -> DynamicToolExecutor:
    """Create DynamicToolExecutor with dynamic registry."""
    return DynamicToolExecutor(dynamic_registry, permission_manager)


# ============================================================
# Re-export for backward compatibility
# ============================================================

__all__ = [
    "EnhancedToolMetadata",
    "ToolAvailability",
    "ToolLifecycleState",
    "ToolResultStatus",
    "ToolResult",
    "DynamicToolRegistry",
    "DynamicToolExecutor",
    "register_builtin_capabilities",
    "get_available_tools_for_planner",
    "create_dynamic_extension_manager",
    "create_dynamic_tool_executor",
    "MockCalculatorTool",
    "MockUnsafeTool",
    "wrap_legacy_tool_registry",
]


# Helper function to wrap legacy registry (from registry.py)
def wrap_legacy_tool_registry(legacy_registry: ToolRegistry) -> ToolExtensionRegistry:
    """Wrap a legacy ToolRegistry to expose the new contract."""
    new_registry = ToolExtensionRegistry()
    
    # Get all registered legacy tools
    for tool_info in legacy_registry.list_tools_with_capabilities():
        name = tool_info["name"]
        try:
            legacy_tool = legacy_registry.get(name)
            adapter = LegacyToolAdapter(legacy_tool)
            if not new_registry.contains(name):
                new_registry.register(adapter)
        except Exception:
            pass
    
    return new_registry