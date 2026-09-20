import unittest

from app.core.planner import Planner


CALCULATOR_TOOL = {
    "name": "calculator",
    "description": "Evaluate a safe arithmetic expression.",
    "selection_phrases": ["what is", "calculate", "solve"],
    "parameters": {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
        "additionalProperties": False,
    },
}


class PlannerDecisionTests(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_uses_calculator_metadata_for_a_numeric_expression(self):
        plan = self.planner.plan(
            "What is 25 * 4 + 10?",
            available_tools=[CALCULATOR_TOOL],
        )

        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "calculator")
        self.assertEqual(plan.arguments, {"expression": "25 * 4 + 10"})

    def test_responds_when_calculator_is_not_registered(self):
        plan = self.planner.plan(
            "What is 25 * 4 + 10?",
            available_tools=[],
        )

        self.assertEqual(plan.action, "respond")

    def test_responds_to_non_tool_request(self):
        plan = self.planner.plan(
            "Explain what a neural network is.",
            available_tools=[CALCULATOR_TOOL],
        )

        self.assertEqual(plan.action, "respond")

    def test_rejects_tool_names_without_metadata(self):
        with self.assertRaisesRegex(TypeError, "available_tools must be a list"):
            self.planner.plan(
                "What is 25 * 4 + 10?",
                available_tools={"calculator"},
            )

    def test_selects_an_arithmetic_capability_by_its_metadata_not_its_name(self):
        plan = self.planner.plan(
            "Please solve 7 * 6.",
            available_tools=[
                {
                    "name": "math_engine",
                    "description": "Evaluate arithmetic expressions.",
                    "parameters": {
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"],
                        "additionalProperties": False,
                    },
                    "selection_phrases": ["solve", "calculate"],
                }
            ],
        )

        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "math_engine")
        self.assertEqual(plan.arguments, {"expression": "7 * 6"})


if __name__ == "__main__":
    unittest.main()
