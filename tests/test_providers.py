from app.core.gateway import ModelGateway


def main():
    gateway = ModelGateway()

    providers = [
        "local",
        "gemini",
        "groq",
    ]

    for provider in providers:
        print(f"\n{'=' * 50}")
        print(f"Testing: {provider}")
        print(f"{'=' * 50}")

        try:
            response = gateway.ask(
                provider,
                f"Reply with exactly: {provider.upper()} PROVIDER WORKING",
            )

            print(response)

        except Exception as error:
            print(f"ERROR: {error}")


if __name__ == "__main__":
    main()