from app.core.agent import Agent


def main():
    print("=" * 60)
    print("AGENT MEMORY CONTEXT TEST")
    print("=" * 60)

    agent = Agent(max_memory_messages=10)

    print("\nUSER: My name is Anshu.")
    response = agent.run("My name is Anshu.")
    print("AGENT:", response)

    print("\nUSER: What is my name?")
    response = agent.run("What is my name?")
    print("AGENT:", response)

    print("\nMEMORY:")
    for message in agent.get_memory():
        print(message)


if __name__ == "__main__":
    main()