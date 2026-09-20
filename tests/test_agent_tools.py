from app.core.agent import Agent


def main():
    print("=" * 60)
    print("AGENT TOOL USE TEST")
    print("=" * 60)

    agent = Agent()

    print("\nUSER: What is 25 * 4 + 10?")

    response = agent.run(
        "What is 25 * 4 + 10?"
    )

    print(f"\nAGENT: {response}")

    print("\nAVAILABLE TOOLS:")
    for tool in agent.list_tools():
        print(tool)


if __name__ == "__main__":
    main()
