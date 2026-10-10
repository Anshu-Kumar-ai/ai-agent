from collections.abc import Callable

from app.core.agent_loop import AgentLoop
from app.core.evaluator import Evaluator
from app.core.gateway import ModelGateway
from app.core.omniroute import OmniRoute
from app.core.permissions import PermissionManager
from app.core.planner import LLMPlanner, Planner
from app.core.providers import get_provider_manager
from app.core.task_executor import TaskExecutor, create_task_executor
from app.memory.enhanced import EnhancedMemory
from app.tools.adapters import (
    FSListTool,
    FSMoveTool,
    FSReadTool,
    FSWriteTool,
    TerminalRunTool,
)
from app.tools.advanced_browser_agent import create_browser_agent_tools
from app.tools.calculator import CalculatorTool
from app.tools.desktop_tools import create_desktop_tools
from app.tools.executor import ToolExecutor
from app.tools.multi_agent import MultiAgentTool, create_orchestrator
from app.tools.python_exec import create_python_exec_tool
from app.tools.rag_tools import create_rag_tools
from app.tools.registry import ToolRegistry
from app.tools.time_tool import TimeTool
from app.tools.web_tools import HTTPFetchTool, WebSearchTool


class Agent:
    """AI agent with memory, planning, routing, and tool execution."""

    def __init__(
        self,
        max_memory_messages: int = 10,
        permission_callback: Callable[[str, str, dict], bool] | None = None,
        planner: Planner | LLMPlanner | None = None,
    ):
        self.memory = EnhancedMemory(
            max_messages=max_memory_messages
        )
        self.permission_manager = PermissionManager()
        self.provider_manager = get_provider_manager()

        self.tool_registry = ToolRegistry()

        # Register original tools
        self.tool_registry.register(CalculatorTool())
        self.tool_registry.register(TimeTool())

        # Register filesystem tools
        self.tool_registry.register(FSReadTool())
        self.tool_registry.register(FSWriteTool())
        self.tool_registry.register(FSMoveTool())
        self.tool_registry.register(FSListTool())

        # Register terminal tool
        self.tool_registry.register(TerminalRunTool())

        # Register web tools
        self.tool_registry.register(HTTPFetchTool())
        self.tool_registry.register(WebSearchTool())

        # Register python execution tool (HIGH risk - code execution)
        self.tool_registry.register(create_python_exec_tool())

        # Register advanced browser agent tools (HIGH risk - browser automation)
        for tool in create_browser_agent_tools():
            self.tool_registry.register(tool)

        # Register desktop automation tools (HIGH risk - desktop control)
        for tool in create_desktop_tools():
            self.tool_registry.register(tool)

        # Register RAG tools (MEDIUM risk - knowledge retrieval)
        for tool in create_rag_tools():
            self.tool_registry.register(tool)

        # Register multi-agent orchestrator tool (HIGH risk - agent coordination)
        self.orchestrator = create_orchestrator(self, self.permission_manager)
        self.tool_registry.register(MultiAgentTool(self.orchestrator))

        # Create tool_executor
        self.tool_executor = ToolExecutor(self.tool_registry)

        # Set up model gateway and omniroute for intelligent provider selection
        self.model_gateway = ModelGateway(self.provider_manager)
        # Pass the gateway itself so OmniRoute can lazy-load models on demand
        self.omniroute = OmniRoute(self.provider_manager, self.model_gateway)

        # Use injected planner, or default to LLMPlanner with OmniRoute
        if planner is not None:
            self.planner = planner
        else:
            self.planner = LLMPlanner(self.omniroute, fallback_gateway=self.model_gateway)

        self.evaluator = Evaluator()

        # Create task executor for autonomous multi-step execution
        self.task_executor = create_task_executor(
            planner=self.planner,
            tool_executor=self.tool_executor,
            evaluator=self.evaluator,
            memory=self.memory,
            max_steps=10,
            max_retries_per_step=2,
            max_replans=3,
            max_task_duration_seconds=300,
            permission_manager=self.permission_manager,
            permission_callback=permission_callback,
        )

        # Keep agent_loop for backward compatibility (single-message processing)
        self.agent_loop = AgentLoop(
            self.planner,
            self.tool_executor,
            evaluator=self.evaluator,
            evaluation_callback=self.memory.add_evaluation,
            memory=self.memory,
            permission_manager=self.permission_manager,
            permission_callback=permission_callback,
        )

    def set_permission_callback(self, callback: Callable[[str, str, dict], bool] | None):
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
        """Return a deterministic tool result or ask the model directly via OmniRoute."""
        if observations:
            last_obs = observations[-1]
            self.memory.add_tool_observation(last_obs.tool_name, last_obs.result)
            return str(last_obs.result)
        # No tool observations, generate a direct response using the LLM via OmniRoute
        try:
            # Use omniroute to select a provider (non-local) and ask
            provider_type = self.omniroute.select_provider(message=message)
            response = self.omniroute.ask(provider_type, message)
            return response
        except RuntimeError as e:
            # If no remote providers available, fall back to local model via gateway
            try:
                return self.model_gateway.ask("local", message)
            except Exception:
                # If local also fails, return error
                return f"Error: {e}"

    def get_memory(self) -> list[dict]:
        """Return the current conversation history."""
        return self.memory.get_messages()

    def clear_memory(self) -> None:
        """Clear the current conversation history."""
        self.memory.clear()

    def list_tools(self) -> list[dict]:
        """Return the tools currently available to the agent."""
        return self.tool_registry.list_tools()

    def run_task(self, user_goal: str) -> str:
        """Execute a multi-step autonomous task using the task executor.

        This is the new Stage 29 entry point for complex goals.
        Returns the final result or error message.
        """
        if not isinstance(user_goal, str):
            raise TypeError("user_goal must be a string")
        user_goal = user_goal.strip()
        if not user_goal:
            raise ValueError("user_goal cannot be empty")

        # Create and execute task
        task = self.task_executor.create_task(user_goal)
        available_tools = self._available_tool_metadata()

        executed_task = self.task_executor.execute_task(
            task=task,
            available_tools=available_tools,
            responder=lambda observations: self._create_response(
                user_goal,
                self.memory.build_context(user_goal),
                observations,
            ),
            reflection_callback=lambda tool_name, result: self.memory.add_reflection(
                f"Executed {tool_name} and got result: {result}."
            ),
        )

        if executed_task.status.name == "COMPLETED":
            return str(executed_task.final_result)
        elif executed_task.status.name == "FAILED":
            return f"Task failed: {executed_task.error}"
        elif executed_task.status.name == "CANCELLED":
            return "Task was cancelled"
        else:
            return f"Task ended in unexpected state: {executed_task.status.value}"

    def get_task_status(self, task_id: str) -> dict | None:
        """Get the status of a task by ID."""
        task = self.task_executor.get_task(task_id)
        if task:
            return task.to_dict()
        return None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task by ID."""
        return self.task_executor.cancel_task(task_id)