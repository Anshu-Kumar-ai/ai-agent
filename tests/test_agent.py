from app.core.agent import Agent


def main():
    print("=" * 60)
    print("AGENT + MEMORY TEST")
    print("=" * 60)

    agent = Agent(max_memory_messages=4)

    response = agent.run("My name is Anshu.")

    print("\nAI RESPONSE:")
    print(response)

    response = agent.run("I am learning Python.")

    print("\nAI RESPONSE:")
    print(response)

    print("\nMEMORY:")
    for message in agent.get_memory():
        print(message)

    print(f"\nMemory count: {len(agent.get_memory())}")

    agent.clear_memory()

    print(f"After clear: {len(agent.get_memory())}")


if __name__ == "__main__":
    main()