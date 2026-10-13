"""Regression tests for Planner fix - semantic mathematical requests."""

import unittest
from app.core.planner import Planner
from app.tools.calculator import CalculatorTool
from app.tools.base import BaseTool


class MockTool(BaseTool):
    """Mock tool accepting expression parameter for testing fallback."""
    name = "mock_calculator"
    description = "Mock calculator for testing"
    selection_phrases = ("mock",)
    parameters = {
        "type": "object",
        "properties": {
            "expression": {"type": "string"}
        },
        "required": ["expression"],
    }

    def execute(self, expression: str):
        return f"mock: {expression}"


class TestPlannerRegression(unittest.TestCase):
    """Test planner handles semantic math requests without 'calculate' keyword."""

    def setUp(self):
        self.planner = Planner()
        self.calculator_tool = {
            "name": "calculator",
            "description": "Evaluate basic arithmetic expressions",
            "selection_phrases": ["calculate", "calculator", "what is", "solve"],
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        }
        self.time_tool = {
            "name": "time",
            "description": "Get current time",
            "selection_phrases": ["time", "what time"],
            "parameters": {"type": "object", "properties": {}, "required": []},
        }

    def test_average_request_triggers_calculator_fallback(self):
        """'Find the average of 10, 20 and 30.' should select calculator via fallback."""
        message = "Find the average of 10, 20 and 30."
        available_tools = [self.calculator_tool]

        # First call (no observations) - should compute sum
        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")
        self.assertEqual(plan.arguments["expression"], "10 + 20 + 30")

    def test_average_second_step_computes_division(self):
        """Second step of average should divide sum by count."""
        message = "Find the average of 10, 20 and 30."
        available_tools = [self.calculator_tool]

        # Simulate first observation with sum result
        from app.core.agent_loop import ToolObservation
        obs = [ToolObservation(tool_name="calculator", result="60")]

        plan = self.planner.plan(message, available_tools, observations=obs)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")
        self.assertEqual(plan.arguments["expression"], "(60) / 3")

    def test_average_third_step_responds(self):
        """Third step of average should respond with completion."""
        message = "Find the average of 10, 20 and 30."
        available_tools = [self.calculator_tool]

        from app.core.agent_loop import ToolObservation
        obs = [
            ToolObservation(tool_name="calculator", result="60"),
            ToolObservation(tool_name="calculator", result="20"),
        ]

        plan = self.planner.plan(message, available_tools, observations=obs)
        self.assertEqual(plan.action, "respond")
        self.assertEqual(plan.reason, "Average calculation complete.")

    def test_calculate_average_with_keyword(self):
        """'Calculate the average of 10, 20 and 30.' matches selection phrase 'calculate'."""
        message = "Calculate the average of 10, 20 and 30."
        available_tools = [self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")

    def test_what_is_average_with_keyword(self):
        """'What is the average of 10, 20 and 30?' matches 'what is'."""
        message = "What is the average of 10, 20 and 30?"
        available_tools = [self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")

    def test_simple_calculate_expression(self):
        """'Calculate 10 + 20' matches selection phrase."""
        message = "Calculate 10 + 20"
        available_tools = [self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")

    def test_what_is_arithmetic(self):
        """'What is 25 * 4?' matches 'what is'."""
        message = "What is 25 * 4?"
        available_tools = [self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")

    def test_solve_arithmetic(self):
        """'Solve 100 / 5' matches 'solve'."""
        message = "Solve 100 / 5"
        available_tools = [self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")

    def test_non_math_request_no_fallback(self):
        """Non-mathematical requests should not trigger calculator fallback."""
        message = "What is the weather today?"
        available_tools = [self.calculator_tool, self.time_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        # No "expression" in required for time tool, and no expression extracted
        self.assertEqual(plan.action, "respond")
        self.assertEqual(plan.reason, "No registered tool is currently required.")

    def test_observations_without_expression_responds(self):
        """With observations but no expression, should respond."""
        message = "Find the result of 25 * 4"  # No selection phrase match
        available_tools = [self.calculator_tool]

        from app.core.agent_loop import ToolObservation
        obs = [ToolObservation(tool_name="calculator", result="100")]

        plan = self.planner.plan(message, available_tools, observations=obs)
        self.assertEqual(plan.action, "respond")
        self.assertEqual(plan.reason, "Expression evaluation complete.")

    def test_calculator_preferred_over_other_expression_tools(self):
        """Calculator should be preferred when multiple expression tools exist."""
        mock_tool = {
            "name": "mock_calculator",
            "description": "Mock calculator",
            "selection_phrases": ["mock"],
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        }
        message = "Find the average of 10, 20 and 30."
        available_tools = [mock_tool, self.calculator_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.tool_name, "calculator")

    def test_fallback_uses_first_tool_when_no_calculator(self):
        """If no calculator, use first available expression tool."""
        mock_tool = {
            "name": "mock_calculator",
            "description": "Mock calculator",
            "selection_phrases": ["mock"],
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        }
        message = "Find the average of 10, 20 and 30."
        available_tools = [mock_tool]

        plan = self.planner.plan(message, available_tools, observations=None)
        self.assertEqual(plan.tool_name, "mock_calculator")

    def test_selection_phrase_match_with_observations_responds(self):
        """Selection phrase match with observations should respond (not average)."""
        message = "Calculate 10 + 20"
        available_tools = [self.calculator_tool]

        from app.core.agent_loop import ToolObservation
        obs = [ToolObservation(tool_name="calculator", result="30")]

        plan = self.planner.plan(message, available_tools, observations=obs)
        self.assertEqual(plan.action, "respond")
        self.assertEqual(plan.reason, "A tool result is available for the final response.")


class TestPlannerLLMPlannerInit(unittest.TestCase):
    """Test LLMPlanner initialization with fallback_gateway."""

    def test_llm_planner_accepts_fallback_gateway(self):
        """LLMPlanner should accept optional fallback_gateway parameter."""
        from app.core.planner import LLMPlanner
        from app.core.router import SmartRouter

        router = SmartRouter()
        planner = LLMPlanner(router=router, fallback_gateway=None)
        self.assertIsNone(planner.fallback_gateway)

        class MockGateway:
            def ask(self, provider, prompt):
                return '{"action": "respond", "tool_name": null, "arguments": {}, "reason": "test"}'

        gateway = MockGateway()
        planner2 = LLMPlanner(router=router, fallback_gateway=gateway)
        self.assertEqual(planner2.fallback_gateway, gateway)

    def test_llm_planner_backward_compatible(self):
        """LLMPlanner should work without fallback_gateway (default)."""
        from app.core.planner import LLMPlanner
        from app.core.router import SmartRouter

        router = SmartRouter()
        planner = LLMPlanner(router=router)  # No fallback_gateway
        self.assertIsNone(planner.fallback_gateway)


if __name__ == "__main__":
    unittest.main()
