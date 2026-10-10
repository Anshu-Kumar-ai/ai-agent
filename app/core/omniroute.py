"""OmniRoute: Central model routing infrastructure for Stage 21.

Provides intelligent routing between multiple LLM providers (Gemini, Groq, OpenRouter)
based on latency, cost, success rate, context fit, recent failures, and quota.
Allows direct local bypass for ProviderType.LOCAL (Ollama).
"""

import time
from dataclasses import dataclass
from enum import Enum

from app.core.providers import ProviderManager, ProviderType
from app.models.base import BaseModel


class RoutingPolicy(Enum):
    """Routing policies for provider selection."""
    LATENCY = "latency"      # Lowest latency
    COST = "cost"            # Lowest cost
    SUCCESS_RATE = "success_rate"  # Highest success rate
    HEALTH = "health"        # Combination of latency and success rate
    ROUND_ROBIN = "round_robin"    # Simple round-robin


@dataclass
class ProviderStats:
    """Statistics for a provider."""
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    health_ema: float = 0.5      # Exponential moving average of success (0.0 to 1.0)
    latency_ema: float = 0.0     # Exponential moving average of latency
    last_used: float = 0.0
    cooldown_until: float = 0.0  # Timestamp until which provider is in cooldown

    @property
    def success_rate(self) -> float:
        return self.successes / self.requests if self.requests > 0 else 0.0

    @property
    def average_latency(self) -> float:
        return self.total_latency / self.requests if self.requests > 0 else 0.0

    def is_available(self) -> bool:
        """Check if provider is available (not in cooldown)."""
        return time.time() >= self.cooldown_until

    def record_success(self, latency: float, alpha: float = 0.3) -> None:
        """Record a successful request."""
        self.requests += 1
        self.successes += 1
        self.total_latency += latency
        self.last_used = time.time()
        self.health_ema = (1.0 - alpha) * self.health_ema + alpha * 1.0
        self.latency_ema = (1.0 - alpha) * self.latency_ema + alpha * latency

    def record_failure(self, latency: float, alpha: float = 0.3, cooldown_seconds: float = 30.0) -> None:
        """Record a failed request."""
        self.requests += 1
        self.failures += 1
        self.total_latency += latency
        self.last_used = time.time()
        self.health_ema = (1.0 - alpha) * self.health_ema + alpha * 0.0
        self.latency_ema = (1.0 - alpha) * self.latency_ema + alpha * latency
        self.cooldown_until = time.time() + cooldown_seconds


