from app.core.gateway import ModelGateway


def main():
    gateway = ModelGateway()

    response = gateway.ask(
        "openrouter",
        "Explain what an AI agent is in one simple sentence."
    )

    print("\nAI RESPONSE:")
    print(response)


if __name__ == "__main__":
    main()
