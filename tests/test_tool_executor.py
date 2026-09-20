from app.tools.calculator import CalculatorTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


def main():
    print("=" * 60)
    print("TOOL EXECUTOR TEST")
    print("=" * 60)

    registry = ToolRegistry()
    registry.register(CalculatorTool())

    executor = ToolExecutor(registry)

    result = executor.execute(
        "calculator",
        expression="25 * 4 + 10",
    )

    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