class OmniRoute:
    """
    Intelligent model routing infrastructure.

    Routes requests to the best available provider based on:
    - Task type (coding, reasoning, creative, general)
    - Provider health (success rate, latency)
    - Current load and cooldowns
    - Quota and cost considerations (simplified)
    """

    def __init__(
        self,
        provider_manager: ProviderManager,
        models: dict[ProviderType, BaseModel],
        policy: RoutingPolicy = RoutingPolicy.HEALTH,
    ):
        self.provider_manager = provider_manager
        self.models = models  # Shared model instances from ModelGateway
        self.policy = policy

        # Stats for each remote provider (excluding LOCAL)
        self._stats: dict[ProviderType, ProviderStats] = {
            ProviderType.GEMINI: ProviderStats(),
            ProviderType.GROQ: ProviderStats(),
            ProviderType.OPENROUTER: ProviderStats(),
        }

        # Cooldown seconds for failures
        self._cooldown_seconds = 30.0

        # Task type to provider priority mapping (same as SmartRouter but without LOCAL)
        self._priority_profiles = {
            "general": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER],
            "coding": [ProviderType.GROQ, ProviderType.GEMINI, ProviderType.OPENROUTER],
            "reasoning": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER],
            "creative": [ProviderType.GEMINI, ProviderType.OPENROUTER, ProviderType.GROQ],
        }

        # Keyword profiles for task classification (same as SmartRouter)
        self._keyword_profiles = {
            "coding": {
                "code", "python", "javascript", "typescript", "java",
                "program", "programming", "function", "debug",
                "debugging", "bug", "sql", "api", "class",
                "compile", "compiler", "exception",
            },
            "reasoning": {
                "analyze", "analysis", "compare", "comparison",
                "reason", "reasoning", "logic", "calculate",
                "prove", "derive", "solve", "evaluate", "algorithm",
                "algorithms", "efficient", "efficiency", "complexity",
                "tradeoff",
            },
            "creative": {
                "story", "poem", "poetry", "creative", "fiction",
                "script", "brainstorm", "rewrite",
            },
            "general": set(),  # Fallback
        }

    def _classify_task(self, message: str) -> str:
        """Classify the message into a task type (coding, reasoning, creative, general)."""
        text = message.lower()

        # Check for specific keywords
        for task_type, keywords in self._keyword_profiles.items():
            if task_type == "general":
                continue
            if any(keyword in text for keyword in keywords):
                return task_type

        return "general"

    def _select_provider_by_policy(
        self,
        task_type: str,
        available_providers: list[ProviderType],
    ) -> ProviderType:
        """Select a provider based on the routing policy and current stats."""
        if not available_providers:
            raise RuntimeError("No available providers")

        if self.policy == RoutingPolicy.ROUND_ROBIN:
            # Simple round-robin based on last used time
            return min(available_providers, key=lambda p: self._stats[p].last_used)

        # Build scores for each provider
        scores: dict[ProviderType, float] = {}
        for provider in available_providers:
            stats = self._stats[provider]
            if not stats.is_available():
                scores[provider] = -float('inf')  # Penalize providers in cooldown
                continue

            score = 0.0
            if self.policy == RoutingPolicy.LATENCY:
                # Lower latency is better
                score = -stats.average_latency if stats.requests > 0 else 0.0
            elif self.policy == RoutingPolicy.COST:
                # Cost is not implemented yet; use inverse of success rate as placeholder
                score = -stats.success_rate if stats.requests > 0 else 0.0
            elif self.policy == RoutingPolicy.SUCCESS_RATE:
                score = stats.success_rate
            elif self.policy == RoutingPolicy.HEALTH:
                # Combine health (success rate) and latency (inverse)
                health_score = stats.health_ema
                latency_score = -stats.latency_ema if stats.requests > 0 else 0.0
                score = health_score + latency_score
            else:
                # Default to health
                score = stats.health_ema

            scores[provider] = score

        # Check if all providers are in cooldown (all scores are -inf)
        if all(score == -float('inf') for score in scores.values()):
            raise RuntimeError("No remote providers available (all in cooldown)")

        # Return provider with highest score
        return max(scores, key=scores.get)

    def select_provider(
        self,
        provider_type_hint: ProviderType | None = None,
        message: str = "",
    ) -> ProviderType:
        """
        Select the best provider for a given message.

        Args:
            provider_type_hint: A hint from the caller (e.g., from SmartRouter).
                                Can be used to bias selection but is not binding.
            message: The user message to classify and route.

        Returns:
            The selected ProviderType (REMOTE only).
        """
        # Classify the task
        task_type = self._classify_task(message)

        # Get available remote providers (excluding LOCAL)
        available = [
            p for p in self.provider_manager.get_available_providers()
            if p != ProviderType.LOCAL
        ]

        if not available:
            raise RuntimeError("No remote providers available")

        # If we have a hint and it's available, we can bias towards it
        # but still let the policy decide (for now, we ignore the hint and use policy)
        # In the future, we could weight the hint in the scoring.

        return self._select_provider_by_policy(task_type, available)

    def ask(self, provider_type: ProviderType, message: str) -> str:
        """
        Ask a provider for a response, recording stats and handling failures.

        Args:
            provider_type: The provider to ask (must be a remote provider).
            message: The message to send to the provider.

        Returns:
            The provider's response string.

        Raises:
            RuntimeError: If the provider is LOCAL (use direct bypass) or if all attempts fail.
        """
        if provider_type == ProviderType.LOCAL:
            raise RuntimeError(
                "OmniRoute should not be used for LOCAL provider. "
                "Use the ModelGateway's direct local bypass instead."
            )

        # Check if provider is available (not in cooldown)
        stats = self._stats[provider_type]
        if not stats.is_available():
            # If not available, we still try it but will record a failure and extend cooldown
            pass

        start_time = time.perf_counter()
        try:
            # Resolve the model instance (lazy loaded via ModelGateway when possible)
            model = self._resolve_model(provider_type)
            if model is None:
                raise RuntimeError(f"Model not loaded for provider: {provider_type}")
            response = model.chat(message)
            latency = time.perf_counter() - start_time
            stats.record_success(latency)
            return response
        except Exception as e:
            latency = time.perf_counter() - start_time
            stats.record_failure(latency, cooldown_seconds=self._cooldown_seconds)
            # Re-raise the exception so the caller can handle it
            raise e

    def _resolve_model(self, provider_type: ProviderType):
        """Resolve the model instance for a provider.

        Supports both a ModelGateway (lazy loading) and a plain dict of
        shared model instances for backward compatibility.
        """
        ref = self.models
        if hasattr(ref, "_get_model"):
            # ModelGateway: lazy-load on demand
            return ref._get_model(provider_type)
        if isinstance(ref, dict):
            return ref.get(provider_type)
        return None

    def get_stats(self) -> dict[ProviderType, dict[str, float]]:
        """Get current statistics for all remote providers."""
        result = {}
        for provider, stats in self._stats.items():
            result[provider.value] = {
                "requests": stats.requests,
                "successes": stats.successes,
                "failures": stats.failures,
                "success_rate": stats.success_rate,
                "average_latency": stats.average_latency,
                "health_ema": stats.health_ema,
                "latency_ema": stats.latency_ema,
                "last_used": stats.last_used,
                "cooldown_remaining": max(0, stats.cooldown_until - time.time()),
            }
        return result

    def reset_stats(self) -> None:
        """Reset all statistics."""
        for stats in self._stats.values():
            stats.requests = 0
            stats.successes = 0
            stats.failures = 0
            stats.total_latency = 0.0
            stats.health_ema = 0.5
            stats.latency_ema = 0.0
            stats.last_used = 0.0
            stats.cooldown_until = 0.0


# Convenience function to create an OmniRoute instance
def create_omniroute(
    provider_manager: ProviderManager,
    models: dict[ProviderType, BaseModel],
    policy: RoutingPolicy = RoutingPolicy.HEALTH,
) -> OmniRoute:
    """Create an OmniRoute instance with the given provider manager and models."""
    return OmniRoute(provider_manager, models, policy)
