"""
Executable Skill & Workflow Engine - Stage 32 Phase 4

Transforms the Skill system from a descriptive mechanism into a safe,
reusable workflow layer that translates user intent into structured
multi-step execution plans.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union
from enum import Enum
from datetime import datetime
import re
import json
from copy import deepcopy

from app.extensions.contracts import SkillContract, ToolMetadata
from app.extensions.registry import (
    SkillExtensionRegistry,
    ExtensionManager,
    ExtensionType,
    DuplicateRegistrationError,
    InvalidMetadataError,
    MissingInterfaceError,
    SecurityValidationError,
)
from app.extensions.dynamic_tools import (
    DynamicToolRegistry,
    DynamicToolExecutor,
    ToolResult,
    ToolResultStatus,
)
from app.tools.capabilities import CapabilityCategory
from app.tools.registry import ToolRegistry
from app.core.planner import Planner, Plan
from app.core.task_executor import TaskExecutor
from app.memory.skills import Skill as LegacySkill, SkillRegistry as LegacySkillRegistry


# ============================================================
# Skill Execution Enums
# ============================================================

class SkillRiskLevel(Enum):
    """Risk level for skill workflows."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillVerificationStrategy(Enum):
    """Verification strategy for skills."""
    STANDARD = "standard"
    STRICT = "strict"
    NONE = "none"


class WorkflowStepType(Enum):
    """Type of workflow step."""
    TOOL_EXECUTION = "tool_execution"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    PARALLEL = "parallel"


# ============================================================
# Enhanced Skill Contract (Executable)
# ============================================================

@dataclass
class SkillParameter:
    """A skill input parameter with validation."""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None  # Allowed values
    pattern: Optional[str] = None  # Regex pattern for strings
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    
    def validate(self, value: Any) -> bool:
        """Validate a value against this parameter schema."""
        if value is None:
            if self.required:
                raise ValueError(f"Required parameter '{self.name}' is missing")
            return True
        
        # Type validation
        type_map = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_type = type_map.get(self.type)
        if expected_type and not isinstance(value, expected_type):
            raise ValueError(f"Parameter '{self.name}' must be of type {self.type}, got {type(value).__name__}")
        
        # Enum validation
        if self.enum and value not in self.enum:
            raise ValueError(f"Parameter '{self.name}' value '{value}' not in allowed values: {self.enum}")
        
        # Pattern validation for strings
        if self.pattern and isinstance(value, str):
            if not re.match(self.pattern, value):
                raise ValueError(f"Parameter '{self.name}' value '{value}' does not match pattern '{self.pattern}'")
        
        # Range validation for numbers
        if self.min_value is not None and isinstance(value, (int, float)) and value < self.min_value:
            raise ValueError(f"Parameter '{self.name}' value {value} is below minimum {self.min_value}")
        if self.max_value is not None and isinstance(value, (int, float)) and value > self.max_value:
            raise ValueError(f"Parameter '{self.name}' value {value} exceeds maximum {self.max_value}")
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "default": self.default,
            "enum": self.enum,
            "pattern": self.pattern,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillParameter":
        return cls(
            name=data["name"],
            type=data.get("type", "string"),
            description=data.get("description", ""),
            required=data.get("required", True),
            default=data.get("default"),
            enum=data.get("enum"),
            pattern=data.get("pattern"),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
        )


@dataclass
class WorkflowStep:
    """A single step in a skill workflow."""
    step_id: str
    tool: str  # Tool name (from tool registry)
    capability: Optional[str] = None  # Capability this step satisfies
    args_template: Dict[str, Any] = field(default_factory=dict)  # Template with {param} placeholders
    produces: List[str] = field(default_factory=list)  # Output names for use in later steps
    requires: List[str] = field(default_factory=list)  # Input names required from previous steps
    verification_required: bool = True
    risk_level: SkillRiskLevel = SkillRiskLevel.LOW
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "capability": self.capability,
            "args_template": self.args_template,
            "produces": self.produces,
            "requires": self.requires,
            "verification_required": self.verification_required,
            "risk_level": self.risk_level.value,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=data["step_id"],
            tool=data["tool"],
            capability=data.get("capability"),
            args_template=data.get("args_template", {}),
            produces=data.get("produces", []),
            requires=data.get("requires", []),
            verification_required=data.get("verification_required", True),
            risk_level=SkillRiskLevel(data.get("risk_level", "low")),
            description=data.get("description", ""),
        )


