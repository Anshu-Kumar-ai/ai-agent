"""
Adapter-Tool Bridge - Stage 32 Phase 5
Converts application adapter capabilities into tools for the DynamicToolRegistry.
"""

from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    AdapterMetadata,
)
from app.extensions.contracts import ToolInterface, ToolMetadata
from app.extensions.dynamic_tools import DynamicToolRegistry, ToolResult, ToolResultStatus
from app.tools.capabilities import CapabilityCategory, ToolCapability, SideEffectLevel


@dataclass
class AdapterToolMapping:
    """Maps an adapter capability to a tool."""
    adapter_id: str
    capability: str
    tool_name: str
    description: str
    arguments_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    risk_level: str = "medium"
    side_effect_level: str = "write"
    permission_required: Optional[str] = None
    verification_required: bool = True
    availability_requirements: List[str] = None


class AdapterToolBridge:
    """
    Bridge that converts ApplicationAdapterInterface capabilities into ToolInterface
    compatible tools for the DynamicToolRegistry.
    
    This allows the agent to reason about capabilities/tools rather than concrete applications.
    """
    
    def __init__(
        self,
        dynamic_tool_registry: DynamicToolRegistry,
        adapter_factory: Optional[Callable[[str], ApplicationAdapterInterface]] = None
    ):
        self.dynamic_registry = dynamic_tool_registry
        self.adapter_factory = adapter_factory
        self._mappings: Dict[str, AdapterToolMapping] = {}
        self._adapter_instances: Dict[str, ApplicationAdapterInterface] = {}
    
    def register_adapter(self, adapter: ApplicationAdapterInterface) -> None:
        """
        Register an application adapter and create tool mappings for its capabilities.
        
        Args:
            adapter: The application adapter instance to register
        """
        # Store adapter instance
        self._adapter_instances[adapter.adapter_id] = adapter
        
        # Create tool mappings for each capability
        metadata = adapter.metadata
        for capability in adapter.get_capabilities():
            mapping = self._create_mapping(adapter, capability, metadata)
            self._mappings[mapping.tool_name] = mapping
            
            # Create and register the tool
            tool = self._create_tool_from_mapping(mapping, adapter)
            self.dynamic_registry.register_tool(tool)
    
    def unregister_adapter(self, adapter_id: str) -> bool:
        """
        Unregister an adapter and its tools.
        
        Args:
            adapter_id: ID of the adapter to unregister
            
        Returns:
            True if adapter was found and unregistered
        """
        if adapter_id not in self._adapter_instances:
            return False
        
        # Find and unregister all tools for this adapter
        tools_to_remove = [
            name for name, mapping in self._mappings.items()
            if mapping.adapter_id == adapter_id
        ]
        
        for tool_name in tools_to_remove:
            self.dynamic_registry.unregister_tool(tool_name)
            del self._mappings[tool_name]
        
        # Cleanup adapter instance
        adapter = self._adapter_instances.pop(adapter_id)
        adapter.cleanup()
        
        return True
    
    def _create_mapping(
        self,
        adapter: ApplicationAdapterInterface,
        capability: str,
        metadata: AdapterMetadata
    ) -> AdapterToolMapping:
        """Create a tool mapping for an adapter capability."""
        # Generate tool name from capability
        tool_name = capability
        
        # Get capability definition from built-in capabilities if available
        cap_def = self._get_capability_definition(capability)
        
        if cap_def:
            return AdapterToolMapping(
                adapter_id=adapter.adapter_id,
                capability=capability,
                tool_name=tool_name,
                description=cap_def.description,
                arguments_schema=self._capability_to_schema(cap_def),
                output_schema=None,
                risk_level=cap_def.risk_level,
                side_effect_level=cap_def.side_effect_level.value,
                permission_required=metadata.security_metadata.get("permission_required"),
                verification_required=cap_def.supports_verification,
                availability_requirements=metadata.availability_requirements,
            )
        else:
            # Fallback for unknown capabilities
            return AdapterToolMapping(
                adapter_id=adapter.adapter_id,
                capability=capability,
                tool_name=tool_name,
                description=f"Execute {capability} via {adapter.metadata.display_name}",
                arguments_schema={"type": "object", "properties": {}},
                risk_level=metadata.risk_level,
                side_effect_level=metadata.side_effect_level,
                permission_required=metadata.security_metadata.get("permission_required"),
                verification_required=metadata.requires_verification,
                availability_requirements=metadata.availability_requirements,
            )
    
    def _get_capability_definition(self, capability: str) -> Optional[ToolCapability]:
        """Get capability definition from built-in capabilities."""
        from app.tools.capabilities import get_capability
        return get_capability(capability)
    
    def _capability_to_schema(self, cap: ToolCapability) -> Dict[str, Any]:
        """Convert ToolCapability to JSON Schema."""
        properties = {}
        required = []
        
        for param in cap.required_parameters:
            properties[param] = {"type": "string", "description": f"Required parameter: {param}"}
            required.append(param)
        
        for param in cap.optional_parameters:
            properties[param] = {"type": "string", "description": f"Optional parameter: {param}"}
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
    
    def _create_tool_from_mapping(
        self,
        mapping: AdapterToolMapping,
        adapter: ApplicationAdapterInterface
    ) -> ToolInterface:
        """Create a ToolInterface implementation from a mapping."""
        
        class AdapterTool(ToolInterface):
            def __init__(self, mapping: AdapterToolMapping, adapter: ApplicationAdapterInterface):
                self._mapping = mapping
                self._adapter = adapter
            
            def get_metadata(self) -> ToolMetadata:
                return ToolMetadata(
                    name=self._mapping.tool_name,
                    description=self._mapping.description,
                    capability=self._mapping.capability,
                    arguments=self._mapping.arguments_schema,
                    output_schema=self._mapping.output_schema,
                    risk_level=self._mapping.risk_level,
                    side_effects=[self._mapping.side_effect_level],
                    permission_required=self._mapping.permission_required,
                    verification_required=self._mapping.verification_required,
                    availability_requirements=self._mapping.availability_requirements or [],
                )
            
            def execute(self, arguments: Dict[str, Any]) -> Any:
                return self._adapter.execute(self._mapping.capability, arguments)
            
            def is_available(self) -> bool:
                return self._adapter.is_available()
        
        return AdapterTool(mapping, adapter)
    
    def get_adapter(self, adapter_id: str) -> Optional[ApplicationAdapterInterface]:
        """Get an adapter instance by ID."""
        return self._adapter_instances.get(adapter_id)
    
    def list_adapters(self) -> List[Dict[str, Any]]:
        """List all registered adapters."""
        return [
            {
                "adapter_id": adapter.adapter_id,
                "application_id": adapter.application_id,
                "capabilities": adapter.get_capabilities(),
                "available": adapter.is_available(),
                "state": adapter.get_state().value,
            }
            for adapter in self._adapter_instances.values()
        ]
    
    def list_tools_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """List tools that provide a specific capability."""
        return [
            {
                "tool_name": mapping.tool_name,
                "adapter_id": mapping.adapter_id,
                "description": mapping.description,
                "risk_level": mapping.risk_level,
                "available": self._adapter_instances[mapping.adapter_id].is_available(),
            }
            for mapping in self._mappings.values()
            if mapping.capability == capability
        ]
    
    def get_capabilities_summary(self) -> Dict[str, List[str]]:
        """Get a summary of all available capabilities grouped by application."""
        summary = {}
        for adapter_id, adapter in self._adapter_instances.items():
            if adapter.is_available():
                summary[adapter.application_id] = adapter.get_capabilities()
        return summary
    
    def discover_applications(self) -> List[Dict[str, Any]]:
        """
        Answer: "What applications can the agent currently control?"
        
        Returns structured information about available adapters.
        """
        return [
            {
                "adapter_id": adapter.adapter_id,
                "application_id": adapter.application_id,
                "display_name": adapter.metadata.display_name,
                "version": adapter.metadata.version,
                "capabilities": adapter.get_capabilities(),
                "available": adapter.is_available(),
                "availability_requirements": adapter.metadata.availability_requirements,
                "environment_requirements": adapter.metadata.environment_requirements,
            }
            for adapter in self._adapter_instances.values()
        ]


def create_adapter_tool_bridge(
    dynamic_tool_registry: DynamicToolRegistry
) -> AdapterToolBridge:
    """Factory function to create an adapter-tool bridge."""
    return AdapterToolBridge(dynamic_tool_registry)