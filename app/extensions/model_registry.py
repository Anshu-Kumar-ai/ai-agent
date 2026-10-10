"""Model Registry - Stage 32 Phase 2
Supports multiple models per provider and model discovery.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from app.extensions.contracts import ProviderInterface
from app.extensions.provider_registry import ProviderRegistryEnhanced


@dataclass
class ModelInfo:
    """Information about a specific model."""
    
    model_id: str
    provider_id: str
    display_name: str
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    context_length: int = 0
    supports_functions: bool = False
    supports_vision: bool = False
    is_available: bool = True


class ModelRegistry:
    """Registry for managing multiple models per provider."""
    
    def __init__(self, provider_registry: ProviderRegistryEnhanced):
        self.provider_registry = provider_registry
        # Model registry: provider_id -> model_id -> ModelInfo
        self._models: Dict[str, Dict[str, ModelInfo]] = {}
        # Reverse index: model_id -> provider_id (for quick lookup)
        self._model_to_provider: Dict[str, str] = {}
        self._setup_default_models()
    
    def _setup_default_models(self):
        """Setup default models for existing providers."""
        # Gemini models
        self.register_model(ModelInfo(
            model_id="gemini-3.7-flash",
            provider_id="gemini",
            display_name="Gemini 3.7 Flash",
            description="Google's Gemini 3.7 Flash model",
            capabilities=["text-generation"],
            context_length=32768
        ))
        
        # Groq models
        self.register_model(ModelInfo(
            model_id="openai/gpt-oss-20b",
            provider_id="groq",
            display_name="Groq GPT-OSS 20B",
            description="Groq's GPT-OSS 20B model",
            capabilities=["text-generation"],
            context_length=8192
        ))
        
        # Add another Groq model for variety
        self.register_model(ModelInfo(
            model_id="mixtral-8x7b-32768",
            provider_id="groq",
            display_name="Groq Mixtral 8x7B",
            description="Groq's Mixtral 8x7B model",
            capabilities=["text-generation"],
            context_length=32768
        ))
        
        # OpenRouter models
        self.register_model(ModelInfo(
            model_id="openrouter/free",
            provider_id="openrouter",
            display_name="OpenRouter Free Model",
            description="OpenRouter's free tier model",
            capabilities=["text-generation"],
            context_length=4096
        ))
        
        # Local model
        self.register_model(ModelInfo(
            model_id="local",
            provider_id="local",
            display_name="Local Model",
            description="Local fallback model",
            capabilities=["text-generation"],
            context_length=2048
        ))
    
    def register_model(self, model_info: ModelInfo) -> None:
        """Register a model."""
        provider_id = model_info.provider_id
        model_id = model_info.model_id
        
        if provider_id not in self._models:
            self._models[provider_id] = {}
        
        self._models[provider_id][model_id] = model_info
        self._model_to_provider[model_id] = provider_id
    
    def unregister_model(self, provider_id: str, model_id: str) -> bool:
        """Unregister a model."""
        if provider_id in self._models and model_id in self._models[provider_id]:
            del self._models[provider_id][model_id]
            if model_id in self._model_to_provider:
                del self._model_to_provider[model_id]
            # Clean up empty provider dict
            if not self._models[provider_id]:
                del self._models[provider_id]
            return True
        return False
    
    def get_model(self, provider_id: str, model_id: str) -> Optional[ModelInfo]:
        """Get information about a specific model."""
        if provider_id in self._models and model_id in self._models[provider_id]:
            return self._models[provider_id][model_id]
        return None
    
    def get_model_by_id(self, model_id: str) -> Optional[ModelInfo]:
        """Get model information by model ID (searches across providers)."""
        if model_id in self._model_to_provider:
            provider_id = self._model_to_provider[model_id]
            return self.get_model(provider_id, model_id)
        return None
    
    def list_models(self, provider_id: Optional[str] = None) -> List[ModelInfo]:
        """List all models, optionally filtered by provider."""
        if provider_id:
            if provider_id in self._models:
                return list(self._models[provider_id].values())
            return []
        
        # Return all models
        all_models = []
        for provider_models in self._models.values():
            all_models.extend(provider_models.values())
        return all_models
    
    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models (from enabled and configured providers)."""
        available_models = []
        
        # Get enabled providers from provider registry
        enabled_providers = self.provider_registry.get_enabled_providers()
        
        for provider_id in enabled_providers:
            if provider_id in self._models:
                for model_info in self._models[provider_id].values():
                    # Check if the provider itself is available
                    provider = self.provider_registry.get(provider_id)
                    if provider and provider.is_available():
                        available_models.append(model_info)
        
        return available_models
    
    def get_default_model(self, provider_id: str) -> Optional[str]:
        """Get the default model for a provider."""
        # Check if we have a specific default configured
        provider_config = self.provider_registry.get_config(provider_id)
        if provider_config and provider_config.default_model:
            model_info = self.get_model(provider_id, provider_config.default_model)
            if model_info:
                return model_info.model_id
        
        # Fallback to first available model for the provider
        if provider_id in self._models:
            models = list(self._models[provider_id].values())
            if models:
                return models[0].model_id
        
        return None
    
    def get_models_by_capability(self, capability: str) -> List[ModelInfo]:
        """Get models that support a specific capability."""
        matching_models = []
        
        enabled_providers = self.provider_registry.get_enabled_providers()
        
        for provider_id in enabled_providers:
            provider = self.provider_registry.get(provider_id)
            if provider and provider.is_available():
                if provider_id in self._models:
                    for model_info in self._models[provider_id].values():
                        if capability in model_info.capabilities:
                            matching_models.append(model_info)
        
        return matching_models
    
    def clear(self) -> None:
        """Clear all model registrations."""
        self._models.clear()
        self._model_to_provider.clear()


def create_model_registry(provider_registry: ProviderRegistryEnhanced) -> ModelRegistry:
    """Factory function to create a model registry."""
    return ModelRegistry(provider_registry)