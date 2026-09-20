from app.core.planner import Planner


def main():
    print("=" * 60)
    print("PLANNER TEST")
    print("=" * 60)

    planner = Planner()

    direct_plan = planner.plan_response(
        reason="The question can be answered directly."
    )

    print("\nDirect plan:")
    print(direct_plan)

    tool_plan = planner.plan_tool(
        tool_name="calculator",
        arguments={
            "expression": "25 * 4 + 10"
        },
        reason="The task requires arithmetic.",
    )

    print("\nTool plan:")
    print(tool_plan)


if __name__ == "__main__":
    main()
