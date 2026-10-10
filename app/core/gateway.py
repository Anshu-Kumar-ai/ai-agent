"""Model Gateway with lazy provider initialization for Stage 13.

Providers are only instantiated when API keys are available.
"""


from app.core.providers import ProviderManager, ProviderType, get_provider_manager
from app.models.base import BaseModel


class ModelGateway:
    """Lazy gateway that initializes providers only when needed."""

    def __init__(self, provider_manager: ProviderManager | None = None):
        self.provider_manager = provider_manager or get_provider_manager()
        self._models: dict[ProviderType, BaseModel | None] = {
            ProviderType.GEMINI: None,
            ProviderType.GROQ: None,
            ProviderType.OPENROUTER: None,
            ProviderType.LOCAL: None,
        }

    def _get_model(self, provider: ProviderType) -> BaseModel:
        """Lazy-load model instance."""
        if self._models[provider] is not None:
            return self._models[provider]

        config = self.provider_manager.get_config(provider)
        if not config:
            raise ValueError(f"Unknown provider: {provider}")

        if provider == ProviderType.GEMINI:
            from app.models.gemini import GeminiModel
            model = GeminiModel()
        elif provider == ProviderType.GROQ:
            from app.models.groq import GroqModel
            model = GroqModel()
        elif provider == ProviderType.OPENROUTER:
            from app.models.openrouter import OpenRouterModel
            model = OpenRouterModel()
        elif provider == ProviderType.LOCAL:
            from app.models.local import LocalModel
            model = LocalModel()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        self._models[provider] = model
        return model

    def ask(self, provider: str, message: str) -> str:
        """Ask a provider for a response."""
        try:
            provider_type = ProviderType(provider)
        except ValueError:
            raise ValueError(f"Unknown provider: {provider}")

        if not self.provider_manager.is_available(provider_type):
            raise RuntimeError(f"Provider {provider} is not available (no API key)")

        model = self._get_model(provider_type)
        return model.chat(message)

    def get_available_providers(self) -> list[str]:
        """Get list of available provider names."""
        return [p.value for p in self.provider_manager.get_available_providers()]

    def get_model_info(self, provider: str) -> dict:
        """Get information about a model."""
        try:
            provider_type = ProviderType(provider)
        except ValueError:
            return {"error": "Unknown provider"}

        config = self.provider_manager.get_config(provider_type)
        if not config:
            return {"error": "Unknown provider"}

        return {
            "name": config.name,
            "model_name": config.model_name,
            "enabled": config.enabled,
            "base_url": config.base_url,
        }


# Convenience function for backward compatibility
def create_gateway() -> ModelGateway:
    """Create a ModelGateway with default provider manager."""
    return ModelGateway()
