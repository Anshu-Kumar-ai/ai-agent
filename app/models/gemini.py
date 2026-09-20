import os

from dotenv import load_dotenv
from openai import OpenAI

from app.models.base import BaseModel

load_dotenv()


class GeminiModel(BaseModel):
    name = "gemini-3.7-flash"
    provider = "gemini"

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured in .env"
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
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