from app.tools.calculator import CalculatorTool
from app.tools.registry import ToolRegistry


def main():
    print("=" * 60)
    print("TOOL SYSTEM TEST")
    print("=" * 60)

    registry = ToolRegistry()

    calculator = CalculatorTool()

    registry.register(calculator)

    print("\nRegistered tools:")
    for tool in registry.list_tools():
        print(tool)

    print(f"\nTool count: {registry.count()}")

    expression = "10 + 5 * 2"

    result = registry.get("calculator").run(
        expression=expression
    )

    print(f"\nExpression: {expression}")
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
