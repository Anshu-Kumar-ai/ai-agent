"""
Extension Registry System - Stage 32 Phase 1

Provides explicit registration, validation, discovery, and security enforcement
for all extension types: providers, tools, capabilities, skills, application adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type, Union
from enum import Enum

from app.extensions.contracts import (
    ProviderInterface,
    ToolInterface,
    ToolMetadata,
    SkillContract,
)
from app.tools.capabilities import CapabilityCategory, ToolCapability, SideEffectLevel


# ============================================================
# Base Registry Class
# ============================================================

class RegistryError(Exception):
    """Base exception for registry operations."""
    pass


class DuplicateRegistrationError(RegistryError):
    """Raised when attempting to register a duplicate extension."""
    pass


class InvalidMetadataError(RegistryError):
    """Raised when extension metadata is invalid."""
    pass


class MissingInterfaceError(RegistryError):
    """Raised when an extension doesn't implement required interface."""
    pass


class SecurityValidationError(RegistryError):
    """Raised when security metadata validation fails."""
    pass


# ============================================================
# Extension Type Enum
# ============================================================

class ExtensionType(Enum):
    PROVIDER = "provider"
    TOOL = "tool"
    CAPABILITY = "capability"
    SKILL = "skill"
    APPLICATION_ADAPTER = "application_adapter"


# ============================================================
# Provider Registry
# ============================================================

class ProviderRegistry:
    """Registry for LLM provider extensions."""

    def __init__(self):
        self._providers: Dict[str, ProviderInterface] = {}

    def register(self, provider: ProviderInterface) -> None:
        """Register a provider."""
        if not isinstance(provider, ProviderInterface):
            raise MissingInterfaceError(
                f"Provider must implement ProviderInterface, got {type(provider).__name__}"
            )

        provider_id = provider.provider_id
        if not provider_id:
            raise InvalidMetadataError("Provider must have a non-empty provider_id")

        if provider_id in self._providers:
            raise DuplicateRegistrationError(
                f"Provider already registered: {provider_id}"
            )

        if not provider.model_id:
            raise InvalidMetadataError("Provider must have a non-empty model_id")

        self._providers[provider_id] = provider

    def unregister(self, provider_id: str) -> bool:
        """Unregister a provider. Returns True if existed."""
        if provider_id in self._providers:
            del self._providers[provider_id]
            return True
        return False

    def get(self, provider_id: str) -> Optional[ProviderInterface]:
        """Get a provider by ID."""
        return self._providers.get(provider_id)

    def list(self) -> List[Dict[str, Any]]:
        """List all registered providers with metadata."""
        return [
            {
                "provider_id": p.provider_id,
                "model_id": p.model_id,
                "available": p.is_available(),
                "timeout": p.get_timeout(),
                "health": p.get_health_info(),
            }
            for p in self._providers.values()
        ]

    def contains(self, provider_id: str) -> bool:
        """Check if provider is registered."""
        return provider_id in self._providers

    def clear(self) -> None:
        """Clear all providers (for testing)."""
        self._providers.clear()


# ============================================================
# Tool Registry (Extension)
# ============================================================

@dataclass
class ToolRegistration:
    """Tool registration record with metadata."""
    tool: ToolInterface
    metadata: ToolMetadata


