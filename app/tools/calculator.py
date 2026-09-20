import ast
import operator as op

from app.tools.base import BaseTool


class CalculatorTool(BaseTool):
    """Safely evaluate basic mathematical expressions."""

    name = "calculator"
    description = (
        "Evaluate basic arithmetic expressions such as "
        "2 + 3 * 4, (10 / 2), or 5 ** 2."
    )
    selection_phrases = (
        "calculate",
        "calculator",
        "what is",
        "solve",
        "multiply",
        "divide",
        "subtract",
        "add",
    )

    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression to evaluate.",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    _operators = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.FloorDiv: op.floordiv,
        ast.Mod: op.mod,
        ast.Pow: op.pow,
        ast.USub: op.neg,
        ast.UAdd: op.pos,
    }

    def execute(self, expression: str):
        if not isinstance(expression, str):
            raise TypeError("expression must be a string")

        expression = expression.strip()

        if not expression:
            raise ValueError("expression cannot be empty")

        tree = ast.parse(expression, mode="eval")

        return self._evaluate(tree.body)

    def _evaluate(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value

            raise ValueError("Only numeric values are allowed")

        if isinstance(node, ast.BinOp):
            operation = self._operators.get(type(node.op))

            if operation is None:
                raise ValueError("Operator is not allowed")

            left = self._evaluate(node.left)
            right = self._evaluate(node.right)

            return operation(left, right)

        if isinstance(node, ast.UnaryOp):
            operation = self._operators.get(type(node.op))

            if operation is None:
                raise ValueError("Operator is not allowed")

            return operation(self._evaluate(node.operand))

        raise ValueError("Invalid mathematical expression")
