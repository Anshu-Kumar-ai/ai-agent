"""
Supervised Repair Loop - Phase 11 Integration
Orchestrates validation, failure analysis, repair proposal, and change management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import hashlib
import json
from app.persistence.execution_journal import ExecutionJournal, ExecutionJournalEntry
import uuid

# Import existing components
from app.extensions.repair_proposal import (
    RepairProposal,
    RepairProposalRequest,
    RepairRiskLevel,
    ValidationStep as RepairValidationStep,
)
from app.extensions.change_proposal import (
    ChangeProposal,
    FileChange,
    ChangeType,
    ProposalStatus,
    RiskLevel,
    ValidationStep as ChangeValidationStep,
    is_command_allowed,
    split_allowed_command,
    validate_workspace_path,
    VALIDATION_COMMAND_ALLOWLIST,
    ApprovalGate,
    ApprovalDecisionStatus,
)
from app.extensions.validation_tools import (
    ValidationTool,
    ValidationRequest,
    ValidationStatus,
    ValidationResult,
)
from app.extensions.failure_analyzer import (
    FailureAnalyzerTool,
    FailureAnalysisRequest,
    FailureAnalysisResult,
)
from app.extensions.change_manager import ChangeManager
from app.core.permissions import PermissionManager
from app.monitoring.emitter import get_emitter


class RepairLoopState(Enum):
    """State machine for the supervised repair loop."""
    INIT = "init"
    VALIDATION_RUNNING = "validation_running"
    VALIDATION_COMPLETED = "validation_completed"
    ANALYSIS_RUNNING = "analysis_running"
    ANALYSIS_COMPLETED = "analysis_completed"
    PROPOSAL_GENERATION = "proposal_generation"
    PROPOSAL_GENERATED = "proposal_generated"
    CONVERSION = "conversion"
    VALIDATION = "validation"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    APPLICATION = "application"
    POST_VALIDATION = "post_validation"
    ROLLBACK = "rollback"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RepairLoopOutcome(Enum):
    """Terminal outcomes for the repair loop."""
    COMPLETED = "completed"
    FAILED_VALIDATION = "failed_validation"
    NO_REPAIR_JUSTIFIED = "no_repair_justified"
    PROPOSAL_REJECTED = "proposal_rejected"
    AWAITING_APPROVAL = "awaiting_approval"
    APPLY_FAILED_ROLLED_BACK = "apply_failed_rolled_back"
    POST_VALIDATION_FAILED_ROLLED_BACK = "post_validation_failed_rolled_back"
    ROLLBACK_INCOMPLETE = "rollback_incomplete"
    CANCELLED = "cancelled"
    MAX_ITERATIONS_EXCEEDED = "max_iterations_exceeded"


@dataclass
class RepairLoopReport:
    """Structured report for the repair loop execution."""
    task_id: str
    workspace_root: str
    loop_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    outcome: Optional[RepairLoopOutcome] = None
    iteration_count: int = 0
    max_iterations: int = 2

    # Step results
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    failure_analysis: Optional[Dict[str, Any]] = None
    repair_proposal: Optional[Dict[str, Any]] = None
    change_proposal: Optional[Dict[str, Any]] = None
    approval_record: Optional[Dict[str, Any]] = None
    applied_changes: List[Dict[str, Any]] = field(default_factory=list)
    rollback_outcome: Optional[Dict[str, Any]] = None
    post_validation_results: List[Dict[str, Any]] = field(default_factory=list)

    # Evidence and uncertainties
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workspace_root": self.workspace_root,
            "loop_id": self.loop_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "outcome": self.outcome.value if self.outcome else None,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "validation_results": self.validation_results,
            "failure_analysis": self.failure_analysis,
            "repair_proposal": self.repair_proposal,
            "change_proposal": self.change_proposal,
            "approval_record": self.approval_record,
            "applied_changes": self.applied_changes,
            "rollback_outcome": self.rollback_outcome,
            "post_validation_results": self.post_validation_results,
            "evidence": self.evidence,
            "uncertainties": self.uncertainties,
        }


def convert_repair_to_change_proposal(
    repair_proposal: RepairProposal,
    task_id: str,
    workspace_root: str,
) -> ChangeProposal:
    """
    Convert a RepairProposal to a ChangeProposal for the ChangeManager pipeline.

    Preserves all paths, content, validation information, and security-relevant metadata.
    Ensures proposal hashes are stable for unchanged proposals and change when
    relevant proposal content changes.

    Args:
        repair_proposal: The RepairProposal to convert
        task_id: Task identifier
        workspace_root: Absolute path to workspace root

    Returns:
        ChangeProposal ready for ChangeManager validation

    Raises:
        ValueError: If repair_proposal has empty changes or code_change_justified is False
    """
    # Validate repair proposal has justified changes
    if not repair_proposal.changes:
        raise ValueError("Cannot convert repair proposal with empty changes")

    if repair_proposal.failure_analysis and not repair_proposal.failure_analysis.code_change_justified:
        raise ValueError("Cannot convert repair proposal where code_change_justified is False")

    # Convert changes
    file_changes = []
    for change in repair_proposal.changes:
        file_changes.append(FileChange(
            target_path=change.target_path,
            change_type=ChangeType(change.change_type.value),
            content=change.content,
            expected_pre_hash=change.expected_pre_hash,
            expected_post_hash=change.expected_post_hash,
        ))

    # Convert validation plan (RepairValidationStep -> ChangeValidationStep)
    validation_plan = []
    for step in repair_proposal.validation_plan:
        validation_plan.append(ChangeValidationStep(
            name=step.name,
            command=step.command,
            description=step.description,
            required=step.required,
            timeout_seconds=step.timeout_seconds,
            working_directory=step.working_directory,
        ))

    # Map risk level
    risk_level_map = {
        RepairRiskLevel.LOW: RiskLevel.LOW,
        RepairRiskLevel.MEDIUM: RiskLevel.MEDIUM,
        RepairRiskLevel.HIGH: RiskLevel.HIGH,
    }

    # Create ChangeProposal
    change_proposal = ChangeProposal(
        proposal_id=f"change-{repair_proposal.proposal_id}",
        task_id=task_id,
        workspace_root=workspace_root,
        changes=file_changes,
        rationale=repair_proposal.rationale,
        risk_level=risk_level_map.get(repair_proposal.risk_level, RiskLevel.MEDIUM),
        validation_plan=validation_plan,
        approval_status=ProposalStatus.DRAFT,
        created_at=repair_proposal.created_at,
        updated_at=repair_proposal.updated_at,
    )

    return change_proposal


class SupervisedRepairLoop:
    """
    Supervised end-to-end repair loop orchestrator.

    Integrates existing validation, failure analysis, repair proposal,
    and change management components into a supervised workflow with
    explicit human approval gates.
    """

    def __init__(
        self,
        workspace_root: str,
        task_id: str,
        permission_manager: Optional[PermissionManager] = None,
        approval_callback: Optional[callable] = None,
        max_iterations: int = 2,
        cancellation_token: Optional[callable] = None,
        approval_expiry_seconds: int = 3600,
        execution_journal: Optional[ExecutionJournal] = None,
    ):
        """
        Initialize the supervised repair loop.

        Args:
            workspace_root: Absolute path to workspace root
            task_id: Unique task identifier
            permission_manager: PermissionManager for approval decisions
            approval_callback: Optional callback(approval_request) -> bool for automated approval
            max_iterations: Maximum loop iterations per task (default 2)
            cancellation_token: Optional callable that returns True when cancelled
            approval_expiry_seconds: Approval request expiry in seconds (default 1 hour)
        """
        self.workspace_root = workspace_root
        self.task_id = task_id
        self.permission_manager = permission_manager
        self.approval_callback = approval_callback
        self.max_iterations = max_iterations
        self.cancellation_token = cancellation_token
        # Initialize execution journal
        if execution_journal is None:
            self.execution_journal = ExecutionJournal()
        else:
            self.execution_journal = execution_journal

        # Initialize components
        self.validation_tool = ValidationTool(permission_manager)
        self.failure_analyzer = FailureAnalyzerTool()
        # Initialize approval gate
        self.approval_gate = ApprovalGate(
            permission_manager=permission_manager,
            default_expiry_seconds=approval_expiry_seconds,
            execution_journal=self.execution_journal,
        )
        # RepairProposalGenerator is used directly (no constructor args needed)
        self.change_manager = ChangeManager(
            workspace_root, permission_manager,
            approval_gate=self.approval_gate,
            approval_expiry_seconds=approval_expiry_seconds,
            execution_journal=self.execution_journal,
        )

        # State
        # Initialize approval gate

        # State
        self.state = RepairLoopState.INIT
        self.loop_id = f"loop-{uuid.uuid4().hex[:8]}"
        self.report = RepairLoopReport(
            task_id=task_id,
            workspace_root=workspace_root,
            loop_id=self.loop_id,
            start_time=datetime.now(),
            max_iterations=max_iterations,
        )
        self.current_iteration = 0

    def _check_cancellation(self) -> bool:
        """Check if cancellation has been requested."""
        if self.cancellation_token and callable(self.cancellation_token):
            return self.cancellation_token()
        return False

    def _emit_event(self, event_type: str, **metadata):
        """Emit monitoring event."""
        try:
            emitter = get_emitter()
            if emitter:
                emitter.emit(event_type, task_id=self.task_id, loop_id=self.loop_id, **metadata)
        except Exception:
            pass  # Monitoring failure must not bypass security

    def _update_state(self, new_state: RepairLoopState):
        """Update loop state and emit event."""
        self.state = new_state
        self._emit_event(f"repair_loop.state_changed", old_state=self.state.value, new_state=new_state.value)

    def run(
        self,
        validation_request: ValidationRequest,
        repair_request: Optional[RepairProposalRequest] = None,
    ) -> RepairLoopReport:
        """
        Execute the full supervised repair loop.

        Args:
            validation_request: Initial validation to run
            repair_request: Optional explicit repair request (uses validation result if not provided)

        Returns:
            RepairLoopReport with complete execution evidence
        """
        self._update_state(RepairLoopState.INIT)

        try:
            for iteration in range(self.max_iterations):
                self.current_iteration = iteration + 1
                self.report.iteration_count = self.current_iteration

                if self._check_cancellation():
                    self._handle_cancellation()
                    return self._finalize_report()

                # Step 1: Run approved validation commands
                validation_result = self._run_validation(validation_request)
                if validation_result is None:
                    return self._finalize_report(outcome=RepairLoopOutcome.CANCELLED)

                self.report.validation_results.append(validation_result.to_dict() if hasattr(validation_result, 'to_dict') else validation_result)

                # Check if validation passed
                if self._is_validation_passed(validation_result):
                    self.report.outcome = RepairLoopOutcome.COMPLETED
                    self._finalize_report()
                    return self.report

                # Step 2: Analyze failure evidence
                failure_analysis = self._analyze_failure(validation_result, validation_request)
                if failure_analysis is None:
                    return self._finalize_report(outcome=RepairLoopOutcome.FAILED_VALIDATION)

                self.report.failure_analysis = failure_analysis.to_dict() if hasattr(failure_analysis, 'to_dict') else failure_analysis

                # Step 3: Generate repair proposal (if justified)
                repair_proposal = self._generate_repair_proposal(
                    validation_result, validation_request, failure_analysis, repair_request
                )

                if repair_proposal is None:
                    self.report.outcome = RepairLoopOutcome.NO_REPAIR_JUSTIFIED
                    self._finalize_report()
                    return self.report

                self.report.repair_proposal = repair_proposal.to_dict() if hasattr(repair_proposal, 'to_dict') else repair_proposal

                # Step 4: Convert to ChangeProposal
                change_proposal = self._convert_proposal(repair_proposal)
                if change_proposal is None:
                    return self._finalize_report(outcome=RepairLoopOutcome.PROPOSAL_REJECTED)

                self.report.change_proposal = change_proposal.to_dict()

                # Step 5: Validate paths and content
                if not self._validate_change_proposal(change_proposal):
                    self.report.outcome = RepairLoopOutcome.PROPOSAL_REJECTED
                    self._finalize_report()
                    return self.report

                # Step 6: Request explicit approval
                approval_result = self._request_approval(change_proposal)
                if not approval_result:
                    self.report.outcome = RepairLoopOutcome.AWAITING_APPROVAL
                    self._finalize_report()
                    return self.report

                self.report.approval_record = approval_result

                # Step 7: Apply approved changes
                apply_result = self._apply_changes(change_proposal)
                if not apply_result:
                    self.report.outcome = RepairLoopOutcome.APPLY_FAILED_ROLLED_BACK
                    self._finalize_report()
                    return self.report

                self.report.applied_changes = apply_result.get("applied_changes", [])

                # Step 8: Post-validation
                post_validation_result = self._run_post_validation(change_proposal, validation_request)
                if post_validation_result is None:
                    return self._finalize_report(outcome=RepairLoopOutcome.CANCELLED)

                self.report.post_validation_results.append(
                    post_validation_result.to_dict() if hasattr(post_validation_result, 'to_dict') else post_validation_result
                )

                if self._is_validation_passed(post_validation_result):
                    self.report.outcome = RepairLoopOutcome.COMPLETED
                    self._finalize_report()
                    return self.report

                # Step 9: Rollback on post-validation failure
                rollback_result = self._rollback_changes(change_proposal)
                self.report.rollback_outcome = rollback_result

                if rollback_result.get("status") == "incomplete":
                    self.report.outcome = RepairLoopOutcome.ROLLBACK_INCOMPLETE
                    self.report.uncertainties.append("Rollback incomplete - some files may not be restored")
                    self._emit_event("repair_loop.rollback_incomplete", severity="critical", **rollback_result)
                    self._finalize_report()
                    return self.report

                # Loop continues with fresh evidence if rollback succeeded
                self.report.outcome = RepairLoopOutcome.POST_VALIDATION_FAILED_ROLLED_BACK

            # Max iterations exceeded
            self.report.outcome = RepairLoopOutcome.MAX_ITERATIONS_EXCEEDED
            self.report.uncertainties.append(f"Max iterations ({self.max_iterations}) reached without success")
            self._finalize_report()
            return self.report

        except Exception as e:
            self.report.outcome = RepairLoopOutcome.FAILED
            self.report.uncertainties.append(f"Loop exception: {str(e)}")
            self._finalize_report()
            return self.report

    def _run_validation(self, validation_request: ValidationRequest) -> Optional[ValidationResult]:
        """Step 1: Run approved validation commands."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.VALIDATION_RUNNING)

        try:
            result_dict = self.validation_tool.execute({"validation_request": validation_request.to_dict()})
            validation_result = result_dict["validation_result"]
            self._update_state(RepairLoopState.VALIDATION_COMPLETED)
            return validation_result
        except Exception as e:
            self._update_state(RepairLoopState.FAILED)
            self.report.uncertainties.append(f"Validation execution error: {str(e)}")
            return None

    def _is_validation_passed(self, validation_result: ValidationResult) -> bool:
        """Check if validation result indicates success."""
        return (validation_result.status == ValidationStatus.PASSED and
                validation_result.test_counts.get("failed", 0) == 0)

    def _analyze_failure(
        self,
        validation_result: ValidationResult,
        validation_request: ValidationRequest
    ) -> Optional[FailureAnalysisResult]:
        """Step 2: Analyze the failure evidence."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.ANALYSIS_RUNNING)

        try:
            analysis_request = FailureAnalysisRequest(
                analysis_id=f"analysis-{uuid.uuid4().hex[:8]}",
                task_id=self.task_id,
                validation_result=validation_result,
                workspace_root=self.workspace_root,
            )
            result_dict = self.failure_analyzer.execute({"analysis_request": analysis_request.to_dict()})
            failure_analysis = result_dict["failure_analysis_result"]
            self._update_state(RepairLoopState.ANALYSIS_COMPLETED)
            return failure_analysis
        except Exception as e:
            self.report.uncertainties.append(f"Failure analysis error: {str(e)}")
            return None

    def _generate_repair_proposal(
        self,
        validation_result: ValidationResult,
        validation_request: ValidationRequest,
        failure_analysis: FailureAnalysisResult,
        repair_request: Optional[RepairProposalRequest],
    ) -> Optional[RepairProposal]:
        """Step 3: Generate a minimal repair proposal."""
        if self._check_cancellation():
            return None

        if not failure_analysis.code_change_justified:
            return None

        self._update_state(RepairLoopState.PROPOSAL_GENERATION)

        try:
            from app.extensions.repair_proposal import RepairProposalGenerator

            if repair_request is None:
                repair_request = RepairProposalRequest(
                    request_id=f"repair-{uuid.uuid4().hex[:8]}",
                    task_id=self.task_id,
                    workspace_root=self.workspace_root,
                    failure_analysis=failure_analysis,
                    validation_result=validation_result,
                    target_files=failure_analysis.affected_files,
                )

            generator = RepairProposalGenerator()
            repair_proposal = generator.generate_repair_proposal(repair_request)

            self._update_state(RepairLoopState.PROPOSAL_GENERATED)
            return repair_proposal
        except Exception as e:
            self.report.uncertainties.append(f"Repair proposal generation error: {str(e)}")
            return None

    def _convert_proposal(self, repair_proposal: RepairProposal) -> Optional[ChangeProposal]:
        """Step 4: Convert RepairProposal to ChangeProposal."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.CONVERSION)

        try:
            change_proposal = convert_repair_to_change_proposal(
                repair_proposal, self.task_id, self.workspace_root
            )
            return change_proposal
        except ValueError as e:
            self.report.uncertainties.append(f"Proposal conversion rejected: {str(e)}")
            return None
        except Exception as e:
            self.report.uncertainties.append(f"Proposal conversion error: {str(e)}")
            return None

    def _validate_change_proposal(self, change_proposal: ChangeProposal) -> bool:
        """Step 5: Validate target paths, content, command profiles, and security restrictions."""
        if self._check_cancellation():
            return False

        self._update_state(RepairLoopState.VALIDATION)

        try:
            is_valid, errors = self.change_manager.validate_proposal(change_proposal)
            if not is_valid:
                self.report.uncertainties.extend(errors)
                return False

            # Also generate preview for approval
            preview = self.change_manager.generate_preview(change_proposal)
            self.report.evidence.append({"preview": preview})
            return True
        except Exception as e:
            self.report.uncertainties.append(f"Proposal validation error: {str(e)}")
            return False

    def _request_approval(self, change_proposal: ChangeProposal) -> Optional[Dict[str, Any]]:
        """Step 6: Request explicit approval tied to the proposal hash."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.APPROVAL_REQUIRED)

        # Emit approval required event
        self._emit_event("repair_loop.approval_required",
                        proposal_hash=change_proposal.compute_proposal_hash(),
                        proposal_id=change_proposal.proposal_id)

        # Create approval request
        approval_request = self.approval_gate.request_approval(change_proposal, self.task_id)

        # Emit approval required event with approval ID
        self._emit_event("repair_loop.approval_required",
                        proposal_hash=change_proposal.compute_proposal_hash(),
                        proposal_id=change_proposal.proposal_id,
                        approval_id=approval_request.approval_id)

        approval_result = None

        # Try approval callback (for automated/unattended)
        if self.approval_callback:
            try:
                approved = self.approval_callback(change_proposal)
                if approved:
                    approval_result = {
                        "approved": True,
                        "approver": "automated_callback",
                        "timestamp": datetime.now().isoformat(),
                        "proposal_hash": change_proposal.compute_proposal_hash(),
                    }
            except Exception as e:
                self.report.uncertainties.append(f"Approval callback error: {str(e)}")

        # If no callback result, use approval gate with callback
        if not approval_result:
            try:
                # Use the approval gate's callback if available
                decision = self.approval_gate.wait_for_approval(
                    approval_request.approval_id,
                    cancellation_token=self.cancellation_token,
                    timeout=approval_request.expires_at.timestamp() - datetime.now().timestamp() if approval_request.expires_at else None
                )

                if decision and decision.decision == "approved":
                    approval_result = {
                        "approved": True,
                        "approver": decision.decided_by,
                        "timestamp": decision.decided_at.isoformat(),
                        "proposal_hash": decision.proposal_hash,
                        "approval_id": decision.approval_id,
                    }
                elif decision and decision.decision == "rejected":
                    self.report.uncertainties.append(f"Approval rejected: {decision.reason}")
                    return None
                elif decision and decision.status == ApprovalDecisionStatus.EXPIRED:
                    self.report.uncertainties.append("Approval request expired")
                    return None
                elif decision and decision.status == ApprovalDecisionStatus.CANCELLED:
                    self.report.uncertainties.append("Approval cancelled")
                    return None
            except TimeoutError:
                self.report.uncertainties.append("Approval request timed out")
                return None
            except RuntimeError as e:
                self.report.uncertainties.append(f"Approval error: {str(e)}")
                return None
            except Exception as e:
                self.report.uncertainties.append(f"PermissionManager approval error: {str(e)}")

        if not approval_result:
            # No approval available - would require interactive in production
            self.report.uncertainties.append("No approval mechanism available - requires interactive approval")
            return None

        # Record approval in change proposal
        change_proposal.approval_status = ProposalStatus.APPROVED
        change_proposal.approved_by = approval_result.get("approver", "unknown")
        change_proposal.approval_timestamp = datetime.now()
        change_proposal.approval_proposal_hash = change_proposal.compute_proposal_hash()

        # Record decision in approval gate
        if "approval_id" in approval_result:
            self.approval_gate.consume_approval(approval_result["approval_id"])

        self._update_state(RepairLoopState.APPROVED)
        self._emit_event("repair_loop.approved", **approval_result)
        return approval_result

    def _apply_changes(self, change_proposal: ChangeProposal) -> Optional[Dict[str, Any]]:
        """Step 7: Apply approved changes using ChangeManager."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.APPLICATION)

        try:
            result = self.change_manager.apply_proposal(change_proposal)
            if result.success:
                self._update_state(RepairLoopState.POST_VALIDATION)
                return {"applied_changes": result.applied_changes, "rollback_data": result.rollback_data}
            else:
                self.report.uncertainties.append(f"Apply failed: {result.error}")
                return None
        except Exception as e:
            self.report.uncertainties.append(f"Apply error: {str(e)}")
            return None

    def _run_post_validation(
        self,
        change_proposal: ChangeProposal,
        original_request: ValidationRequest
    ) -> Optional[ValidationResult]:
        """Step 8: Rerun appropriate validation."""
        if self._check_cancellation():
            return None

        self._update_state(RepairLoopState.POST_VALIDATION)

        # Run the original validation plus proposal's validation plan
        # For now, run the original validation
        try:
            result_dict = self.validation_tool.execute({"validation_request": original_request.to_dict()})
            return result_dict["validation_result"]
        except Exception as e:
            self.report.uncertainties.append(f"Post-validation error: {str(e)}")
            return None

    def _rollback_changes(self, change_proposal: ChangeProposal) -> Dict[str, Any]:
        """Step 9: Rollback safely on failure."""
        self._update_state(RepairLoopState.ROLLBACK)

        try:
            result = self.change_manager.rollback_proposal(change_proposal)
            if result.success:
                return {"status": "completed", "restored_files": result.rollback_data}
            else:
                # Partial rollback - check what was restored
                restored = []
                for item in change_proposal.rollback_data:
                    path = item.get("path", "")
                    if path and os.path.exists(os.path.join(self.workspace_root, path)):
                        restored.append(path)
                return {
                    "status": "incomplete" if restored else "failed",
                    "restored_files": restored,
                    "error": result.error,
                }
        except Exception as e:
            return {"status": "incomplete", "error": str(e)}

    def _handle_cancellation(self):
        """Handle loop cancellation."""
        self.report.outcome = RepairLoopOutcome.CANCELLED
        self._update_state(RepairLoopState.CANCELLED)
        self._emit_event("repair_loop.cancelled")

    def _finalize_report(self, outcome: Optional[RepairLoopOutcome] = None) -> RepairLoopReport:
        """Finalize and return the report."""
        if outcome:
            self.report.outcome = outcome
        self.report.end_time = datetime.now()
        self._emit_event("repair_loop.completed", outcome=self.report.outcome.value if self.report.outcome else "unknown")
        return self.report


# Export public API
__all__ = [
    "RepairLoopState",
    "RepairLoopOutcome",
    "RepairLoopReport",
    "convert_repair_to_change_proposal",
    "SupervisedRepairLoop",
]
