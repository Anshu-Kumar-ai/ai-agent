import unittest

from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Return the provided text unchanged."
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to return.",
            }
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, text: str) -> str:
        return text


class GenericToolMetadataTests(unittest.TestCase):
    def test_calculator_exposes_a_json_schema_for_its_input(self):
        calculator = CalculatorTool()

        self.assertEqual(calculator.parameters["type"], "object")
        self.assertEqual(
            calculator.parameters["properties"]["expression"]["type"],
            "string",
        )
        self.assertEqual(calculator.parameters["required"], ["expression"])

    def test_registry_lists_tool_parameters(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())

        tool = registry.list_tools()[0]

        self.assertEqual(tool["name"], "calculator")
        self.assertIn("parameters", tool)
        self.assertEqual(tool["parameters"]["required"], ["expression"])

    def test_executor_uses_the_generic_execute_interface(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        executor = ToolExecutor(registry)

        self.assertEqual(executor.execute("echo", text="hello"), "hello")

    def test_run_remains_a_compatible_alias_for_execute(self):
        self.assertEqual(CalculatorTool().run(expression="2 + 3"), 5)


if __name__ == "__main__":
    unittest.main()
