from app.models.openrouter import OpenRouterModel


def main():
    print("=" * 50)
    print("OPENROUTER PROVIDER TEST")
    print("=" * 50)

    model = OpenRouterModel()

    response = model.chat(
        "Reply with exactly this sentence: OpenRouter is working correctly."
    )

    print("\nAI RESPONSE:")
    print(repr(response))

    if response:
        print("\nOPENROUTER PROVIDER WORKING")
    else:
        print("\nWARNING: OpenRouter returned an empty response")


if __name__ == "__main__":
    main()