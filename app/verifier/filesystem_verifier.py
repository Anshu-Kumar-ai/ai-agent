
import os

from ...core.state.agent_state import TaskGoalState
from ...core.state.goal_state import Goal
from .base import VerificationResult, Verifier


class FileExistsVerifier(Verifier):
    """Verifies that a file exists at the given path."""
    def verify(self, goal: Goal, task_state: TaskGoalState) -> VerificationResult:
        criteria = goal.success_criteria.criteria
        path = criteria.get("expected_path")
        if not path:
            return VerificationResult(success=False, detail="Missing 'expected_path' in success criteria")
        # If path is relative, treat as relative to current working directory
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        if os.path.isfile(path):
            return VerificationResult(success=True, detail=f"File exists: {path}")
        else:
            return VerificationResult(success=False, detail=f"File not found: {path}")


class FileContentVerifier(Verifier):
    """Verifies that a file exists and its content matches the expected string."""
    def verify(self, goal: Goal, task_state: TaskGoalState) -> VerificationResult:
        criteria = goal.success_criteria.criteria
        path = criteria.get("expected_path")
        expected = criteria.get("expected_content")
        if not path:
            return VerificationResult(success=False, detail="Missing 'expected_path' in success criteria")
        if expected is None:
            return VerificationResult(success=False, detail="Missing 'expected_content' in success criteria")
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        if not os.path.isfile(path):
            return VerificationResult(success=False, detail=f"File not found: {path}")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return VerificationResult(success=False, detail=f"Error reading file: {e}")
        if content == expected:
            return VerificationResult(success=True, detail=f"File content matches: {path}")
        else:
            return VerificationResult(success=False, detail=f"File content mismatch for {path}")


class FileMovedVerifier(Verifier):
    """Verifies that a file has been moved from source to destination (source gone, destination exists)."""
    def verify(self, goal: Goal, task_state: TaskGoalState) -> VerificationResult:
        criteria = goal.success_criteria.criteria
        src = criteria.get("source_path")
        dst = criteria.get("destination_path")
        if not src:
            return VerificationResult(success=False, detail="Missing 'source_path' in success criteria")
        if not dst:
            return VerificationResult(success=False, detail="Missing 'destination_path' in success criteria")
        if not os.path.isabs(src):
            src = os.path.abspath(src)
        if not os.path.isabs(dst):
            dst = os.path.abspath(dst)
        src_exists = os.path.isfile(src)
        dst_exists = os.path.isfile(dst)
        if not src_exists and dst_exists:
            return VerificationResult(success=True, detail=f"File moved from {src} to {dst}")
        else:
            return VerificationResult(
                success=False,
                detail=f"Move not completed: source exists={src_exists}, destination exists={dst_exists}"
            )


# You can add more verifiers as needed, e.g., DirectoryExists, PathListMatches, etc.