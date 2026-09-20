from app.models.gemini import GeminiModel


def main():
    model = GeminiModel()

    response = model.chat(
        "Reply with exactly: CLOUD AI WORKING"
    )

    print("\nAI RESPONSE:")
    print(response)


if __name__ == "__main__":
    main()