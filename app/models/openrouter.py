import os
from openai import OpenAI
from dotenv import load_dotenv
from app.models.base import BaseModel

load_dotenv()


class OpenRouterModel(BaseModel):
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )

    def chat(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content