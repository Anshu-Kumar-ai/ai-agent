from app.models.gemini import GeminiModel
from app.models.groq import GroqModel
from app.models.local import LocalModel
from app.models.openrouter import OpenRouterModel


class ModelGateway:
    def __init__(self):
        self.models = {
            "gemini": GeminiModel(),
            "groq": GroqModel(),
            "openrouter": OpenRouterModel(),
            "local": LocalModel(),
        }

    def ask(self, provider: str, message: str) -> str:
        if provider not in self.models:
            raise ValueError(
                f"Unknown provider: {provider}"
            )

        return self.models[provider].chat(message)