@dataclass
class ExecutableSkillContract:
    """
    Enhanced executable skill contract with parameter validation and workflow.
    
    Separates skill DESCRIPTION from skill EXECUTION PLAN.
    No arbitrary code execution allowed in skill definitions.
    """
    skill_id: str
    name: str
    intent: str  # Human-readable description
    version: str = "1.0.0"
    description: str = ""
    
    # Input parameters
    parameters: List[SkillParameter] = field(default_factory=list)
    
    # Required capabilities
    required_capabilities: List[str] = field(default_factory=list)
    
    # Workflow definition (declarative, no code)
    workflow: List[WorkflowStep] = field(default_factory=list)
    
    # Constraints and metadata
    constraints: List[str] = field(default_factory=list)
    verification_strategy: SkillVerificationStrategy = SkillVerificationStrategy.STANDARD
    risk_level: SkillRiskLevel = SkillRiskLevel.LOW
    
    # History and metadata (for ranking/selection)
    success_history: List[Dict[str, Any]] = field(default_factory=list)
    usage_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Registration metadata
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    registered_by: str = "system"
    
    def get_parameter(self, name: str) -> Optional[SkillParameter]:
        """Get parameter by name."""
        for p in self.parameters:
            if p.name == name:
                return p
        return None
    
    def validate_parameters(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fill in defaults for skill inputs."""
        validated = {}
        
        # Check required parameters and apply defaults
        for param in self.parameters:
            if param.name in inputs:
                param.validate(inputs[param.name])
                validated[param.name] = inputs[param.name]
            elif param.required:
                if param.default is not None:
                    validated[param.name] = param.default
                else:
                    raise ValueError(f"Required parameter '{param.name}' is missing")
            elif param.default is not None:
                validated[param.name] = param.default
        
        # Check for unknown parameters
        known_params = {p.name for p in self.parameters}
        unknown = set(inputs.keys()) - known_params
        if unknown:
            raise ValueError(f"Unknown parameters: {unknown}")
        
        return validated
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "intent": self.intent,
            "version": self.version,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "required_capabilities": self.required_capabilities,
            "workflow": [w.to_dict() for w in self.workflow],
            "constraints": self.constraints,
            "verification_strategy": self.verification_strategy.value,
            "risk_level": self.risk_level.value,
            "success_history": self.success_history,
            "usage_metadata": self.usage_metadata,
            "registered_at": self.registered_at,
            "registered_by": self.registered_by,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutableSkillContract":
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            intent=data["intent"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            parameters=[SkillParameter.from_dict(p) for p in data.get("parameters", [])],
            required_capabilities=data.get("required_capabilities", []),
            workflow=[WorkflowStep.from_dict(w) for w in data.get("workflow", [])],
            constraints=data.get("constraints", []),
            verification_strategy=SkillVerificationStrategy(data.get("verification_strategy", "standard")),
            risk_level=SkillRiskLevel(data.get("risk_level", "low")),
            success_history=data.get("success_history", []),
            usage_metadata=data.get("usage_metadata", {}),
            registered_at=data.get("registered_at", datetime.utcnow().isoformat()),
            registered_by=data.get("registered_by", "system"),
        )


# ============================================================
# Template Substitution (Safe, No Eval)
# ============================================================

class TemplateSubstitutionError(Exception):
    """Error during template substitution."""
    pass


class SafeTemplateEngine:
    """
    Safe template substitution engine.
    
    Only supports explicit {parameter_name} substitutions.
    No eval(), no expressions, no function calls.
    """
    
    # Pattern: {param_name} where param_name is alphanumeric + underscore
    PLACEHOLDER_PATTERN = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
    
    @classmethod
    def substitute(cls, template: Any, parameters: Dict[str, Any], 
                   step_outputs: Dict[str, Any] = None) -> Any:
        """
        Safely substitute placeholders in a template.
        
        Supports:
        - String values with {param} placeholders
        - Nested dicts and lists
        - References to skill parameters and step outputs
        
        Args:
            template: Template value (string, dict, list, or primitive)
            parameters: Skill input parameters
            step_outputs: Outputs from previous workflow steps
            
        Returns:
            Template with all placeholders resolved
        """
        # Combine parameters and step outputs
        context = {}
        if parameters:
            context.update(parameters)
        if step_outputs:
            context.update(step_outputs)
        
        return cls._substitute_recursive(template, context)
    
    @classmethod
    def _substitute_recursive(cls, value: Any, context: Dict[str, Any]) -> Any:
        """Recursively substitute placeholders in any value."""
        if isinstance(value, str):
            return cls._substitute_string(value, context)
        elif isinstance(value, dict):
            return {k: cls._substitute_recursive(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [cls._substitute_recursive(item, context) for item in value]
        else:
            return value
    
    @classmethod
    def _substitute_string(cls, template: str, context: Dict[str, Any]) -> str:
        """Substitute placeholders in a string."""
        
        def replace_placeholder(match):
            param_name = match.group(1)
            if param_name not in context:
                raise TemplateSubstitutionError(
                    f"Unknown template parameter: '{param_name}'. "
                    f"Available: {list(context.keys())}"
                )
            value = context[param_name]
            # Convert to string representation
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)
        
        return cls.PLACEHOLDER_PATTERN.sub(replace_placeholder, template)
    
    @classmethod
    def extract_placeholders(cls, template: Any) -> Set[str]:
        """Extract all placeholder names from a template."""
        placeholders = set()
        
        if isinstance(template, str):
            placeholders.update(cls.PLACEHOLDER_PATTERN.findall(template))
        elif isinstance(template, dict):
            for v in template.values():
                placeholders.update(cls.extract_placeholders(v))
        elif isinstance(template, list):
            for item in template:
                placeholders.update(cls.extract_placeholders(item))
        
        return placeholders


# ============================================================
# Workflow Expansion
# ============================================================

class SkillWorkflowExpander:
    """
    Expands a skill into an execution-ready plan.
    
    Responsibilities:
    - Validate skill inputs
    - Resolve templates
    - Create structured workflow steps
    - Infer dependencies
    - Validate capabilities
    - Produce Plan/PlanStep representation
    """
    
    def __init__(
        self,
        dynamic_tool_registry: DynamicToolRegistry,
        capability_registry: Any = None,
    ):
        self.tool_registry = dynamic_tool_registry
        self.capability_registry = capability_registry
    
    def expand(
        self,
        skill: ExecutableSkillContract,
        inputs: Dict[str, Any],
    ) -> List[Plan]:
        """
        Expand a skill into a list of Plans ready for execution.
        
        Args:
            skill: The skill contract to expand
            inputs: Skill input parameters
            
        Returns:
            List of Plan objects ready for TaskExecutor
            
        Raises:
            ValueError: If validation fails
            TemplateSubstitutionError: If template resolution fails
        """
        # 1. Validate skill inputs
        validated_inputs = skill.validate_parameters(inputs)
        
        # 2. Validate workflow structure
        self._validate_workflow(skill)
        
        # 3. Check tool availability for each step
        self._validate_tool_availability(skill)
        
        # 4. Expand workflow steps into Plans
        plans = []
        step_outputs = {}
        produced_outputs = set()
        
        for step in skill.workflow:
            # Build context with skill parameters and previously produced outputs
            # (but not future outputs - we track what's been produced so far)
            context = dict(validated_inputs)
            context.update({k: v for k, v in step_outputs.items() if v is not None})
            
            # Resolve args template with skill parameters and previously produced step outputs
            # Allow placeholders for outputs that will be produced by future steps
            # We extract placeholders first to check if they're known
            placeholders = SafeTemplateEngine.extract_placeholders(step.args_template)
            
            # Separate known vs unknown placeholders
            unknown_placeholders = placeholders - set(context.keys()) - produced_outputs
            if unknown_placeholders:
                raise TemplateSubstitutionError(
                    f"Step '{step.step_id}' references unknown parameters: {unknown_placeholders}. "
                    f"Available: {list(context.keys()) + list(produced_outputs)}"
                )
            
            # Resolve with context (will include None for future outputs - that's OK for validation)
            # We don't actually resolve at expansion time; we just validate structure
            # For argument validation, we use a dummy value for future outputs
            validation_context = dict(context)
            for ph in placeholders - set(context.keys()):
                validation_context[ph] = f"{{placeholder_{ph}}}"  # Dummy value for validation
            
            resolved_args = SafeTemplateEngine.substitute(
                step.args_template,
                validation_context,
                {}  # step_outputs already in validation_context
            )
            
            # Validate tool arguments
            tool_metadata = self.tool_registry.get_metadata(step.tool)
            if tool_metadata:
                try:
                    self.tool_registry.validate_arguments(step.tool, resolved_args)
                except Exception as e:
                    raise ValueError(f"Step '{step.step_id}' argument validation failed: {e}")
            
            # Create Plan for this step
            plan = Plan(
                action="use_tool",
                tool_name=step.tool,
                arguments=resolved_args,
                reason=f"Skill '{skill.name}' step '{step.step_id}': {step.description or step.tool}",
            )
            
            plans.append(plan)
            
            # Track outputs for next steps
            # The actual output values will be resolved at execution time
            for output in step.produces:
                step_outputs[output] = None  # Will be filled during execution
                produced_outputs.add(output)
        
        return plans
    
    def _validate_workflow(self, skill: ExecutableSkillContract) -> None:
        """Validate workflow structure."""
        if not skill.workflow:
            raise ValueError("Skill workflow cannot be empty")
        
        step_ids = set()
        produced_outputs = set()
        
        for i, step in enumerate(skill.workflow):
            # Check for duplicate step IDs
            if step.step_id in step_ids:
                raise ValueError(f"Duplicate step ID: {step.step_id}")
            step_ids.add(step.step_id)
            
            # Check that 'tool' is specified
            if not step.tool:
                raise ValueError(f"Step {i} must specify a tool")
            
            # Check that 'requires' references previously produced outputs
            for req in step.requires:
                if req not in produced_outputs:
                    raise ValueError(
                        f"Step '{step.step_id}' requires output '{req}' "
                        f"which was not produced by any previous step"
                    )
            
            # Track produced outputs
            for output in step.produces:
                produced_outputs.add(output)
            
            # Check for circular references in args_template
            placeholders = SafeTemplateEngine.extract_placeholders(step.args_template)
            for placeholder in placeholders:
                if placeholder in produced_outputs and placeholder not in step.requires:
                    raise ValueError(
                        f"Step '{step.step_id}' references output '{placeholder}' "
                        f"but doesn't declare it in 'requires'"
                    )
    
    def _validate_tool_availability(self, skill: ExecutableSkillContract) -> None:
        """Check that all tools in workflow are available."""
        for step in skill.workflow:
            tool = self.tool_registry.get_tool(step.tool)
            if not tool:
                raise ValueError(f"Tool '{step.tool}' not registered")
            
            if not tool.is_available():
                raise ValueError(f"Tool '{step.tool}' is not available")
            
            # Check capability if specified
            if step.capability:
                metadata = self.tool_registry.get_metadata(step.tool)
                if metadata and metadata.capability != step.capability:
                    raise ValueError(
                        f"Tool '{step.tool}' capability '{metadata.capability}' "
                        f"doesn't match required capability '{step.capability}'"
                    )


# ============================================================
# Skill Registry (Integrated with ExtensionRegistry)
# ============================================================

class ExecutableSkillRegistry:
    """
    Registry for executable skills with validation and discovery.
    
    Integrates with Stage 32 ExtensionRegistry.
    """
    
    def __init__(self, extension_manager: ExtensionManager = None):
        self._skill_registry = SkillExtensionRegistry()
        self._extension_manager = extension_manager
        # Store full ExecutableSkillContract for parameter retrieval
        self._executable_skills: Dict[str, ExecutableSkillContract] = {}
    
    def register(self, skill: ExecutableSkillContract) -> None:
        """Register an executable skill with full validation."""
        # Convert to SkillContract for base registry
        base_contract = self._to_base_contract(skill)
        
        # Validate before registration
        self._validate_skill(skill)
        
        # Register in extension registry
        self._skill_registry.register(base_contract)
        
        # Store full executable skill
        self._executable_skills[skill.skill_id] = skill
        
        # Emit monitoring event
        self._emit_skill_registered(skill)
    
    def _to_base_contract(self, skill: ExecutableSkillContract) -> SkillContract:
        """Convert to base SkillContract for registry."""
        return SkillContract(
            name=skill.skill_id,
            intent=skill.intent,
            required_capabilities=skill.required_capabilities,
            workflow=[w.to_dict() for w in skill.workflow],
            constraints=skill.constraints,
            verification_strategy=skill.verification_strategy.value,
            success_history=skill.success_history,
            usage_metadata=skill.usage_metadata,
        )
    
    def _validate_skill(self, skill: ExecutableSkillContract) -> None:
        """Validate skill contract."""
        if not skill.skill_id:
            raise InvalidMetadataError("Skill must have a non-empty skill_id")
        
        if not skill.name:
            raise InvalidMetadataError("Skill must have a non-empty name")
        
        if not skill.intent:
            raise InvalidMetadataError("Skill must have a non-empty intent")
        
        # Validate parameters
        param_names = set()
        for param in skill.parameters:
            if param.name in param_names:
                raise InvalidMetadataError(f"Duplicate parameter name: {param.name}")
            param_names.add(param.name)
        
        # Validate workflow
        if not skill.workflow:
            raise InvalidMetadataError("Skill must have at least one workflow step")
        
        step_ids = set()
        produced = set()
        for step in skill.workflow:
            if step.step_id in step_ids:
                raise InvalidMetadataError(f"Duplicate step ID: {step.step_id}")
            step_ids.add(step.step_id)
            
            if not step.tool:
                raise InvalidMetadataError(f"Step '{step.step_id}' must specify a tool")
            
            for req in step.requires:
                if req not in produced:
                    raise InvalidMetadataError(
                        f"Step '{step.step_id}' requires '{req}' not produced by previous steps"
                    )
            
            for output in step.produces:
                produced.add(output)
        
        # Validate verification strategy
        valid_strategies = {s.value for s in SkillVerificationStrategy}
        if skill.verification_strategy.value not in valid_strategies:
            raise InvalidMetadataError(f"Invalid verification_strategy: {skill.verification_strategy.value}")
        
        # Validate risk level
        valid_risks = {r.value for r in SkillRiskLevel}
        if skill.risk_level.value not in valid_risks:
            raise InvalidMetadataError(f"Invalid risk_level: {skill.risk_level.value}")
    
    def unregister(self, skill_id: str) -> bool:
        """Unregister a skill."""
        # Note: SkillExtensionRegistry uses name as key, which is skill_id in our case
        result = self._skill_registry.unregister(skill_id)
        if skill_id in self._executable_skills:
            del self._executable_skills[skill_id]
        return result
    
    def get(self, skill_id: str) -> Optional[ExecutableSkillContract]:
        """Get a skill by ID."""
        # Return the full executable skill from our storage
        return self._executable_skills.get(skill_id)
    
    def list(self) -> List[Dict[str, Any]]:
        """List all registered skills."""
        return self._skill_registry.list()
    
    def find_relevant(
        self,
        goal: str,
        required_capabilities: List[str],
        available_tools: List[str],
        current_permissions: List[str],
        environment: Dict[str, Any],
    ) -> List[ExecutableSkillContract]:
        """Find skills relevant to the goal."""
        base_skills = self._skill_registry.find_relevant(
            goal, required_capabilities, available_tools, current_permissions, environment
        )
        return [self._executable_skills.get(s.name) for s in base_skills if s.name in self._executable_skills]
    
    def contains(self, skill_id: str) -> bool:
        return skill_id in self._executable_skills
    
    def clear(self) -> None:
        self._skill_registry.clear()
        self._executable_skills.clear()
    
    def _emit_skill_registered(self, skill: ExecutableSkillContract) -> None:
        """Emit monitoring event."""
        try:
            from app.monitoring.emitter import emit_skill_event
            emit_skill_event("skill.registered", skill.skill_id, {
                "intent": skill.intent,
                "risk_level": skill.risk_level.value,
                "version": skill.version,
            })
        except ImportError:
            pass


# ============================================================
# Skill Executor
# ============================================================

class SkillExecutor:
    """
    Executes skills through the existing TaskExecutor pipeline.
    
    Pipeline:
    intent → skill selected → skill parameters extracted → workflow expanded
    → capability planner validates/ranks tools → final plan → TaskExecutor
    """
    
    def __init__(
        self,
        skill_registry: ExecutableSkillRegistry,
        dynamic_tool_registry: DynamicToolRegistry,
        dynamic_tool_executor: DynamicToolExecutor,
        planner: Planner,
        task_executor: TaskExecutor = None,
        permission_manager: Any = None,
    ):
        self.skill_registry = skill_registry
        self.tool_registry = dynamic_tool_registry
        self.tool_executor = dynamic_tool_executor
        self.planner = planner
        self.task_executor = task_executor
        self.permission_manager = permission_manager
        self.workflow_expander = SkillWorkflowExpander(dynamic_tool_registry)
    
    def execute_skill(
        self,
        skill_id: str,
        inputs: Dict[str, Any],
        task_id: str = "",
        permission_mode: str = "BALANCED",
    ) -> ToolResult:
        """
        Execute a skill end-to-end.
        
        Args:
            skill_id: ID of the skill to execute
            inputs: Skill input parameters
            task_id: Task ID for monitoring
            permission_mode: SAFE, BALANCED, or FULL_AUTO
            
        Returns:
            ToolResult with final outcome
        """
        # 1. Get skill
        skill = self.skill_registry.get(skill_id)
        if not skill:
            return ToolResult.failure(
                f"Skill not found: {skill_id}",
                tool_name=skill_id,
                capability="skill",
            )
        
        # 2. Validate inputs
        try:
            validated_inputs = skill.validate_parameters(inputs)
        except ValueError as e:
            return ToolResult.validation_error(str(e), tool_name=skill_id, capability="skill")
        
        # 3. Emit selection event
        self._emit_event("skill.selected", skill_id, {
            "inputs": validated_inputs,
        }, task_id)
        
        # 4. Expand workflow
        try:
            plans = self.workflow_expander.expand(skill, validated_inputs)
        except (ValueError, TemplateSubstitutionError) as e:
            self._emit_event("skill.workflow_rejected", skill_id, {
                "error": str(e),
            }, task_id)
            return ToolResult.failure(
                f"Workflow expansion failed: {e}",
                tool_name=skill_id,
                capability="skill",
            )
        
        self._emit_event("skill.workflow_expanded", skill_id, {
            "num_steps": len(plans),
        }, task_id)
        
        # 5. Execute each step through tool executor
        all_results = []
        step_outputs = {}
        
        for i, plan in enumerate(plans):
            step = skill.workflow[i]
            step_task_id = f"{task_id}_step_{i}" if task_id else f"skill_{skill_id}_step_{i}"
            
            self._emit_event("skill.step_started", skill_id, {
                "step": step.step_id,
                "tool": step.tool,
            }, step_task_id)
            
            # Resolve args template with actual outputs from previous steps
            resolved_args = SafeTemplateEngine.substitute(
                step.args_template,
                validated_inputs,
                {k: v for k, v in step_outputs.items() if v is not None}
            )
            
            # Execute tool with resolved arguments
            result = self.tool_executor.execute(
                plan.tool_name,
                resolved_args,
                task_id=step_task_id,
                step_id=step.step_id,
                permission_mode=permission_mode,
            )
            
            all_results.append(result)
            
            if not result.is_success():
                self._emit_event("skill.step_failed", skill_id, {
                    "step": step.step_id,
                    "error": result.error,
                }, step_task_id)
                
                # On failure, return failure
                return ToolResult.failure(
                    f"Skill '{skill_id}' step '{step.step_id}' failed: {result.error}",
                    tool_name=skill_id,
                    capability="skill",
                    metadata={"step_results": [r.to_dict() for r in all_results]},
                )
            
            # Capture outputs for next steps
            for output in step.produces:
                step_outputs[output] = result.output
            
            self._emit_event("skill.step_completed", skill_id, {
                "step": step.step_id,
                "tool": step.tool,
            }, step_task_id)
        
        # 6. Verify if required
        if skill.verification_strategy != SkillVerificationStrategy.NONE:
            verification_result = self._verify_skill_output(skill, all_results, step_outputs)
            if not verification_result:
                return ToolResult.failure(
                    f"Skill '{skill_id}' verification failed",
                    tool_name=skill_id,
                    capability="skill",
                )
        
        # 7. Record success
        self._emit_event("skill.execution_completed", skill_id, {
            "num_steps": len(plans),
            "duration_ms": sum(r.execution_duration_ms or 0 for r in all_results),
        }, task_id)
        
        # Return final result
        final_output = all_results[-1].output if all_results else None
        return ToolResult.success(
            output=final_output,
            tool_name=skill_id,
            capability="skill",
            metadata={
                "step_results": [r.to_dict() for r in all_results],
                "step_outputs": step_outputs,
            },
            verification_info={"verified": True},
        )
    
    def _verify_skill_output(
        self,
        skill: ExecutableSkillContract,
        step_results: List[ToolResult],
        step_outputs: Dict[str, Any],
    ) -> bool:
        """Verify skill execution based on strategy."""
        if skill.verification_strategy == SkillVerificationStrategy.NONE:
            return True
        
        if skill.verification_strategy == SkillVerificationStrategy.STRICT:
            # All steps must have succeeded and have verification info
            return all(r.verification_info is not None for r in step_results)
        
        # Standard: at least final step has verification
        return step_results[-1].verification_info is not None if step_results else False
    
    def _emit_event(self, event_type: str, skill_id: str, data: Dict[str, Any], task_id: str) -> None:
        """Emit monitoring event."""
        try:
            from app.monitoring.emitter import emit_skill_event
            emit_skill_event(event_type, skill_id, {
                **data,
                "task_id": task_id,
                "skill_version": self.skill_registry.get(skill_id).version if self.skill_registry.get(skill_id) else "unknown",
            })
        except ImportError:
            pass


# ============================================================
# Migration Helpers
# ============================================================

def migrate_legacy_skill(legacy_skill: LegacySkill) -> ExecutableSkillContract:
    """
    Migrate a Stage 31 Skill to ExecutableSkillContract.
    
    Preserves behavior while adding executable structure.
    """
    parameters = []
    
    # Extract parameters from workflow templates
    for step in legacy_skill.workflow:
        args_template = step.get("args_template", {})
        for key, value in args_template.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                param_name = value[1:-1]
                if not any(p.name == param_name for p in parameters):
                    parameters.append(SkillParameter(
                        name=param_name,
                        type="string",
                        description=f"Input for {legacy_skill.name}",
                        required=True,
                    ))
    
    # Convert workflow steps
    workflow_steps = []
    for i, step in enumerate(legacy_skill.workflow):
        workflow_steps.append(WorkflowStep(
            step_id=f"step_{i}",
            tool=step.get("tool", ""),
            args_template=step.get("args_template", {}),
            produces=step.get("produces", []),
            verification_required=legacy_skill.verification_strategy != "none",
            risk_level=SkillRiskLevel.LOW if legacy_skill.verification_strategy != "strict" else SkillRiskLevel.MEDIUM,
        ))
    
    return ExecutableSkillContract(
        skill_id=legacy_skill.name,
        name=legacy_skill.name,
        intent=legacy_skill.intent,
        version="1.0.0",
        parameters=parameters,
        required_capabilities=[c.value for c in legacy_skill.required_capabilities],
        workflow=workflow_steps,
        constraints=legacy_skill.constraints,
        verification_strategy=SkillVerificationStrategy(legacy_skill.verification_strategy),
        risk_level=SkillRiskLevel.LOW if legacy_skill.verification_strategy != "strict" else SkillRiskLevel.MEDIUM,
        success_history=legacy_skill.success_history,
        usage_metadata=legacy_skill.usage_metadata,
    )


def migrate_all_builtin_skills(legacy_registry: LegacySkillRegistry) -> List[ExecutableSkillContract]:
    """Migrate all built-in skills."""
    skills = []
    for legacy_skill in legacy_registry.skills.values():
        skills.append(migrate_legacy_skill(legacy_skill))
    return skills


# ============================================================
# Integration with ExtensionManager
# ============================================================

def create_skill_extension_manager(
    dynamic_tool_registry: DynamicToolRegistry = None,
    dynamic_tool_executor: DynamicToolExecutor = None,
    planner: Planner = None,
    task_executor: TaskExecutor = None,
    permission_manager: Any = None,
) -> ExtensionManager:
    """
    Create an ExtensionManager with executable skill support.
    
    This is the main integration point for Phase 4.
    """
    manager = ExtensionManager()
    
    # Create executable skill registry
    skill_registry = ExecutableSkillRegistry(manager)
    manager.skills = skill_registry  # Replace base registry
    
    # Migrate built-in skills
    from app.memory.skills import BUILTIN_SKILLS as legacy_skills
    for legacy_skill in legacy_skills.values():
        executable_skill = migrate_legacy_skill(legacy_skill)
        skill_registry.register(executable_skill)
    
    return manager


# ============================================================
# Re-exports
# ============================================================

__all__ = [
    "SkillRiskLevel",
    "SkillVerificationStrategy",
    "WorkflowStepType",
    "SkillParameter",
    "WorkflowStep",
    "ExecutableSkillContract",
    "SafeTemplateEngine",
    "TemplateSubstitutionError",
    "SkillWorkflowExpander",
    "ExecutableSkillRegistry",
    "SkillExecutor",
    "migrate_legacy_skill",
    "migrate_all_builtin_skills",
    "create_skill_extension_manager",
]