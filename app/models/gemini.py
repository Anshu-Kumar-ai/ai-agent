
from dotenv import load_dotenv
from openai import OpenAI

from app.core.providers import ProviderType, get_provider_manager
from app.models.base import BaseModel

load_dotenv()


class GeminiModel(BaseModel):
    name = "gemini-3.7-flash"
    provider = "gemini"

    def __init__(self):
        # Check API key via provider manager
        pm = get_provider_manager()
        config = pm.get_config(ProviderType.GEMINI)
        if not config or not config.enabled:
            raise RuntimeError("Gemini API key not configured")

        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
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