class ToolExtensionRegistry:
    """Registry for tool extensions with full contract validation."""

    def __init__(self):
        self._tools: Dict[str, ToolRegistration] = {}
        # Map capability -> set of tool names
        self._capability_index: Dict[str, Set[str]] = {}

    def _validate_metadata(self, metadata: ToolMetadata) -> None:
        """Validate tool metadata."""
        if not metadata.name:
            raise InvalidMetadataError("Tool must have a non-empty name")

        if not metadata.description:
            raise InvalidMetadataError("Tool must have a non-empty description")

        if not metadata.capability:
            raise InvalidMetadataError("Tool must declare a capability")

        if not metadata.arguments:
            raise InvalidMetadataError("Tool must have arguments schema")

        valid_risk_levels = {"low", "medium", "high"}
        if metadata.risk_level not in valid_risk_levels:
            raise InvalidMetadataError(
                f"Invalid risk_level: {metadata.risk_level}. Must be one of {valid_risk_levels}"
            )

        valid_verification = {True, False}
        if metadata.verification_required not in valid_verification:
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

    def register(self, tool: ToolInterface) -> None:
        """Register a tool."""
        if not isinstance(tool, ToolInterface):
            raise MissingInterfaceError(
                f"Tool must implement ToolInterface, got {type(tool).__name__}"
            )

        metadata = tool.get_metadata()
        self._validate_metadata(metadata)
        self._validate_security_metadata(metadata)

        if metadata.name in self._tools:
            raise DuplicateRegistrationError(
                f"Tool already registered: {metadata.name}"
            )

        # Register tool
        self._tools[metadata.name] = ToolRegistration(tool=tool, metadata=metadata)

        # Update capability index
        if metadata.capability not in self._capability_index:
            self._capability_index[metadata.capability] = set()
        self._capability_index[metadata.capability].add(metadata.name)

    def unregister(self, tool_name: str) -> bool:
        """Unregister a tool. Returns True if existed."""
        if tool_name in self._tools:
            metadata = self._tools[tool_name].metadata
            # Remove from capability index
            if metadata.capability in self._capability_index:
                self._capability_index[metadata.capability].discard(tool_name)
                if not self._capability_index[metadata.capability]:
                    del self._capability_index[metadata.capability]
            del self._tools[tool_name]
            return True
        return False

    def get(self, tool_name: str) -> Optional[ToolInterface]:
        """Get a tool by name."""
        reg = self._tools.get(tool_name)
        return reg.tool if reg else None

    def get_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name."""
        reg = self._tools.get(tool_name)
        return reg.metadata if reg else None

    def list(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata."""
        return [
            {
                "name": reg.metadata.name,
                "description": reg.metadata.description,
                "capability": reg.metadata.capability,
                "risk_level": reg.metadata.risk_level,
                "side_effects": reg.metadata.side_effects,
                "permission_required": reg.metadata.permission_required,
                "verification_required": reg.metadata.verification_required,
                "availability_requirements": reg.metadata.availability_requirements,
                "available": reg.tool.is_available(),
            }
            for reg in self._tools.values()
        ]

    def list_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """List tools providing a specific capability."""
        tool_names = self._capability_index.get(capability, set())
        return [
            {
                "name": self._tools[name].metadata.name,
                "description": self._tools[name].metadata.description,
                "capability": capability,
                "risk_level": self._tools[name].metadata.risk_level,
                "available": self._tools[name].tool.is_available(),
            }
            for name in tool_names
        ]

    def contains(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        return tool_name in self._tools

    def get_capabilities(self) -> List[str]:
        """Get all registered capability names."""
        return list(self._capability_index.keys())

    def clear(self) -> None:
        """Clear all tools (for testing)."""
        self._tools.clear()
        self._capability_index.clear()


# ============================================================
# Capability Registry
# ============================================================

class CapabilityRegistry:
    """Registry for capability definitions."""

    def __init__(self):
        self._capabilities: Dict[str, ToolCapability] = {}

    def register(self, capability: ToolCapability) -> None:
        """Register a capability."""
        if not isinstance(capability, ToolCapability):
            raise MissingInterfaceError(
                f"Capability must be ToolCapability, got {type(capability).__name__}"
            )

        if not capability.name:
            raise InvalidMetadataError("Capability must have a non-empty name")

        if capability.name in self._capabilities:
            raise DuplicateRegistrationError(
                f"Capability already registered: {capability.name}"
            )

        if not capability.categories:
            raise InvalidMetadataError("Capability must have at least one category")

        self._capabilities[capability.name] = capability

    def unregister(self, capability_name: str) -> bool:
        """Unregister a capability. Returns True if existed."""
        if capability_name in self._capabilities:
            del self._capabilities[capability_name]
            return True
        return False

    def get(self, capability_name: str) -> Optional[ToolCapability]:
        """Get a capability by name."""
        return self._capabilities.get(capability_name)

    def list(self) -> List[Dict[str, Any]]:
        """List all registered capabilities."""
        return [c.to_dict() for c in self._capabilities.values()]

    def list_by_category(self, category: CapabilityCategory) -> List[Dict[str, Any]]:
        """List capabilities by category."""
        return [
            c.to_dict() for c in self._capabilities.values()
            if c.matches_category(category)
        ]

    def contains(self, capability_name: str) -> bool:
        """Check if capability is registered."""
        return capability_name in self._capabilities

    def clear(self) -> None:
        """Clear all capabilities (for testing)."""
        self._capabilities.clear()


# ============================================================
# Skill Registry
# ============================================================

class SkillExtensionRegistry:
    """Registry for skill extensions with contract validation."""

    def __init__(self, max_skills: int = 100):
        self._skills: Dict[str, SkillContract] = {}
        self.max_skills = max_skills

    def _validate_skill(self, skill: SkillContract) -> None:
        """Validate skill contract."""
        if not skill.name:
            raise InvalidMetadataError("Skill must have a non-empty name")

        if not skill.intent:
            raise InvalidMetadataError("Skill must have a non-empty intent")

        if not skill.required_capabilities:
            raise InvalidMetadataError("Skill must declare required_capabilities")

        valid_strategies = {"standard", "strict", "none"}
        if skill.verification_strategy not in valid_strategies:
            raise InvalidMetadataError(
                f"Invalid verification_strategy: {skill.verification_strategy}. Must be one of {valid_strategies}"
            )

        # Validate workflow structure
        for i, step in enumerate(skill.workflow):
            if not isinstance(step, dict):
                raise InvalidMetadataError(f"Workflow step {i} must be a dict")
            if "tool" not in step:
                raise InvalidMetadataError(f"Workflow step {i} missing required 'tool' field")
            if "produces" not in step:
                raise InvalidMetadataError(f"Workflow step {i} missing required 'produces' field")

    def register(self, skill: SkillContract) -> None:
        """Register a skill."""
        if not isinstance(skill, SkillContract):
            raise MissingInterfaceError(
                f"Skill must be SkillContract, got {type(skill).__name__}"
            )

        self._validate_skill(skill)

        if skill.name in self._skills:
            raise DuplicateRegistrationError(
                f"Skill already registered: {skill.name}"
            )

        # Evict LRU if at capacity
        if len(self._skills) >= self.max_skills:
            oldest = min(
                self._skills.values(),
                key=lambda s: s.usage_metadata.get("last_used", 0)
            )
            del self._skills[oldest.name]

        self._skills[skill.name] = skill

    def unregister(self, skill_name: str) -> bool:
        """Unregister a skill. Returns True if existed."""
        if skill_name in self._skills:
            del self._skills[skill_name]
            return True
        return False

    def get(self, skill_name: str) -> Optional[SkillContract]:
        """Get a skill by name."""
        return self._skills.get(skill_name)

    def list(self) -> List[Dict[str, Any]]:
        """List all registered skills."""
        return [s.to_dict() for s in self._skills.values()]

    def find_relevant(
        self,
        goal: str,
        required_capabilities: List[str],
        available_tools: List[str],
        current_permissions: List[str],
        environment: Dict[str, Any],
    ) -> List[SkillContract]:
        """Find skills relevant to the goal, ranked by match score."""
        candidates = []

        for skill in self._skills.values():
            # Check applicability
            applicable, reasons = skill.is_applicable(goal, available_tools, current_permissions, environment)
            if not applicable:
                continue

            # Calculate match score
            score = skill.matches_intent(goal, required_capabilities)
            if score > 0:
                skill.usage_metadata["last_used"] = __import__("time").time()
                candidates.append((score, skill))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: -x[0])
        return [s for _, s in candidates]

    def contains(self, skill_name: str) -> bool:
        """Check if skill is registered."""
        return skill_name in self._skills

    def clear(self) -> None:
        """Clear all skills (for testing)."""
        self._skills.clear()


