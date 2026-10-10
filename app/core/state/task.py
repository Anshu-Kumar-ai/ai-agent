"""Task State Model - Stage 29: Autonomous Execution Orchestration.

Persistent task execution state with lifecycle management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class TaskStatus(Enum):
    """Lifecycle status of a task."""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    RECOVERING = "recovering"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureCategory(Enum):
    """Categories of execution failures for recovery decisions."""
    TIMEOUT = "timeout"
    TRANSIENT_PROVIDER_FAILURE = "transient_provider_failure"
    TOOL_FAILURE = "tool_failure"
    INVALID_ARGUMENT = "invalid_argument"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    STATE_CHANGED = "state_changed"
    BROWSER_FAILURE = "browser_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    UNKNOWN = "unknown"


@dataclass
class StepExecution:
    """Record of a single step execution attempt."""
    step_id: str
    action: str          # "use_tool" or "respond"
    tool_name: str | None
    arguments: dict
    reason: str
    started_at: float
    ended_at: float | None = None
    success: bool | None = None
    result: Any = None
    error: str | None = None
    failure_category: FailureCategory | None = None
    retry_count: int = 0
    verification_passed: bool | None = None
    verification_details: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize step execution."""
        return {
            "step_id": self.step_id,
            "action": self.action,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "retry_count": self.retry_count,
            "verification_passed": self.verification_passed,
            "verification_details": self.verification_details,
        }


@dataclass
class PlanVersion:
    """A version of the execution plan."""
    version: int
    plan_id: str
    goal: str
    steps: list[StepExecution] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    parent_version: int | None = None  # For replanning traceability

    def to_dict(self) -> dict[str, Any]:
        """Serialize plan version."""
        return {
            "version": self.version,
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
            "parent_version": self.parent_version,
        }


@dataclass
class TaskCheckpoint:
    """Lightweight checkpoint for restart recovery."""
    task_id: str
    plan_version: int
    completed_step_ids: list[str]
    current_step_id: str | None
    observations_summary: list[dict]  # Minimal observation data
    important_results: dict[str, Any]  # Key tool results needed for recovery
    created_at: float = field(default_factory=lambda: datetime.utcnow().timestamp())


