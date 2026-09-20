from typing import Optional, Callable
from app.core.agent_loop import AgentLoop
from app.core.planner import Planner
from app.core.router import SmartRouter
from app.memory.enhanced import EnhancedMemory
from app.tools.calculator import CalculatorTool
from app.tools.time_tool import TimeTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.core.evaluator import Evaluator
from app.core.evaluation import Evaluation
from app.core.permissions import PermissionManager

# Import new adapter tools
from app.tools.adapters import (
    FSReadTool,
    FSWriteTool,
    FSMoveTool,
    FSListTool,
    TerminalRunTool,
)


class Agent:
    """AI agent with memory, planning, routing, and tool execution."""

    def __init__(self, max_memory_messages: int = 10, permission_callback: Optional[Callable[[str, str, dict], bool]] = None):
        self.router = SmartRouter()
        self.memory = EnhancedMemory(
            max_messages=max_memory_messages
        )
        self.permission_manager = PermissionManager()

        self.tool_registry = ToolRegistry()
        
        # Register original tools
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(TimeTool())
        
        # Register new filesystem tools
        self.tool_registry.register(FSReadTool())
        self.tool_registry.register(FSWriteTool())
        self.tool_registry.register(FSMoveTool())
        self.tool_registry.register(FSListTool())
        
        # Register terminal tool
        self.tool_registry.register(TerminalRunTool())
        
        # Create tool_executor
        self.tool_executor = ToolExecutor(self.tool_registry)

        self.planner = Planner()
        self.evaluator = Evaluator()
        self.agent_loop = AgentLoop(
            self.planner,
            self.tool_executor,
            evaluator=self.evaluator,
            evaluation_callback=self.memory.add_evaluation,
            memory=self.memory,
            permission_manager=self.permission_manager,
            permission_callback=permission_callback,
        )

    def set_permission_callback(self, callback: Optional[Callable[[str, str, dict], bool]]):
        """Set or update the permission callback used to request user approval."""
        self.agent_loop.permission_callback = callback

    def _create_reflection(self, tool_name: str, result) -> str:
        """Create a reflection evaluating a tool execution."""
        return f"Executed {tool_name} and got result: {result}."

    def run(self, message: str) -> str:
        """Process a user request."""
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        message = message.strip()

        if not message:
            raise ValueError("message cannot be empty")

        context = self.memory.build_context(message)

        self.memory.add_user_message(message)

        response = self.agent_loop.run(
            message,
            available_tools=self._available_tool_metadata(),
            responder=lambda observations: self._create_response(
                message,
                context,
                observations,
            ),
            reflection_callback=lambda tool_name, result: self.memory.add_reflection(
                self._create_reflection(tool_name, result)
            ),
            context=context,
        )

        self.memory.add_agent_message(response)

        return response

    def _available_tool_metadata(self) -> list[dict]:
        """Return registry metadata for the planner's constrained choices."""
        return self.tool_registry.list_tools()

    def _create_response(self, message: str, context: str, observations: list) -> str:
        """Return a deterministic tool result or ask the model directly."""
        if observations:
            last_obs = observations[-1]
            self.memory.add_tool_observation(last_obs.tool_name, last_obs.result)
            return str(last_obs.result)

        return self.router.ask(
            message,
            model_message=context,
        )

    def get_memory(self) -> list[dict]:
        """Return the current conversation history."""
        return self.memory.get_messages()

    def clear_memory(self) -> None:
        """Clear the current conversation history."""
        self.memory.clear()

    def list_tools(self) -> list[dict]:
        """Return the tools currently available to the agent."""
        return self.tool_registry.list_tools()