# ============================================================
# Application Adapter Registry
# ============================================================

class ApplicationAdapterInterface(ABC):
    """Interface for application adapters."""
    
    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for the adapter."""
        pass

    @property
    @abstractmethod
    def supported_application(self) -> str:
        """Name of the application this adapter targets."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """List of capabilities this adapter provides."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if adapter is available (dependencies installed)."""
        pass

    @abstractmethod
    def execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute an action on the target application."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources."""
        pass


class ApplicationAdapterRegistry:
    """Registry for application adapters."""

    def __init__(self):
        self._adapters: Dict[str, ApplicationAdapterInterface] = {}

    def register(self, adapter: ApplicationAdapterInterface) -> None:
        """Register an application adapter."""
        if not isinstance(adapter, ApplicationAdapterInterface):
            raise MissingInterfaceError(
                f"Adapter must implement ApplicationAdapterInterface, got {type(adapter).__name__}"
            )

        adapter_id = adapter.adapter_id
        if not adapter_id:
            raise InvalidMetadataError("Adapter must have a non-empty adapter_id")

        if not adapter.supported_application:
            raise InvalidMetadataError("Adapter must have a supported_application")

        if adapter_id in self._adapters:
            raise DuplicateRegistrationError(
                f"Adapter already registered: {adapter_id}"
            )

        if not adapter.capabilities:
            raise InvalidMetadataError("Adapter must declare capabilities")

        self._adapters[adapter_id] = adapter

    def unregister(self, adapter_id: str) -> bool:
        """Unregister an adapter. Returns True if existed."""
        if adapter_id in self._adapters:
            del self._adapters[adapter_id]
            return True
        return False

    def get(self, adapter_id: str) -> Optional[ApplicationAdapterInterface]:
        """Get an adapter by ID."""
        return self._adapters.get(adapter_id)

    def list(self) -> List[Dict[str, Any]]:
        """List all registered adapters."""
        return [
            {
                "adapter_id": a.adapter_id,
                "supported_application": a.supported_application,
                "capabilities": a.capabilities,
                "available": a.is_available(),
            }
            for a in self._adapters.values()
        ]

    def list_by_application(self, application: str) -> List[Dict[str, Any]]:
        """List adapters for a specific application."""
        return [
            {
                "adapter_id": a.adapter_id,
                "supported_application": a.supported_application,
                "capabilities": a.capabilities,
                "available": a.is_available(),
            }
            for a in self._adapters.values()
            if a.supported_application == application
        ]

    def list_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """List adapters providing a specific capability."""
        return [
            {
                "adapter_id": a.adapter_id,
                "supported_application": a.supported_application,
                "capabilities": a.capabilities,
                "available": a.is_available(),
            }
            for a in self._adapters.values()
            if capability in a.capabilities
        ]

    def contains(self, adapter_id: str) -> bool:
        """Check if adapter is registered."""
        return adapter_id in self._adapters

    def clear(self) -> None:
        """Clear all adapters (for testing)."""
        self._adapters.clear()


