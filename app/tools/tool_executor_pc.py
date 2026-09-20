from typing import Optional
from ...core.state.action import Action, SandboxSpec
from ...core.state.observation import Observation
from .base_tool import Tool
from .tool_registry import ToolRegistry
from ...modules.permission import PermissionLayer

class ToolExecutor:
    """Executes a tool action via the registry, applying permission checks."""
    def __init__(self, permission_layer: PermissionLayer):
        self.permission_layer = permission_layer

    def execute(self, action: Action) -> Observation:
        # Permission check
        if not self.permission_layer.authorize(action, action.sandbox):
            self.permission_layer.log_decision(action, False, "Permission denied")
            return Observation.permission_denied()
        self.permission_layer.log_decision(action, True, "")

        # Retrieve tool
        try:
            tool: Tool = ToolRegistry.get(action.tool_name)
        except KeyError:
            return Observation.tool_not_found()

        # Prepare sandbox/context
        context = tool.prepare(action)
        try:
            obs = tool.execute(action, context)
        finally:
            tool.cleanup(action, context)
        return obs