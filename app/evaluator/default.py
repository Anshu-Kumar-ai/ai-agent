
from ...core.state.action import Action
from ...core.state.evaluation import EvaluationEnum, ProgressInfo
from ...core.state.goal_state import Goal
from ...core.state.observation import Observation, ToolStatus
from .base import Evaluator


class DefaultEvaluator(Evaluator):
    """Default evaluator that assesses the outcome of an action."""

    def evaluate(
        self,
        action: Action,
        observation: Observation,
        goal: Goal,
        pre_task_state: dict
    ) -> tuple[EvaluationEnum, ProgressInfo | None]:
        if observation.status == ToolStatus.SUCCESS:
            progress = ProgressInfo(
                metric_name="side_effects_count",
                value=float(len(observation.side_effects)),
                delta=float(len(observation.side_effects)),
                details={"side_effects": observation.side_effects}
            )
            return EvaluationEnum.TOOL_SUCCEEDED, progress
        if observation.status == ToolStatus.PERMISSION_DENIED:
            return EvaluationEnum.ACTION_FAILED, None
        if observation.status == ToolStatus.TOOL_NOT_FOUND:
            return EvaluationEnum.ACTION_FAILED, None
        # For any other non-success status (ERROR, TIMEOUT) we treat as action failed.
        return EvaluationEnum.ACTION_FAILED, None