# ============================================================
# Extension Manager (Unified Access)
# ============================================================

class ExtensionManager:
    """Unified manager for all extension registries."""

    def __init__(self):
        self.providers = ProviderRegistry()
        self.tools = ToolExtensionRegistry()
        self.capabilities = CapabilityRegistry()
        self.skills = SkillExtensionRegistry()
        self.adapters = ApplicationAdapterRegistry()

    def register(self, extension: Any, extension_type: ExtensionType) -> None:
        """Register an extension by type."""
        if extension_type == ExtensionType.PROVIDER:
            self.providers.register(extension)
        elif extension_type == ExtensionType.TOOL:
            self.tools.register(extension)
        elif extension_type == ExtensionType.CAPABILITY:
            self.capabilities.register(extension)
        elif extension_type == ExtensionType.SKILL:
            self.skills.register(extension)
        elif extension_type == ExtensionType.APPLICATION_ADAPTER:
            self.adapters.register(extension)
        else:
            raise ValueError(f"Unknown extension type: {extension_type}")

    def discover(self) -> Dict[str, List[Dict[str, Any]]]:
        """Discover all available extensions."""
        return {
            "providers": self.providers.list(),
            "tools": self.tools.list(),
            "capabilities": self.capabilities.list(),
            "skills": self.skills.list(),
            "application_adapters": self.adapters.list(),
        }

    def discover_by_type(self, extension_type: ExtensionType) -> List[Dict[str, Any]]:
        """Discover extensions of a specific type."""
        if extension_type == ExtensionType.PROVIDER:
            return self.providers.list()
        elif extension_type == ExtensionType.TOOL:
            return self.tools.list()
        elif extension_type == ExtensionType.CAPABILITY:
            return self.capabilities.list()
        elif extension_type == ExtensionType.SKILL:
            return self.skills.list()
        elif extension_type == ExtensionType.APPLICATION_ADAPTER:
            return self.adapters.list()
        else:
            raise ValueError(f"Unknown extension type: {extension_type}")

    def clear_all(self) -> None:
        """Clear all registries (for testing)."""
        self.providers.clear()
        self.tools.clear()
        self.capabilities.clear()
        self.skills.clear()
        self.adapters.clear()


# ============================================================
# Backward Compatibility Adapter
# ============================================================

