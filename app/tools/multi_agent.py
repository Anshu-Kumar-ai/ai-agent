"""Multi-Agent Orchestration for Stage 17 - Multi-Agent Coordination.

Provides:
- Agent registry for managing multiple specialized agents
- Task decomposition and delegation
- Inter-agent communication
- Result aggregation and synthesis
- Agent lifecycle management
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.permissions import ApprovalMode, PermissionManager
from app.tools.base import BaseTool
from app.core.state.observation import Observation


class AgentRole(Enum):
    """Predefined agent roles for specialization."""
    GENERAL = "general"
    RESEARCHER = "researcher"
    CODER = "coder"
    ANALYST = "analyst"
    WRITER = "writer"
    REVIEWER = "reviewer"
    PLANNER = "planner"
    EXECUTOR = "executor"


class TaskStatus(Enum):
    """Status of a delegated task."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DelegatedTask:
    """A task delegated to a sub-agent."""
    id: str
    description: str
    assigned_agent: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    dependencies: list[str] = field(default_factory=list)  # Task IDs this depends on
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSpec:
    """Specification for a sub-agent."""
    name: str
    role: AgentRole
    description: str
    tools: list[str] = field(default_factory=list)  # Tool names this agent can use
    system_prompt: str = ""
    max_steps: int = 10
    approval_mode: ApprovalMode = ApprovalMode.BALANCED


class SubAgent:
    """A specialized sub-agent that can be delegated tasks."""

    def __init__(
        self,
        spec: AgentSpec,
        parent_agent: "Agent",
        permission_manager: PermissionManager
    ):
        self.spec = spec
        self.parent_agent = parent_agent
        self.permission_manager = permission_manager
        self._agent = None  # Lazy initialization

        # Add system prompt
        self.system_prompt = self._build_system_prompt()

    def _get_agent(self) -> "Agent":
        """Get or create the agent instance (lazy initialization)."""
        if self._agent is None:
            from app.core.agent import Agent
            self._agent = Agent(
                permission_callback=None  # Sub-agents don't prompt for approval
            )
            self._agent.permission_manager.approval_mode = self.spec.approval_mode
        return self._agent

    def _build_system_prompt(self) -> str:
        """Build the system prompt for this sub-agent."""
        base = f"""You are a specialized agent with the role: {self.spec.role.value}
        
Description: {self.spec.description}

{f"Additional instructions: {self.spec.system_prompt}" if self.spec.system_prompt else ""}

You are working as part of a multi-agent system. Complete your assigned tasks thoroughly and return clear results."""
        return base

    def run(self, task_description: str) -> Any:
        """Execute a task and return the result."""
        # Combine system prompt with task
        full_message = f"{self.system_prompt}\n\nTask: {task_description}"
        return self._get_agent().run(full_message)


