import unittest
from unittest.mock import MagicMock

from app.core.agent_loop import AgentLoop
from app.core.planner import Plan
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


class LLMPlannerTests(unittest.TestCase):
    """Tests for an LLM-based planner that proposes plans validated through Plan.from_dict()."""

    def setUp(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        self.executor = ToolExecutor(registry)
        self.available_tools = [CALCULATOR_META]

    def test_llm_planner_proposes_valid_plan_for_arithmetic(self):
        """An LLM planner should return a validated Plan for a calculator request."""
        from app.core.llm_planner import LLMPlanner

        mock_router = MagicMock()
        mock_router.ask.return_value = """{
            "action": "use_tool",
            "tool_name": "calculator",
            "arguments": {"expression": "25 * 4 + 10"},
            "reason": "The user is asking for an arithmetic calculation."
        }"""

        planner = LLMPlanner(router=mock_router)
        plan = planner.plan(
            "What is 25 * 4 + 10?",
            available_tools=self.available_tools,
        )

        self.assertIsInstance(plan, Plan)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")
        self.assertEqual(plan.arguments, {"expression": "25 * 4 + 10"})

    def test_llm_planner_rejects_invalid_json_and_falls_back(self):
        """Malformed LLM output should raise a clear error, not crash silently."""
        from app.core.llm_planner import LLMPlanner

        mock_router = MagicMock()
        mock_router.ask.return_value = "not valid json { action: use_tool }"

        planner = LLMPlanner(router=mock_router)

        with self.assertRaisesRegex(ValueError, "LLM response is not valid JSON"):
            planner.plan(
                "What is 25 * 4 + 10?",
                available_tools=self.available_tools,
            )

    def test_llm_planner_rejects_unknown_tool_name(self):
        """An LLM proposing a tool not in available_tools should be rejected."""
        from app.core.llm_planner import LLMPlanner

        mock_router = MagicMock()
        mock_router.ask.return_value = """{
            "action": "use_tool",
            "tool_name": "unknown_tool",
            "arguments": {},
            "reason": "Trying something not registered."
        }"""

        planner = LLMPlanner(router=mock_router)

        with self.assertRaisesRegex(ValueError, "tool_name must be a registered tool"):
            planner.plan(
                "What is 25 * 4 + 10?",
                available_tools=self.available_tools,
            )

    def test_llm_planner_integration_with_agent_loop(self):
        """An LLM planner should work end-to-end through AgentLoop."""
        from app.core.llm_planner import LLMPlanner

        mock_router = MagicMock()
        mock_router.ask.return_value = """{
            "action": "use_tool",
            "tool_name": "calculator",
            "arguments": {"expression": "10 + 20 + 30"},
            "reason": "Sum the three numbers."
        }"""

        planner = LLMPlanner(router=mock_router)
        loop = AgentLoop(planner, self.executor, max_steps=3)

        # First call returns calculator plan, second call should respond
        call_count = [0]
        def mock_ask_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return """{
                    "action": "use_tool",
                    "tool_name": "calculator",
                    "arguments": {"expression": "10 + 20 + 30"},
                    "reason": "Sum the three numbers."
                }"""
            else:
                return """{
                    "action": "respond",
                    "tool_name": null,
                    "arguments": {},
                    "reason": "The sum is 60."
                }"""

        mock_router.ask.side_effect = mock_ask_side_effect

        result = loop.run(
            "Find the sum of 10, 20, and 30.",
            available_tools=self.available_tools,
            responder=lambda observations: f"The sum is {observations[-1].result}.",
        )

        self.assertEqual(result, "The sum is 60.")


if __name__ == "__main__":
    unittest.main()