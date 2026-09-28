import json
import logging
import time

from ...core.state.action import Action, RetryPolicy, SandboxSpec
from ...core.state.agent_state import ConversationState, TaskGoalState
from ...core.state.goal_state import Goal
from ...modules.executor.tool_registry import ToolRegistry
from ...modules.llm.provider import LLMProvider
from ...modules.planner.stub_planner import StubPlanner
from .base import Planner

logger = logging.getLogger(__name__)


class LLMPlanner(Planner):
    """
    Planner that uses an LLM to generate a list of actions.
    Falls back to StubPlanner on failure.
    """

    def __init__(self, llm_provider: LLMProvider, fallback_planner: Planner | None = None, max_retries: int = 2):
        self.llm_provider = llm_provider
        self.fallback_planner = fallback_planner or StubPlanner()
        self.max_retries = max_retries
        # Tool descriptions for the prompt
        self.tool_descriptions = {
            "fs.read": "Read a file. Arguments: {'path': string}. Returns file content.",
            "fs.write": "Write a file. Arguments: {'path': string, 'content': string}.",
            "fs.move": "Move/rename a file. Arguments: {'src': string, 'dst': string}.",
            "fs.list": "List directory contents. Arguments: {'path': string}. Returns list of file info.",
            "terminal.run": "Run a terminal command. Arguments: {'cmd': list of strings or string, 'timeout?: number}. Returns stdout, stderr, exit code.",
            "echo": "Echo tool for testing. Arguments: {'msg': string}. Returns the message."
        }

    def _build_prompt(self, goal: Goal, task_state: TaskGoalState, conv_state: ConversationState) -> str:
        """Construct a prompt for the LLM."""
        # Goal info
        prompt_parts = [
            "You are an AI agent tasked with achieving a goal.",
            f"Goal: {goal.description}",
            ""
        ]

        # Success criteria
        if goal.success_criteria.criteria:
            prompt_parts.append("Success criteria:")
            for key, val in goal.success_criteria.criteria.items():
                prompt_parts.append(f"  {key}: {json.dumps(val)}")
            prompt_parts.append("")

        # Current state
        prompt_parts.append("Current state:")
        prompt_parts.append(f"  Version: {task_state.version}")
        prompt_parts.append(f"  Active goal ID: {str(task_state.active_goal_id) if task_state.active_goal_id else 'None'}")
        prompt_parts.append(f"  Goal stack depth: {len(task_state.goal_stack)}")
        prompt_parts.append(f"  Working memory keys: {list(task_state.working_memory.keys())}")
        prompt_parts.append(f"  Sandbox context: {json.dumps(task_state.sandbox_context)}")
        prompt_parts.append("")

        # Recent attempts (last 3)
        recent_attempts = task_state.attempt_history[-3:] if task_state.attempt_history else []
        if recent_attempts:
            prompt_parts.append("Recent attempts (most recent last):")
            for i, attempt in enumerate(recent_attempts):
                prompt_parts.append(
                    f"  {i+1}. Tool: {attempt.action.tool_name}, "
                    f"Args: {json.dumps(attempt.action.arguments)}, "
                    f"Result: {attempt.observation.status if hasattr(attempt.observation, 'status') else 'unknown'}"
                )
            prompt_parts.append("")

        # Recent conversation turns (last 3 turns)
        recent_turns = conv_state.get_recent_turns(3)
        if recent_turns:
            prompt_parts.append("Recent conversation:")
            for turn in recent_turns:
                prompt_parts.append(f"  {turn.role}: {turn.text}")
            prompt_parts.append("")

        # Available tools
        prompt_parts.append("Available tools:")
        for tool_name in ToolRegistry.list_names():
            desc = self.tool_descriptions.get(tool_name, "No description available.")
            prompt_parts.append(f"  {tool_name}: {desc}")
        prompt_parts.append("")

        # Instructions
        prompt_parts.append(
            "Return a JSON array of action objects to try next, in order of preference. "
            "Each action object must have: "
            "\"tool_name\" (string) and \"arguments\" (object). "
            "Example: [{\"tool_name\": \"fs.write\", \"arguments\": {\"path\": \"hello.txt\", \"content\": \"Hello\"}}]"
        )
        prompt_parts.append(
            "If you do not know what to do, return an empty array []. "
            "Do not include any extra text before or after the JSON array."
        )

        return "\n".join(prompt_parts)

    def _parse_llm_response(self, response: str) -> list[Action]:
        """Parse the LLM's JSON response into a list of Action objects."""
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"LLM response is not valid JSON: {response}")
            raise ValueError(f"Invalid JSON from LLM: {e}")

        if not isinstance(data, list):
            logger.warning(f"LLM response is not a list: {data}")
            raise ValueError("Expected a JSON array")

        actions: list[Action] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning(f"LLM response item {i} is not an object: {item}")
                raise ValueError(f"Expected object at index {i}")

            tool_name = item.get("tool_name")
            if not isinstance(tool_name, str):
                logger.warning(f"LLM response item {i} missing or invalid 'tool_name'")
                raise ValueError(f"Missing or invalid 'tool_name' at index {i}")

            arguments = item.get("arguments")
            if not isinstance(arguments, dict):
                logger.warning(f"LLM response item {i} missing or invalid 'arguments'")
                raise ValueError(f"Missing or invalid 'arguments' at index {i}")

            # Validate that the tool exists
            try:
                ToolRegistry.get(tool_name)
            except KeyError:
                logger.warning(f"LLM response item {i} references unknown tool: {tool_name}")
                raise ValueError(f"Unknown tool '{tool_name}' at index {i}")

            # Create the action with default sandbox, timeout, and retry policy
            action = Action.create(
                tool_name=tool_name,
                arguments=arguments,
                sandbox=SandboxSpec(),
                timeout_sec=10.0,
                retry_policy=RetryPolicy()
            )
            actions.append(action)

        return actions

    def plan(self, goal: Goal, task_state: TaskGoalState, conv_state: ConversationState) -> list[Action]:
        """Generate a plan using the LLM, with fallback and retries."""
        if not self.llm_provider.is_available():
            logger.warning("LLM provider not available, using fallback planner")
            return self.fallback_planner.plan(goal, task_state, conv_state)

        prompt = self._build_prompt(goal, task_state, conv_state)
        logger.debug(f"LLM planner prompt:\n{prompt}")

        last_exception = None
        for retry in range(self.max_retries + 1):
            try:
                response = self.llm_provider.generate(prompt)
                logger.debug(f"LLM planner raw response: {response}")
                actions = self._parse_llm_response(response)
                logger.info(f"LLM planner generated {len(actions)} actions")
                return actions
            except Exception as e:
                last_exception = e
                logger.warning(f"LLM planner attempt {retry + 1}/{self.max_retries + 1} failed: {e}")
                if retry < self.max_retries:
                    time.sleep(0.5 * (retry + 1))  # brief backoff
                else:
                    logger.warning(f"LLM planner failed after {self.max_retries + 1} attempts: {last_exception}. Falling back to stub planner.")
                    return self.fallback_planner.plan(goal, task_state, conv_state)

        # Should not reach here due to return in loop, but for type safety:
        return self.fallback_planner.plan(goal, task_state, conv_state)