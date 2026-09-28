from dataclasses import dataclass


@dataclass
class Evaluation:
    """A validated evaluation of the agent's performance.

    Attributes:
        score: A float between 0.0 and 1.0 indicating the quality of the response.
        feedback: A string providing suggestions for improvement.
        criteria_met: A list of strings describing which criteria were satisfied.
        criteria_not_met: A list of strings describing which criteria were not satisfied.
    """

    score: float
    feedback: str
    criteria_met: list[str]
    criteria_not_met: list[str]

    def __post_init__(self):
        if not isinstance(self.score, float) or not (0.0 <= self.score <= 1.0):
            raise ValueError("score must be a float between 0.0 and 1.0")
        if not isinstance(self.feedback, str) or not self.feedback.strip():
            raise ValueError("feedback must be a non-empty string")
        if not isinstance(self.criteria_met, list) or not all(
            isinstance(c, str) for c in self.criteria_met
        ):
            raise TypeError("criteria_met must be a list of strings")
        if not isinstance(self.criteria_not_met, list) or not all(
            isinstance(c, str) for c in self.criteria_not_met
        ):
            raise TypeError("criteria_not_met must be a list of strings")

    def is_good_enough(self, threshold: float = 0.7) -> bool:
        """Return True if the score meets or exceeds the threshold."""
        return self.score >= threshold

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return (
            f"Evaluation(score={self.score:.2f}, feedback='{self.feedback}', "
            f"criteria_met={self.criteria_met}, criteria_not_met={self.criteria_not_met})"
        )