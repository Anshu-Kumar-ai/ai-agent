import unittest
from unittest.mock import MagicMock, patch

from app.core.agent import Agent
from app.core.agent_loop import AgentLoop
from app.core.planner import Plan
from app.memory.enhanced import EnhancedMemory
from app.tools.calculator import CalculatorTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


CALCULATOR_META = {
    "name": "calculator",
    "description": "Evaluate basic arithmetic expressions such as 2 + 3 * 4, (10 / 2), or 5 ** 2.",
    "selection_phrases": ["what is", "calculate", "solve", "multiply", "divide"],
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression to evaluate.",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
}


class AgentEnhancedMemoryTests(unittest.TestCase):
    """Tests for EnhancedMemory integration with Agent."""

    def test_agent_uses_enhanced_memory(self):
        """Agent should use EnhancedMemory instead of base ConversationMemory."""
        agent = Agent()

        self.assertIsInstance(agent.memory, EnhancedMemory)

    def test_agent_stores_tool_observations_automatically(self):
        """Tool observations should be stored after each tool execution."""
        agent = Agent()

        agent.run("What is 25 * 4 + 10?")

        observations = agent.memory.get_tool_observations()

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["tool"], "calculator")
        self.assertEqual(observations[0]["result"], 110)

    def test_agent_stores_reflection_after_tool_execution(self):
        """Agent should add a reflection evaluating the tool result."""
        agent = Agent()

        agent.run("What is 25 * 4 + 10?")

        reflections = agent.memory.get_reflections()

        self.assertGreaterEqual(len(reflections), 1)
        self.assertIn("110", reflections[0])

    def test_agent_context_includes_observations_and_reflections(self):
        """Subsequent requests should see previous observations and reflections in context."""
        agent = Agent()

        # First request
        agent.run("What is 25 * 4 + 10?")

        # Check the context for the second request includes the observation and reflection
        from app.core.planner import Plan

        # Also mock evaluator to return high score to avoid retries
        original_evaluator = agent.evaluator
        from app.core.evaluation import Evaluation
        
        mock_evaluation = Evaluation(score=1.0, feedback="All criteria met.", criteria_met=["all"], criteria_not_met=[])
        agent.evaluator.evaluate = lambda *args, **kwargs: mock_evaluation
        
        try:
            with patch.object(agent.planner, "plan", side_effect=[
                Plan(action="use_tool", tool_name="calculator", arguments={"expression": "25 * 4 + 10"}, reason="Calculate"),
                Plan(action="respond", tool_name=None, arguments={}, reason="The answer is 110."),
                Plan(action="respond", tool_name=None, arguments={}, reason="The answer is 110."),
            ]) as mock_plan:
                agent.run("What was the previous answer?")

                # Get the context passed to the planner
                call_args = mock_plan.call_args_list[1]  # Second call (first plan for second request)
                context = call_args[1].get("context", "") if call_args[1] else call_args[0][3]
                self.assertIn("calculator", context)
                self.assertIn("110", context)
                self.assertIn("Tool observations", context)
        finally:
            agent.evaluator = original_evaluator


class AgentLoopWithReflectionTests(unittest.TestCase):
    """Tests for AgentLoop integration with reflection."""

    def setUp(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        self.executor = ToolExecutor(registry)
        self.available_tools = [CALCULATOR_META]

    def test_agent_loop_can_accept_reflection_callback(self):
        """AgentLoop should accept an optional reflection callback."""
        from app.core.llm_planner import LLMPlanner

        mock_router = MagicMock()
        mock_router.ask.side_effect = [
            """{
                "action": "use_tool",
                "tool_name": "calculator",
                "arguments": {"expression": "10 + 20"},
                "reason": "Sum the numbers."
            }""",
            """{
                "action": "respond",
                "tool_name": null,
                "arguments": {},
                "reason": "The sum is 30."
            }""",
        ]

        planner = LLMPlanner(router=mock_router)
        reflection_calls = []

        def reflection_callback(tool_name, result):
            reflection_calls.append(f"Executed {tool_name} = {result}")

        loop = AgentLoop(planner, self.executor, max_steps=3, reflection_callback=reflection_callback)

        result = loop.run(
            "Find the sum of 10 and 20.",
            available_tools=self.available_tools,
            responder=lambda observations: f"The sum is {observations[-1].result}.",
        )

        self.assertEqual(result, "The sum is 30.")
        self.assertEqual(len(reflection_calls), 1)
        self.assertIn("calculator", reflection_calls[0])
        self.assertIn("30", reflection_calls[0])


if __name__ == "__main__":
    unittest.main()