@dataclass
class Task:
    """Complete task execution state for autonomous multi-step goals."""
    
    task_id: str
    user_goal: str
    status: TaskStatus = TaskStatus.PENDING
    current_plan: PlanVersion | None = None
    plan_history: list[PlanVersion] = field(default_factory=list)
    completed_step_ids: list[str] = field(default_factory=list)
    failed_step_ids: list[str] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)  # From EnhancedMemory
    permissions_granted: list[str] = field(default_factory=list)
    permissions_denied: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.utcnow().timestamp())
    final_result: Any = None
    error: str | None = None
    
    # Execution limits
    max_steps: int = 10
    max_retries_per_step: int = 2
    max_replans: int = 3
    max_task_duration_seconds: int = 300
    
    # Runtime state
    _current_step: StepExecution | None = field(default=None, repr=False)
    _start_time: float | None = field(default=None, repr=False)
    
    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid4())[:8]
    
    def start(self) -> None:
        """Mark task as started."""
        if self.status != TaskStatus.PENDING:
            raise ValueError(f"Cannot start task in status {self.status}")
        self.status = TaskStatus.PLANNING
        self._start_time = datetime.utcnow().timestamp()
        self.updated_at = self._start_time
    
    def set_plan(self, plan: PlanVersion) -> None:
        """Set the current execution plan."""
        if self.status not in (TaskStatus.PLANNING, TaskStatus.REPLANNING):
            raise ValueError(f"Cannot set plan in status {self.status}")
        self.current_plan = plan
        self.plan_history.append(plan)
        self.status = TaskStatus.RUNNING
        self.updated_at = datetime.utcnow().timestamp()
    
    def replan(self, new_plan: PlanVersion) -> None:
        """Replace current plan with a revised version."""
        if self.status not in (TaskStatus.RUNNING, TaskStatus.RECOVERING, TaskStatus.REPLANNING):
            raise ValueError(f"Cannot replan in status {self.status}")
        if self.current_plan:
            new_plan.parent_version = self.current_plan.version
        self.current_plan = new_plan
        self.plan_history.append(new_plan)
        self.status = TaskStatus.REPLANNING
        self.updated_at = datetime.utcnow().timestamp()
    
    def start_step(self, step: StepExecution) -> None:
        """Begin executing a step."""
        if self.status != TaskStatus.RUNNING:
            raise ValueError(f"Cannot start step in status {self.status}")
        self._current_step = step
        self.updated_at = datetime.utcnow().timestamp()
    
    def complete_step(self, success: bool, result: Any = None, error: str | None = None, 
                      failure_category: FailureCategory | None = None) -> None:
        """Mark current step as completed."""
        if not self._current_step:
            raise ValueError("No current step to complete")
        
        step = self._current_step
        step.ended_at = datetime.utcnow().timestamp()
        step.success = success
        step.result = result
        step.error = error
        step.failure_category = failure_category
        
        if success:
            self.completed_step_ids.append(step.step_id)
            if self.current_plan:
                self.current_plan.steps.append(step)
        else:
            self.failed_step_ids.append(step.step_id)
        
        self.observations.append({
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "result": result,
            "error": error,
            "success": success,
            "timestamp": step.ended_at,
        })
        
        self._current_step = None
        self.updated_at = datetime.utcnow().timestamp()
    
    def verify_step(self, passed: bool, details: str = "") -> None:
        """Record step verification result."""
        # Verification happens after step completion, updates the last completed step
        if self.current_plan and self.current_plan.steps:
            last_step = self.current_plan.steps[-1]
            last_step.verification_passed = passed
            last_step.verification_details = details
        self.updated_at = datetime.utcnow().timestamp()
    
    def wait_for_approval(self, tool_name: str, arguments: dict) -> None:
        """Pause execution waiting for permission approval."""
        if self.status != TaskStatus.RUNNING:
            raise ValueError(f"Cannot wait for approval in status {self.status}")
        self.status = TaskStatus.WAITING_APPROVAL
        self.updated_at = datetime.utcnow().timestamp()
    
    def grant_permission(self, tool_name: str) -> None:
        """Record granted permission."""
        self.permissions_granted.append(tool_name)
        self.status = TaskStatus.RUNNING
        self.updated_at = datetime.utcnow().timestamp()
    
    def deny_permission(self, tool_name: str) -> None:
        """Record denied permission."""
        self.permissions_denied.append(tool_name)
        self.status = TaskStatus.FAILED
        self.error = f"Permission denied for {tool_name}"
        self.updated_at = datetime.utcnow().timestamp()
    
    def enter_recovery(self) -> None:
        """Enter recovery state."""
        if self.status not in (TaskStatus.RUNNING, TaskStatus.RETRYING):
            raise ValueError(f"Cannot enter recovery from status {self.status}")
        self.status = TaskStatus.RECOVERING
        self.updated_at = datetime.utcnow().timestamp()
    
    def exit_recovery(self, success: bool) -> None:
        """Exit recovery state."""
        if self.status != TaskStatus.RECOVERING:
            raise ValueError(f"Cannot exit recovery from status {self.status}")
        self.status = TaskStatus.RUNNING if success else TaskStatus.FAILED
        self.updated_at = datetime.utcnow().timestamp()
    
    def complete(self, result: Any) -> None:
        """Mark task as successfully completed."""
        if self.status not in (TaskStatus.RUNNING, TaskStatus.VERIFYING):
            raise ValueError(f"Cannot complete task in status {self.status}")
        self.status = TaskStatus.COMPLETED
        self.final_result = result
        self.updated_at = datetime.utcnow().timestamp()
    
    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.updated_at = datetime.utcnow().timestamp()
    
    def cancel(self) -> None:
        """Cancel the task."""
        if self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            raise ValueError(f"Cannot cancel task in status {self.status}")
        self.status = TaskStatus.CANCELLED
        self.updated_at = datetime.utcnow().timestamp()
    
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    
    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since task start."""
        if not self._start_time:
            return 0.0
        return datetime.utcnow().timestamp() - self._start_time
    
    def has_exceeded_duration(self) -> bool:
        """Check if task has exceeded max duration."""
        return self.get_elapsed_seconds() > self.max_task_duration_seconds
    
    def create_checkpoint(self) -> TaskCheckpoint:
        """Create a lightweight checkpoint for restart recovery."""
        important_results = {}
        if self.current_plan:
            for step in self.current_plan.steps:
                if step.success and step.result is not None:
                    important_results[step.step_id] = step.result
        
        return TaskCheckpoint(
            task_id=self.task_id,
            plan_version=self.current_plan.version if self.current_plan else 0,
            completed_step_ids=self.completed_step_ids.copy(),
            current_step_id=self._current_step.step_id if self._current_step else None,
            observations_summary=[{
                "step_id": o["step_id"],
                "tool_name": o["tool_name"],
                "success": o["success"],
            } for o in self.observations],
            important_results=important_results,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize task state."""
        return {
            "task_id": self.task_id,
            "user_goal": self.user_goal,
            "status": self.status.value,
            "current_plan": self.current_plan.to_dict() if self.current_plan else None,
            "plan_history": [p.to_dict() for p in self.plan_history],
            "completed_step_ids": self.completed_step_ids,
            "failed_step_ids": self.failed_step_ids,
            "observations": self.observations,
            "attempts": self.attempts,
            "permissions_granted": self.permissions_granted,
            "permissions_denied": self.permissions_denied,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "final_result": self.final_result,
            "error": self.error,
            "max_steps": self.max_steps,
            "max_retries_per_step": self.max_retries_per_step,
            "max_replans": self.max_replans,
            "max_task_duration_seconds": self.max_task_duration_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Deserialize task state."""
        task = cls(
            task_id=data["task_id"],
            user_goal=data["user_goal"],
            status=TaskStatus(data["status"]),
            completed_step_ids=data.get("completed_step_ids", []),
            failed_step_ids=data.get("failed_step_ids", []),
            observations=data.get("observations", []),
            attempts=data.get("attempts", []),
            permissions_granted=data.get("permissions_granted", []),
            permissions_denied=data.get("permissions_denied", []),
            created_at=data.get("created_at", datetime.utcnow().timestamp()),
            updated_at=data.get("updated_at", datetime.utcnow().timestamp()),
            final_result=data.get("final_result"),
            error=data.get("error"),
            max_steps=data.get("max_steps", 10),
            max_retries_per_step=data.get("max_retries_per_step", 2),
            max_replans=data.get("max_replans", 3),
            max_task_duration_seconds=data.get("max_task_duration_seconds", 300),
        )
        
        if data.get("current_plan"):
            task.current_plan = PlanVersion(**data["current_plan"])
        if data.get("plan_history"):
            task.plan_history = [PlanVersion(**p) for p in data["plan_history"]]
        
        return task


# State machine validation
VALID_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_APPROVAL, TaskStatus.VERIFYING, TaskStatus.RETRYING,
        TaskStatus.RECOVERING, TaskStatus.REPLANNING, TaskStatus.COMPLETED,
        TaskStatus.FAILED, TaskStatus.CANCELLED
    },
    TaskStatus.WAITING_APPROVAL: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.VERIFYING: {TaskStatus.RUNNING, TaskStatus.RETRYING, TaskStatus.REPLANNING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RETRYING: {TaskStatus.RUNNING, TaskStatus.RECOVERING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RECOVERING: {TaskStatus.RUNNING, TaskStatus.REPLANNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.REPLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Validate a state transition."""
    return to_status in VALID_TRANSITIONS.get(from_status, set())