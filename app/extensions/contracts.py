"""
Extension Contracts - Stage 32 Phase 1
Defines interfaces and metadata models for extensible agent architecture.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Provider Contract

class ProviderInterface(ABC):
    """Interface for LLM providers."""
    
    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for the provider (e.g., 'openai', 'anthropic')."""
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier for the model being used (e.g., 'gpt-4', 'claude-3-sonnet')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API keys set, network reachable, etc.)."""
        pass

    @abstractmethod
    def invoke(self, prompt: str, **kwargs) -> str:
        """Invoke the model with the given prompt and return the response text."""
        pass

    @abstractmethod
    def get_timeout(self) -> float:
        """Return the default timeout for invocations in seconds."""
        pass

    @abstractmethod
    def classify_failure(self, exception: Exception) -> str:
        """Classify an exception into a failure category for retry logic."""
        pass

    @abstractmethod
    def get_token_usage(self) -> Dict[str, int]:
        """Return token usage statistics if available (prompt, completion, total)."""
        pass

    @abstractmethod
    def get_health_info(self) -> Dict[str, Any]:
        """Return health information (latency, rate limits, etc.)."""
        pass


# Tool Contract

@dataclass
class ToolMetadata:
    """Metadata describing a tool's capabilities and requirements."""
    name: str
    description: str
    capability: str  # Capability category this tool satisfies
    arguments: Dict[str, Any]  # JSON Schema for tool arguments
    output_schema: Optional[Dict[str, Any]] = None  # JSON Schema for tool output
    risk_level: str = "low"  # Risk level: low, medium, high
    side_effects: List[str] = field(default_factory=list)  # Descriptions of side effects
    permission_required: Optional[str] = None  # Permission name required to use this tool
    verification_required: bool = False  # Whether output requires verification
    availability_requirements: List[str] = field(default_factory=list)  # External requirements (e.g., 'playwright')


class ToolInterface(ABC):
    """Interface for all tools."""
    
    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """Return the tool's metadata."""
        pass

    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute the tool with the given arguments and return the result."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tool is available (dependencies installed, etc.)."""
        pass


# Capability Contract (using existing CapabilityCategory enum)
# Note: We keep capabilities as an enum for simplicity in Phase 1.
# New capabilities require adding to the enum, but this is infrequent.

# Skill Contract

@dataclass
class SkillContract:
    """A reusable skill representing a capability/workflow pattern."""
    name: str
    intent: str  # Human-readable description of what the skill accomplishes
    required_capabilities: List[str] = field(default_factory=list)  # Capability category strings
    # Workflow is a list of steps, each step being a dict with:
    #   - tool: str (tool name from ToolRegistry)
    #   - args_template: Dict[str, Any] (Jinja2 template or similar for argument substitution)
    #   - produces: List[str] (names of outputs produced by this step, to be used in later steps)
    workflow: List[Dict[str, Any]] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)  # e.g., "no_network", "windows_only"
    verification_strategy: str = field(default="standard")  # "standard", "strict", "none"
    # Optional: success_history and usage_metadata for ranking
    success_history: List[Dict[str, Any]] = field(default_factory=list)
    usage_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "intent": self.intent,
            "required_capabilities": self.required_capabilities,
            "workflow": self.workflow,
            "constraints": self.constraints,
            "verification_strategy": self.verification_strategy,
            "success_history": self.success_history,
            "usage_metadata": self.usage_metadata,
        }

    def matches_intent(self, goal: str, required_capabilities: List[str]) -> float:
        """Calculate how well this skill matches the goal (0-1)."""
        score = 0.0
        goal_lower = goal.lower()

        # Intent keyword match
        intent_words = self.intent.lower().split()
        for word in intent_words:
            if len(word) > 2 and word in goal_lower:
                score += 0.2

        # Capability match
        if required_capabilities:
            matched = sum(1 for cap in required_capabilities if cap in self.required_capabilities)
            if self.required_capabilities:
                score += 0.5 * (matched / len(self.required_capabilities))

        # Success history bonus
        if self.success_history:
            recent_success = sum(1 for s in self.success_history[-5:] if s.get("success", False))
            score += 0.3 * (recent_success / min(5, len(self.success_history)))

        return min(score, 1.0)

    def is_applicable(
        self,
        goal: str,
        available_tools: List[str],
        current_permissions: List[str],
        environment: Dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Check if skill is applicable given current constraints."""
        reasons = []

        # Check constraints
        for constraint in self.constraints:
            if constraint == "no_network" and environment.get("network_required", False):
                return False, [f"Constraint violated: {constraint}"]
            if constraint == "windows_only" and not environment.get("is_windows", False):
                return False, [f"Constraint violated: {constraint}"]

        # Check verification strategy doesn't bypass safety
        if self.verification_strategy == "none":
            reasons.append("Warning: skill has no verification strategy")

        return True, reasons


# Application Adapter Contract
# Application adapters are tools that satisfy capabilities like BROWSER, DESKTOP, GIT, etc.
# They follow the ToolInterface but are specialized for application automation.

# Security Contract
# Extension metadata must include security-relevant fields:
# - capabilities (for tools) or required_capabilities (for skills)
# - risk_level / side_effects (for tools)
# - permission_required (for tools)
# - verification_required (for tools)
# - constraints (for skills)

# Registration Model
# Extensions register themselves via explicit registry APIs:
#   provider_registry.register_provider(provider_instance)
#   tool_registry.register_tool(tool_instance)
#   skill_registry.register_skill(skill_instance)
#   tool_registry.register_tool(adapter_instance)  # for application adapters

# Backward Compatibility
# Existing Stage 31 tools should continue to operate.
# We provide a base class that adapts old-style tools to the new contract.
