from app.core.router import SmartRouter


def main():
    router = SmartRouter()

    # Save the real gateway method
    original_ask = router.gateway.ask

    # Force Gemini and Groq to fail for this test
    def test_ask(provider, message):
        if provider == "gemini":
            raise RuntimeError("Simulated Gemini failure")

        if provider == "groq":
            raise RuntimeError("Simulated Groq failure")

        # OpenRouter and Local work normally
        return original_ask(provider, message)

    router.gateway.ask = test_ask

    print("\n" + "=" * 60)
    print("SMART ROUTER FALLBACK TEST")
    print("=" * 60)

    response = router.ask(
        "Explain what an AI agent is in one simple sentence."
    )

    print("\nAI RESPONSE:")
    print(response)


if __name__ == "__main__":
    main()