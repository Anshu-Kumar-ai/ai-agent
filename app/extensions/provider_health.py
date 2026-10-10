"""Provider Health Tracking - Stage 32 Phase 2
Lightweight provider health abstraction for tracking availability and performance.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import time
import threading
from collections import defaultdict


@dataclass
class ProviderHealthMetrics:
    """Health metrics for a provider."""
    
    provider_id: str
    model_id: str
    
    # Availability tracking
    available: bool = True
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    
    # Performance tracking
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0  # in milliseconds
    
    # Failure categorization
    failure_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_failure_category: str = ""
    
    # Cooldown/backoff state
    in_cooldown: bool = False
    cooldown_until: float = 0.0
    base_cooldown_seconds: float = 30.0
    max_cooldown_seconds: float = 300.0
    
    def record_success(self, latency_ms: float):
        """Record a successful request."""
        self.available = True
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.in_cooldown = False
        self.cooldown_until = 0.0
        
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency += latency_ms
        
        # Clear failure category on success
        self.last_failure_category = ""
    
    def record_failure(self, exception: Exception, latency_ms: float):
        """Record a failed request."""
        from app.extensions.provider_adapter import ProviderAdapter
        
        # Classify the failure
        adapter = ProviderAdapter.__new__(ProviderAdapter)  # Create instance without calling __init__
        failure_category = adapter.classify_failure(exception)
        
        self.available = False
        self.last_failure_time = time.time()
        self.consecutive_failures += 1
        self.last_failure_category = failure_category
        
        self.total_requests += 1
        self.failed_requests += 1
        self.total_latency += latency_ms
        
        # Update failure counts
        self.failure_counts[failure_category] += 1
        
        # Apply cooldown/backoff
        self._apply_cooldown()
    
    def _apply_cooldown(self):
        """Apply exponential backoff cooldown."""
        if self.consecutive_failures >= 1:
            # Exponential backoff: base * (2^(failures-1)), capped at max
            cooldown = self.base_cooldown_seconds * (2 ** (self.consecutive_failures - 1))
            cooldown = min(cooldown, self.max_cooldown_seconds)
            
            self.in_cooldown = True
            self.cooldown_until = time.time() + cooldown
    
    def is_available_now(self) -> bool:
        """Check if provider is currently available (not in cooldown)."""
        if not self.available:
            return False
        
        if self.in_cooldown and time.time() < self.cooldown_until:
            return False
        
        # If cooldown period has passed, reset cooldown state
        if self.in_cooldown and time.time() >= self.cooldown_until:
            self.in_cooldown = False
            self.cooldown_until = 0.0
        
        return True
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    def get_average_latency(self) -> float:
        """Get average latency in milliseconds."""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency / self.successful_requests
    
    def get_health_score(self) -> float:
        """Get overall health score (0-100)."""
        if self.total_requests == 0:
            return 50.0  # Neutral score for no requests
        
        # Base score on success rate
        success_rate_score = self.get_success_rate()
        
        # Penalize for recent failures
        time_since_last_failure = time.time() - self.last_failure_time
        recency_penalty = min(30.0, 30.0 * (1.0 / (1.0 + time_since_last_failure / 300.0)))  # Max 30pt penalty
        
        # Penalize for being in cooldown
        cooldown_penalty = 20.0 if self.in_cooldown and time.time() < self.cooldown_until else 0.0
        
        # Calculate final score
        score = success_rate_score - recency_penalty - cooldown_penalty
        return max(0.0, min(100.0, score))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for monitoring/display."""
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "available": self.available,
            "available_now": self.is_available_now(),
            "consecutive_failures": self.consecutive_failures,
            "success_rate": round(self.get_success_rate(), 2),
            "average_latency_ms": round(self.get_average_latency(), 2),
            "health_score": round(self.get_health_score(), 2),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "last_failure_category": self.last_failure_category,
            "in_cooldown": self.in_cooldown,
            "cooldown_remaining": max(0, self.cooldown_until - time.time()) if self.in_cooldown else 0
        }


class ProviderHealthTracker:
    """Tracks health for all providers."""
    
    def __init__(self):
        self._health_metrics: Dict[str, ProviderHealthMetrics] = {}
        self._lock = threading.RLock()
    
    def get_or_create_metrics(self, provider_id: str, model_id: str) -> ProviderHealthMetrics:
        """Get or create health metrics for a provider/model combination."""
        key = f"{provider_id}:{model_id}"
        with self._lock:
            if key not in self._health_metrics:
                self._health_metrics[key] = ProviderHealthMetrics(
                    provider_id=provider_id,
                    model_id=model_id
                )
            return self._health_metrics[key]
    
    def record_success(self, provider_id: str, model_id: str, latency_ms: float):
        """Record a successful request."""
        metrics = self.get_or_create_metrics(provider_id, model_id)
        metrics.record_success(latency_ms)
    
    def record_failure(self, provider_id: str, model_id: str, exception: Exception, latency_ms: float):
        """Record a failed request."""
        metrics = self.get_or_create_metrics(provider_id, model_id)
        metrics.record_failure(exception, latency_ms)
    
    def get_metrics(self, provider_id: str, model_id: str) -> Optional[ProviderHealthMetrics]:
        """Get health metrics for a provider/model."""
        key = f"{provider_id}:{model_id}"
        with self._lock:
            return self._health_metrics.get(key)
    
    def get_all_metrics(self) -> Dict[str, ProviderHealthMetrics]:
        """Get all health metrics."""
        with self._lock:
            return self._health_metrics.copy()
    
    def get_available_providers(self) -> List[str]:
        """Get list of provider IDs that are currently available."""
        available = []
        with self._lock:
            for key, metrics in self._health_metrics.items():
                if metrics.is_available_now():
                    provider_id = metrics.provider_id
                    if provider_id not in available:
                        available.append(provider_id)
        return available
    
    def clear(self):
        """Clear all health metrics."""
        with self._lock:
            self._health_metrics.clear()


# Global instance
_health_tracker: Optional[ProviderHealthTracker] = None


def get_provider_health_tracker() -> ProviderHealthTracker:
    """Get or create the global provider health tracker."""
    global _health_tracker
    if _health_tracker is None:
        _health_tracker = ProviderHealthTracker()
    return _health_tracker


def reset_provider_health():
    """Reset all provider health metrics (for testing)."""
    tracker = get_provider_health_tracker()
    tracker.clear()