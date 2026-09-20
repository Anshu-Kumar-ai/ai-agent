"""
JSON persistence for the Orchestrator state.
"""

import json
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from myagent.core.orchestrator import Orchestrator
from myagent.core.state.agent_state import TaskGoalState, ConversationState
from myagent.core.state.goal_state import Goal, SuccessSpec
from myagent.core.state.action import Action, SandboxSpec, RetryPolicy
from myagent.core.state.observation import Observation, ToolStatus
from myagent.core.state.evaluation import EvaluationEnum, ProgressInfo
from myagent.core.state.reflection import Reflection
from myagent.core.state.next_action import NextAction, NextActionType
from myagent.core.state.attempt import Attempt


def _extract_state(orchestrator: Orchestrator) -> Dict[str, Any]:
    """Extract the serializable state from the orchestrator."""
    state = {
        "task_state": orchestrator.task_state.to_dict(),
        "conv_state": orchestrator.conv_state.to_dict(),
        "_consecutive_no_progress": orchestrator._consecutive_no_progress,
        "_replans_without_progress": orchestrator._replans_without_progress,
        "_last_progress_attempt_id": str(orchestrator._last_progress_attempt_id)
        if orchestrator._last_progress_attempt_id is not None
        else None,
    }
    return state


def _restore_state(orchestrator: Orchestrator, state: Dict[str, Any]) -> None:
    """Restore the orchestrator's state from the serialized state."""
    orchestrator.task_state = TaskGoalState.from_dict(state["task_state"])
    orchestrator.conv_state = ConversationState.from_dict(state["conv_state"])
    orchestrator._consecutive_no_progress = state["_consecutive_no_progress"]
    orchestrator._replans_without_progress = state["_replans_without_progress"]
    last_progress_attempt_id = state["_last_progress_attempt_id"]
    orchestrator._last_progress_attempt_id = (
        UUID(last_progress_attempt_id) if last_progress_attempt_id is not None else None
    )


def save_state(orchestrator: Orchestrator, filepath: str | Path) -> None:
    """Save the orchestrator's state to a JSON file."""
    state = _extract_state(orchestrator)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def load_state(orchestrator: Orchestrator, filepath: str | Path) -> None:
    """Load the orchestrator's state from a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        state = json.load(f)
    _restore_state(orchestrator, state)