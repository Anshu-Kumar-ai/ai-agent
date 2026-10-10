"""Enhanced SmartRouter - Stage 32 Phase 2
Adapts the existing SmartRouter to use the new provider registry and model registry.
"""

import time
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from app.core.providers import ProviderType
from app.extensions.provider_registry import ProviderRegistryEnhanced
from app.extensions.model_registry import ModelRegistry, ModelInfo
from app.extensions.provider_health import ProviderHealthTracker
from app.extensions.contracts import ProviderInterface


class RoutingStrategy(Enum):
    """Routing strategies for provider selection."""
    PRIORITY = "priority"      # Use configured priority
    HEALTH = "health"          # Select healthiest provider
    LOAD_BALANCED = "load_balanced"  # Distribute load
    ROUND_ROBIN = "round_robin"      # Round robin selection


class ProviderSelection:
    """Represents a selected provider and model."""
    
    def __init__(
        self,
        provider_id: str,
        model_id: str,
        provider_instance: ProviderInterface,
        model_info: ModelInfo
    ):
        self.provider_id = provider_id
        self.model_id = model_id
        self.provider_instance = provider_instance
        self.model_info = model_info
        self.selected_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "provider_display_name": self.model_info.provider_id,  # This would come from config
            "model_display_name": self.model_info.display_name,
            "selected_at": self.selected_at
        }


