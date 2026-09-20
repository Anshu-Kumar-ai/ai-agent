import os

from dotenv import load_dotenv
from openai import OpenAI

from app.models.base import BaseModel

load_dotenv()


class GroqModel(BaseModel):
    name = "openai/gpt-oss-20b"
    provider = "groq"

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured in .env"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    def chat(self, message: str) -> str:
        response = self.client.chat.completions.create(
            model=self.name,
            messages=[
                {
                    "role": "user",
                    "content": message,
                }
            ],
        )

        return response.choices[0].message.content