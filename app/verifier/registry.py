from uuid import UUID

from .base import Verifier


class VerifierRegistry:
    """Registry mapping goal IDs to Verifier instances."""
    _mapping: dict[UUID, Verifier] = {}

    @classmethod
    def register(cls, goal_id: UUID, verifier: Verifier) -> None:
        cls._mapping[goal_id] = verifier

    @classmethod
    def get(cls, goal_id: UUID) -> Verifier:
        verifier = cls._mapping.get(goal_id)
        if verifier is None:
            raise KeyError(f"No verifier registered for goal {goal_id}")
        return verifier