class EnhancedSmartRouter:
    """
    Enhanced SmartRouter that uses the new provider registry system.
    Maintains backward compatibility with existing interfaces.
    """
    
    def __init__(
        self,
        provider_registry: Optional[ProviderRegistryEnhanced] = None,
        model_registry: Optional[ModelRegistry] = None,
        health_tracker: Optional[ProviderHealthTracker] = None,
        strategy: RoutingStrategy = RoutingStrategy.PRIORITY
    ):
        # Initialize registries if not provided
        if provider_registry is None:
            from app.extensions.provider_registry import get_provider_registry
            provider_registry = get_provider_registry()
        
        if model_registry is None:
            model_registry = ModelRegistry(provider_registry)
        
        if health_tracker is None:
            health_tracker = ProviderHealthTracker()
        
        self.provider_registry = provider_registry
        self.model_registry = model_registry
        self.health_tracker = health_tracker
        self.strategy = strategy
        
        # Round robin state
        self._rr_index = 0
        
        # Initialize provider registry with default providers
        self._ensure_default_providers_registered()
    
    def _ensure_default_providers_registered(self):
        """Ensure default providers are registered in the registry."""
        # Register all configured providers
        self.provider_registry.register_all_configured()
    
    def route_request(
        self,
        message: str,
        preferred_provider: Optional[str] = None,
        preferred_model: Optional[str] = None,
        required_capabilities: List[str] = None
    ) -> Tuple[ProviderInterface, ModelInfo]:
        """
        Route a request to the best available provider and model.
        
        Returns:
            Tuple of (provider_instance, model_info)
        """
        required_capabilities = required_capabilities or ["text-generation"]
        
        # Step 1: Filter providers by availability and configuration
        available_providers = self._get_available_providers()
        
        if not available_providers:
            raise RuntimeError("No providers are available")
        
        # Step 2: Filter by preferred provider if specified
        if preferred_provider:
            if preferred_provider in available_providers:
                available_providers = [preferred_provider]
            else:
                # Preferred provider not available, continue with all available
                pass
        
        # Step 3: Get models for available providers that match requirements
        candidate_models = self._get_candidate_models(
            available_providers, 
            required_capabilities
        )
        
        if not candidate_models:
            raise RuntimeError(f"No models available for capabilities: {required_capabilities}")
        
        # Step 4: Filter by preferred model if specified
        if preferred_model:
            preferred_candidates = [
                m for m in candidate_models 
                if m.model_id == preferred_model
            ]
            if preferred_candidates:
                candidate_models = preferred_candidates
            # If preferred model not available, continue with all candidates
        
        # Step 5: Select best candidate based on strategy
        selected_model = self._select_best_model(candidate_models, message)
        
        # Step 6: Get provider instance
        provider_instance = self.provider_registry.get(selected_model.provider_id)
        if not provider_instance:
            # Try to register and get the provider
            if self.provider_registry.register_from_config(selected_model.provider_id):
                provider_instance = self.provider_registry.get(selected_model.provider_id)
        
        if not provider_instance:
            raise RuntimeError(f"Could not get provider instance for {selected_model.provider_id}")
        
        return provider_instance, selected_model
    
    def _get_available_providers(self) -> List[str]:
        """Get list of provider IDs that are available and configured."""
        available = []
        
        for provider_id in self.provider_registry.get_enabled_providers():
            # Check if provider is configured and available
            config = self.provider_registry.get_config(provider_id)
            if config and config.is_configured():
                # Try to get/register the provider
                provider = self.provider_registry.get(provider_id)
                if not provider:
                    # Try to register it
                    if self.provider_registry.register_from_config(provider_id):
                        provider = self.provider_registry.get(provider_id)
                
                if provider and provider.is_available():
                    available.append(provider_id)
        
        return available
    
    def _get_candidate_models(
        self, 
        provider_ids: List[str], 
        required_capabilities: List[str]
    ) -> List[ModelInfo]:
        """Get models that match the required capabilities from available providers."""
        candidates = []
        
        for provider_id in provider_ids:
            # Get models for this provider that match capabilities
            models = self.model_registry.get_models_by_capability(
                required_capabilities[0] if required_capabilities else "text-generation"
            )
            
            # Filter to only models from this provider
            provider_models = [
                m for m in models 
                if m.provider_id == provider_id
            ]
            
            # Check if provider is actually available
            provider = self.provider_registry.get(provider_id)
            if provider and provider.is_available():
                candidates.extend(provider_models)
        
        return candidates
    
    def _select_best_model(
        self, 
        candidates: List[ModelInfo], 
        message: str
    ) -> ModelInfo:
        """Select the best model based on the routing strategy."""
        if not candidates:
            raise ValueError("No candidates to select from")
        
        if self.strategy == RoutingStrategy.PRIORITY:
            # Sort by provider priority (lower number = higher priority)
            def get_priority(model_info):
                config = self.provider_registry.get_config(model_info.provider_id)
                return config.priority if config else 999
            
            return min(candidates, key=get_priority)
        
        elif self.strategy == RoutingStrategy.HEALTH:
            # Select the healthiest provider
            def get_health_score(model_info):
                metrics = self.health_tracker.get_metrics(
                    model_info.provider_id, 
                    model_info.model_id
                )
                if metrics:
                    return metrics.get_health_score()
                return 50.0  # Default neutral score
            
            return max(candidates, key=get_health_score)
        
        elif self.strategy == RoutingStrategy.LOAD_BALANCED:
            # Select provider with least recent usage
            def get_usage_score(model_info):
                metrics = self.health_tracker.get_metrics(
                    model_info.provider_id, 
                    model_info.model_id
                )
                if metrics:
                    # Lower success rate = higher usage (inverted)
                    return 100.0 - metrics.get_success_rate()
                return 50.0
            
            return min(candidates, key=get_usage_score)
        
        elif self.strategy == RoutingStrategy.ROUND_ROBIN:
            # Simple round robin across providers
            provider_ids = list(set(m.provider_id for m in candidates))
            if not provider_ids:
                return candidates[0]
            
            # Select provider based on round robin
            selected_provider = provider_ids[self._rr_index % len(provider_ids)]
            self._rr_index += 1
            
            # Return first model from selected provider
            provider_models = [m for m in candidates if m.provider_id == selected_provider]
            return provider_models[0] if provider_models else candidates[0]
        
        else:
            # Default to first candidate
            return candidates[0]
    
    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics about provider availability and health."""
        stats = {
            "total_providers_configured": len(self.provider_registry.list_configs()),
            "providers_enabled": len(self.provider_registry.get_enabled_providers()),
            "providers_available": len(self._get_available_providers()),
            "total_models": len(self.model_registry.list_models()),
            "available_models": len(self.model_registry.get_available_models()),
            "routing_strategy": self.strategy.value,
            "provider_details": []
        }
        
        # Add details for each provider
        for config in self.provider_registry.list_configs():
            provider_id = config["provider_id"]
            provider = self.provider_registry.get(provider_id)
            
            health_metrics = self.health_tracker.get_metrics(
                provider_id, 
                provider.model_id if provider else "unknown"
            ) if provider else None
            
            provider_detail = {
                "provider_id": provider_id,
                "display_name": config["display_name"],
                "enabled": config["enabled"],
                "configured": config["is_configured"],
                "registered": provider_id in self.provider_registry._providers,
                "available": provider.is_available() if provider else False,
                "priority": config["priority"],
                "default_model": config["default_model"]
            }
            
            if health_metrics:
                provider_detail.update({
                    "health_score": health_metrics.get_health_score(),
                    "success_rate": health_metrics.get_success_rate(),
                    "consecutive_failures": health_metrics.consecutive_failures,
                    "available_now": health_metrics.is_available_now()
                })
            
            stats["provider_details"].append(provider_detail)
        
        return stats
    
    def record_provider_success(
        self, 
        provider_id: str, 
        model_id: str, 
        latency_ms: float
    ):
        """Record a successful provider invocation."""
        self.health_tracker.record_success(provider_id, model_id, latency_ms)
    
    def record_provider_failure(
        self, 
        provider_id: str, 
        model_id: str, 
        exception: Exception, 
        latency_ms: float
    ):
        """Record a failed provider invocation."""
        self.health_tracker.record_failure(provider_id, model_id, exception, latency_ms)


# Global instance
_enhanced_smart_router: Optional[EnhancedSmartRouter] = None


def get_enhanced_smart_router() -> EnhancedSmartRouter:
    """Get or create the global enhanced smart router."""
    global _enhanced_smart_router
    if _enhanced_smart_router is None:
        _enhanced_smart_router = EnhancedSmartRouter()
    return _enhanced_smart_router


def route_llm_request(
    message: str,
    preferred_provider: Optional[str] = None,
    preferred_model: Optional[str] = None,
    required_capabilities: List[str] = None
) -> Tuple[ProviderInterface, ModelInfo]:
    """
    Convenience function to route an LLM request using the global router.
    
    Returns:
        Tuple of (provider_instance, model_info)
    """
    router = get_enhanced_smart_router()
    return router.route_request(message, preferred_provider, preferred_model, required_capabilities)