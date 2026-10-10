"""Provider Configuration Model - Stage 32 Phase 2
Defines the structured configuration for providers.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class ProviderConfiguration:
    """Structured configuration for a provider."""
    
    provider_id: str
    display_name: str
    adapter_class: str  # Class name as string for dynamic loading
    api_key_env: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    default_model: str = ""
    capabilities: List[str] = field(default_factory=list)
    # Additional metadata
    description: str = ""
    version: str = "1.0.0"
    
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        if not self.api_key_env:
            return True  # No API key needed
        return bool(os.getenv(self.api_key_env))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "adapter_class": self.adapter_class,
            "api_key_env": self.api_key_env,
            "enabled": self.enabled,
            "priority": self.priority,
            "default_model": self.default_model,
            "capabilities": self.capabilities,
            "description": self.description,
            "version": self.version,
            "is_configured": self.is_configured()
        }


# Default provider configurations
DEFAULT_PROVIDER_CONFIGURATIONS = [
    ProviderConfiguration(
        provider_id="gemini",
        display_name="Gemini",
        adapter_class="app.extensions.provider_adapter.GeminiProviderAdapter",
        api_key_env="GEMINI_API_KEY",
        priority=10,
        default_model="gemini-3.7-flash",
        capabilities=["text-generation"],
        description="Google's Gemini LLM provider"
    ),
    ProviderConfiguration(
        provider_id="groq",
        display_name="Groq",
        adapter_class="app.extensions.provider_adapter.GroqProviderAdapter",
        api_key_env="GROQ_API_KEY",
        priority=20,
        default_model="openai/gpt-oss-20b",
        capabilities=["text-generation"],
        description="Groq's fast LLM inference provider"
    ),
    ProviderConfiguration(
        provider_id="openrouter",
        display_name="OpenRouter",
        adapter_class="app.extensions.provider_adapter.OpenRouterProviderAdapter",
        api_key_env="OPENROUTER_API_KEY",
        priority=30,
        default_model="openrouter/free",
        capabilities=["text-generation"],
        description="OpenRouter model aggregator provider"
    ),
    ProviderConfiguration(
        provider_id="local",
        display_name="Local",
        adapter_class="app.extensions.provider_adapter.LocalProviderAdapter",
        api_key_env=None,  # No API key needed
        priority=40,
        default_model="local",
        capabilities=["text-generation"],
        description="Local model fallback provider"
    )
]


def get_default_provider_configs() -> List[ProviderConfiguration]:
    """Get the default provider configurations."""
    return DEFAULT_PROVIDER_CONFIGURATIONS.copy()


def get_provider_config_by_id(provider_id: str) -> Optional[ProviderConfiguration]:
    """Get a provider configuration by ID."""
    for config in DEFAULT_PROVIDER_CONFIGURATIONS:
        if config.provider_id == provider_id:
            return config
    return None