class LegacyToolAdapter(ToolInterface):
    """Adapter to make legacy BaseTool compatible with ToolInterface."""

    def __init__(self, legacy_tool: Any):
        self._legacy_tool = legacy_tool

    def get_metadata(self) -> ToolMetadata:
        """Generate metadata from legacy tool."""
        # Extract parameters schema
        arguments = getattr(self._legacy_tool, "parameters", {})
        
        # Determine capability from name
        name = getattr(self._legacy_tool, "name", "unknown")
        capability = self._infer_capability(name)

        # Determine risk level from capability
        risk_level = self._infer_risk_level(capability)

        return ToolMetadata(
            name=name,
            description=getattr(self._legacy_tool, "description", ""),
            capability=capability,
            arguments=arguments,
            risk_level=risk_level,
            side_effects=self._infer_side_effects(capability),
            permission_required=self._infer_permission(capability),
            verification_required=capability in {"filesystem", "terminal", "browser", "desktop"},
            availability_requirements=self._infer_availability(capability),
        )

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute legacy tool."""
        return self._legacy_tool.execute(**arguments)

    def is_available(self) -> bool:
        """Check if legacy tool is available."""
        # Legacy tools don't have is_available; assume available
        return True

    def _infer_capability(self, name: str) -> str:
        """Infer capability from tool name."""
        if name.startswith("fs.") or name.startswith("filesystem"):
            return "filesystem"
        elif name.startswith("terminal"):
            return "terminal"
        elif name.startswith("browser"):
            return "browser"
        elif name.startswith("desktop"):
            return "desktop"
        elif name.startswith("web") or name.startswith("http"):
            return "network"
        elif name.startswith("rag"):
            return "knowledge"
        elif name == "calculator" or name == "time_tool":
            return "computation"
        elif name == "python.exec":
            return "code_execution"
        return "computation"

    def _infer_risk_level(self, capability: str) -> str:
        """Infer risk level from capability."""
        high_risk = {"terminal", "code_execution", "browser", "desktop"}
        medium_risk = {"filesystem", "network"}
        if capability in high_risk:
            return "high"
        elif capability in medium_risk:
            return "medium"
        return "low"

    def _infer_side_effects(self, capability: str) -> List[str]:
        """Infer side effects from capability."""
        effects = {
            "filesystem": ["reads/writes files in workspace"],
            "terminal": ["executes shell commands"],
            "browser": ["makes network requests", "controls browser"],
            "desktop": ["interacts with desktop applications"],
            "network": ["makes network requests"],
            "code_execution": ["executes arbitrary code"],
            "computation": [],
            "knowledge": ["reads/writes vector store"],
        }
        return effects.get(capability, [])

    def _infer_permission(self, capability: str) -> Optional[str]:
        """Infer required permission from capability."""
        permissions = {
            "filesystem": "fs.write",
            "terminal": "terminal.run",
            "browser": "browser.navigate",
            "desktop": "desktop.click",
            "code_execution": "python.exec",
        }
        return permissions.get(capability)

    def _infer_availability(self, capability: str) -> List[str]:
        """Infer availability requirements from capability."""
        requirements = {
            "browser": ["playwright", "chromium"],
            "desktop": ["pywinauto", "windows"],
            "code_execution": ["python"],
            "knowledge": ["faiss", "sentence_transformers"],
        }
        return requirements.get(capability, [])


# ============================================================
# Compatibility Wrapper for Legacy ToolRegistry
# ============================================================

def wrap_legacy_tool_registry(legacy_registry: Any) -> ToolExtensionRegistry:
    """Wrap a legacy ToolRegistry to expose the new contract."""
    new_registry = ToolExtensionRegistry()

    # Get all registered legacy tools
    for tool_info in legacy_registry.list_tools_with_capabilities():
        name = tool_info["name"]
        try:
            legacy_tool = legacy_registry.get(name)
            adapter = LegacyToolAdapter(legacy_tool)
            # Only register if not already present
            if not new_registry.contains(name):
                new_registry.register(adapter)
        except Exception:
            # Skip tools that can't be adapted
            pass

    return new_registry


# ============================================================
# Factory for creating ExtensionManager
# ============================================================

def create_extension_manager() -> ExtensionManager:
    """Create a new ExtensionManager with empty registries."""
    return ExtensionManager()


def create_extension_manager_with_legacy(legacy_tool_registry: Any) -> ExtensionManager:
    """Create ExtensionManager with legacy tools pre-registered."""
    manager = ExtensionManager()
    # Wrap and migrate legacy tools
    wrapped = wrap_legacy_tool_registry(legacy_tool_registry)
    manager.tools = wrapped
    return manager