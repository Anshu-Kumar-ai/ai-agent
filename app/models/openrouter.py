
from dotenv import load_dotenv
from openai import OpenAI

from app.core.providers import ProviderType, get_provider_manager
from app.models.base import BaseModel

load_dotenv()


class OpenRouterModel(BaseModel):
    def __init__(self):
        # Check API key via provider manager
        pm = get_provider_manager()
        config = pm.get_config(ProviderType.OPENROUTER)
        if not config or not config.enabled:
            raise RuntimeError("OpenRouter API key not configured")

        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
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
