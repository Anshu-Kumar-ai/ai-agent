from app.models.groq import GroqModel


def main():
    model = GroqModel()

    response = model.chat(
        "Reply with exactly: GROQ AI WORKING"
    )

    print("\nAI RESPONSE:")
    print(response)


if __name__ == "__main__":
    main()