class MultiAgentOrchestrator:
    """Orchestrates multiple sub-agents for complex task execution."""

    def __init__(
        self,
        main_agent: "Agent",
        permission_manager: PermissionManager
    ):
        self.main_agent = main_agent
        self.permission_manager = permission_manager

        # Agent registry
        self.agents: dict[str, SubAgent] = {}
        self.agent_specs: dict[str, AgentSpec] = {}

        # Task management
        self.tasks: dict[str, DelegatedTask] = {}
        self.task_queue: list[str] = []  # Task IDs in order

        # Create default agents
        self._create_default_agents()

    def _create_default_agents(self) -> None:
        """Create a set of default specialized agents."""

        # Researcher agent
        researcher_spec = AgentSpec(
            name="researcher",
            role=AgentRole.RESEARCHER,
            description="Specializes in information gathering, web search, and fact-finding",
            tools=["http.fetch", "web.search", "browser.navigate", "browser.click", "browser.content", "rag.query"],
            system_prompt="You excel at finding accurate information from the web and knowledge bases. Always cite your sources."
        )
        self.register_agent(researcher_spec)

        # Coder agent
        coder_spec = AgentSpec(
            name="coder",
            role=AgentRole.CODER,
            description="Specializes in writing, debugging, and analyzing code",
            tools=["python.exec", "fs.read", "fs.write", "fs.list", "terminal.run", "browser.content"],
            system_prompt="You write clean, well-documented code. Follow best practices and include error handling."
        )
        self.register_agent(coder_spec)

        # Analyst agent
        analyst_spec = AgentSpec(
            name="analyst",
            role=AgentRole.ANALYST,
            description="Specializes in data analysis, synthesis, and drawing insights",
            tools=["python.exec", "rag.query", "rag.stats", "fs.read", "http.fetch"],
            system_prompt="You analyze data thoroughly and present clear, actionable insights with supporting evidence."
        )
        self.register_agent(analyst_spec)

        # Writer agent
        writer_spec = AgentSpec(
            name="writer",
            role=AgentRole.WRITER,
            description="Specializes in creating well-structured written content",
            tools=["rag.query", "rag.add"],
            system_prompt="You produce clear, well-structured written content tailored to the audience."
        )
        self.register_agent(writer_spec)

        # Reviewer agent
        reviewer_spec = AgentSpec(
            name="reviewer",
            role=AgentRole.REVIEWER,
            description="Specializes in reviewing work for quality, accuracy, and completeness",
            tools=["rag.query", "python.exec", "fs.read"],
            system_prompt="You critically evaluate work for correctness, completeness, and clarity. Be thorough but constructive."
        )
        self.register_agent(reviewer_spec)

    def register_agent(self, spec: AgentSpec) -> None:
        """Register a new sub-agent."""
        if spec.name in self.agents:
            raise ValueError(f"Agent '{spec.name}' already registered")

        # Import Agent locally to avoid circular import

        self.agent_specs[spec.name] = spec
        agent = SubAgent(spec, self.main_agent, self.permission_manager)
        self.agents[spec.name] = agent

    def get_agent(self, name: str) -> SubAgent | None:
        """Get a sub-agent by name."""
        return self.agents.get(name)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents."""
        return [
            {
                "name": spec.name,
                "role": spec.role.value,
                "description": spec.description,
                "tools": spec.tools,
            }
            for spec in self.agent_specs.values()
        ]

    def decompose_task(self, task: str, context: str = "") -> list[DelegatedTask]:
        """Decompose a complex task into subtasks using the planner."""
        # Use the main agent's planner to decompose the task
        prompt = f"""
        Decompose the following complex task into 3-7 discrete subtasks that can be executed by specialized agents.
        
        Main task: {task}
        Context: {context}
        
        Available agent types:
        - researcher: Information gathering, web search, fact-finding
        - coder: Writing, debugging, analyzing code
        - analyst: Data analysis, synthesis, insights
        - writer: Creating well-structured written content
        - reviewer: Reviewing work for quality and accuracy
        
        For each subtask, specify:
        1. Description of the subtask
        2. Which agent type should handle it
        3. Any dependencies on other subtasks
        
        Return as a JSON array of subtasks.
        """

        # Use main agent to decompose
        response = self.main_agent.run(prompt)

        # Parse the response (simplified - in production would use structured output)
        tasks = self._parse_decomposition(response, task)
        return tasks

    def _parse_decomposition(self, response: str, original_task: str) -> list[DelegatedTask]:
        """Parse the decomposition response into tasks."""
        # This is a simplified parser - in production would use structured output
        tasks = []
        lines = response.strip().split('\n')
        current_task = None

        for line in lines:
            line = line.strip()
            if line.startswith('{') or line.startswith('- ') or line.startswith('1.') or line.startswith('Subtask'):
                # New task
                if current_task:
                    tasks.append(current_task)

                # Extract description and agent type
                desc = line.lstrip('- 123456789. ').strip()
                agent_type = "researcher"  # default
                for role in AgentRole:
                    if role.value in line.lower():
                        agent_type = role.value
                        break

                task_id = str(uuid.uuid4())[:8]
                current_task = DelegatedTask(
                    id=task_id,
                    description=desc,
                    assigned_agent=agent_type,
                )

        if current_task:
            tasks.append(current_task)

        # If no tasks parsed, create a single task
        if not tasks:
            task_id = str(uuid.uuid4())[:8]
            tasks.append(DelegatedTask(
                id=task_id,
                description=original_task,
                assigned_agent="researcher",
            ))

        # Store tasks
        for task in tasks:
            self.tasks[task.id] = task
            self.task_queue.append(task.id)

        return tasks

    def execute_task(self, task_id: str) -> Any:
        """Execute a specific task."""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Check dependencies
        for dep_id in task.dependencies:
            dep_task = self.tasks.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                raise ValueError(f"Dependency {dep_id} not completed")

        # Get assigned agent
        agent = self.agents.get(task.assigned_agent)
        if not agent:
            raise ValueError(f"Agent {task.assigned_agent} not found")

        # Execute
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = time.time()

        try:
            result = agent.run(task.description)
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            raise

    def execute_all(self, task_ids: list[str] | None = None) -> dict[str, Any]:
        """Execute multiple tasks, respecting dependencies."""
        if task_ids is None:
            task_ids = self.task_queue[:]

        results = {}

        # Simple topological execution (respecting dependencies)
        remaining = set(task_ids)
        completed = set()

        while remaining:
            progress = False

            for task_id in list(remaining):
                task = self.tasks[task_id]

                # Check if all dependencies are completed
                deps_met = all(dep in completed for dep in task.dependencies)

                if deps_met:
                    try:
                        result = self.execute_task(task_id)
                        results[task_id] = result
                        completed.add(task_id)
                        remaining.remove(task_id)
                        progress = True
                    except Exception as e:
                        # Mark as failed but continue
                        results[task_id] = {"error": str(e)}
                        completed.add(task_id)
                        remaining.remove(task_id)
                        progress = True

            if not progress:
                # Circular dependency or all remaining blocked
                break

        return results

    def get_task_status(self, task_id: str) -> DelegatedTask | None:
        """Get status of a task."""
        return self.tasks.get(task_id)

    def get_all_results(self) -> dict[str, Any]:
        """Get results of all completed tasks."""
        return {
            task_id: task.result
            for task_id, task in self.tasks.items()
            if task.status == TaskStatus.COMPLETED
        }

    def synthesize_results(self, task_ids: list[str]) -> str:
        """Synthesize results from multiple tasks into a coherent summary."""
        results = self.get_all_results()

        relevant = {tid: results[tid] for tid in task_ids if tid in results}

        if not relevant:
            return "No results to synthesize."

        # Use main agent to synthesize
        synthesis_prompt = f"""
        Synthesize the following results from multiple sub-tasks into a coherent, comprehensive response.
        
        Original task context: {self.tasks[task_ids[0]].description if task_ids else 'Multi-task execution'}
        
        Sub-task results:
        {json.dumps(relevant, indent=2, default=str)}
        
        Provide a coherent synthesis that integrates all findings.
        """

        return self.main_agent.run(synthesis_prompt)


class MultiAgentTool(BaseTool):
    """Tool for multi-agent orchestration."""

    name = "orchestrator.delegate"
    description = "Delegate a complex task to multiple specialized sub-agents"
    selection_phrases = ("delegate", "orchestrate", "multi-agent", "coordinate agents", "distribute task")
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The complex task to decompose and delegate",
            },
            "context": {
                "type": "string",
                "description": "Additional context for task decomposition",
                "default": "",
            },
            "agents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific agents to use (optional, auto-selected if not provided)",
                "default": [],
            },
            "synthesize": {
                "type": "boolean",
                "description": "Whether to synthesize results into a final answer",
                "default": True,
            },
        },
        "required": ["task"],
        "additionalProperties": False,
    }

    def __init__(self, orchestrator: MultiAgentOrchestrator):
        self.orchestrator = orchestrator

    def validate_arguments(self, arguments: dict) -> None:
        if "task" not in arguments:
            raise ValueError("Missing required argument: 'task'")
        if not isinstance(arguments["task"], str) or not arguments["task"].strip():
            raise ValueError("'task' must be a non-empty string")

    def execute(self, **kwargs) -> Observation:
        task = kwargs["task"]
        context = kwargs.get("context", "")
        agents = kwargs.get("agents", [])
        synthesize = kwargs.get("synthesize", True)

        try:
            # Decompose task
            tasks = self.orchestrator.decompose_task(task, context)

            # Filter agents if specified
            if agents:
                for task in self.orchestrator.tasks.values():
                    if task.assigned_agent in agents:
                        pass  # Keep this task
                    else:
                        # Reassign or skip
                        pass

            # Execute all tasks
            results = self.orchestrator.execute_all()

            if synthesize:
                # Get all task IDs that were executed
                task_ids = list(self.orchestrator.tasks.keys())
                synthesis = self.orchestrator.synthesize_results(list(self.orchestrator.tasks.keys()))

                return Observation.create_success(
                    payload={
                        "tasks_executed": len(results),
                        "task_results": results,
                        "synthesis": synthesis,
                    },
                    metadata={
                        "task": task,
                        "context": context,
                        "synthesized": True,
                    }
                )
            else:
                return Observation.create_success(
                    payload={
                        "tasks_executed": len(results),
                        "task_results": results,
                    },
                    metadata={
                        "task": task,
                        "context": context,
                        "synthesized": False,
                    }
                )

        except Exception as e:
            return Observation.create_error(
                f"Multi-agent orchestration failed: {type(e).__name__}: {e}"
            )


def create_orchestrator(main_agent: "Agent", permission_manager: PermissionManager) -> MultiAgentOrchestrator:
    """Create a multi-agent orchestrator."""
    return MultiAgentOrchestrator(main_agent, permission_manager)
