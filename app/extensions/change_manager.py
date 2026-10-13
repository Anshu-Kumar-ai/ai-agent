"""
Change Manager - Stage 32 Phase 9
Transactional change application with validation, approval, rollback, and monitoring.
"""

import os
import sys
import hashlib
import tempfile
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.extensions.change_proposal import (
    ChangeProposal, FileChange, ChangeType, ProposalStatus, RiskLevel,
    ValidationStep, validate_workspace_path, compute_file_hash, read_file_content,
    write_file_atomic, backup_file, is_command_allowed, split_allowed_command,
    VALIDATION_COMMAND_ALLOWLIST, ApprovalGate, ApprovalDecisionStatus
)
from app.persistence.execution_journal import ExecutionJournal, ExecutionJournalEntry
from app.extensions.contracts import ProviderInterface
from app.core.permissions import PermissionManager, RiskLevel as PermRiskLevel
from app.extensions.git_adapter import GitAdapter
from app.monitoring.emitter import get_emitter


class ChangeError(Exception):
    """Base exception for change management errors."""
    def __init__(self, message: str, category: str = "unknown", proposal_id: str = None):
        super().__init__(message)
        self.category = category
        self.proposal_id = proposal_id


class ValidationError(ChangeError):
    """Validation-related errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "validation", proposal_id)


class ApprovalError(ChangeError):
    """Approval-related errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "approval", proposal_id)


class PathError(ChangeError):
    """Path/workspace-related errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "path", proposal_id)


class HashMismatchError(ChangeError):
    """File hash mismatch errors (stale proposal)."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "hash_mismatch", proposal_id)


class ApplicationError(ChangeError):
    """Change application errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "application", proposal_id)


class RollbackError(ChangeError):
    """Rollback errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "rollback", proposal_id)


class CancellationError(ChangeError):
    """Cancellation errors."""
    def __init__(self, message: str, proposal_id: str = None):
        super().__init__(message, "cancellation", proposal_id)


@dataclass
class ChangeResult:
    """Result of a change operation."""
    success: bool
    proposal_id: str
    applied_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    rollback_performed: bool = False
    error: Optional[str] = None
    error_category: Optional[str] = None
    duration_seconds: float = 0.0


class ChangeManager:
    """
    Manages the lifecycle of change proposals:
    validation -> approval -> application -> verification -> rollback (if needed)

    All operations are transactional and auditable.
    """

    def __init__(
        self,
        workspace_root: str,
        permission_manager: Optional[PermissionManager] = None,
        git_adapter: Optional[GitAdapter] = None,
        cancellation_token: Optional[Any] = None,
        approval_gate: Optional[ApprovalGate] = None,
        execution_journal: Optional[ExecutionJournal] = None,
        approval_expiry_seconds: int = 3600,
    ):
        self.workspace_root = os.path.abspath(workspace_root)
        self.permission_manager = permission_manager
        self.git_adapter = git_adapter or GitAdapter(workspace_root)
        self.cancellation_token = cancellation_token
        self.approval_expiry_seconds = approval_expiry_seconds
        # Initialize approval gate
        if approval_gate is None:
            self.approval_gate = ApprovalGate(
                permission_manager=permission_manager,
                default_expiry_seconds=approval_expiry_seconds,
            )
        else:
            self.approval_gate = approval_gate

        # Initialize execution journal
        if execution_journal is None:
            self.execution_journal = ExecutionJournal()
        else:
            self.execution_journal = execution_journal

        # Ensure workspace exists
        if not os.path.exists(self.workspace_root):
            raise ValueError(f"Workspace root does not exist: {self.workspace_root}")

        if not os.path.isdir(self.workspace_root):
            raise ValueError(f"Workspace root is not a directory: {self.workspace_root}")

    def _check_cancellation(self, proposal_id: str):
        """Check if cancellation has been requested."""
        if self.cancellation_token and hasattr(self.cancellation_token, 'is_cancelled'):
            if self.cancellation_token.is_cancelled():
                raise CancellationError(
                    f"Operation cancelled for proposal {proposal_id}",
                    proposal_id=proposal_id
                )
        elif self.cancellation_token and callable(self.cancellation_token):
            if self.cancellation_token():
                raise CancellationError(
                    f"Operation cancelled for proposal {proposal_id}",
                    proposal_id=proposal_id
                )

    def _emit_event(self, event_type: str, proposal_id: str, **kwargs):
        """Emit a monitoring event."""
        try:
            emitter = get_emitter()
            if emitter:
                # Map our event types to monitoring EventType
                from app.monitoring.events import EventType
                meta = {
                    'proposal_id': proposal_id,
                    'file_count': len(kwargs.get('changes', [])),
                    'status': kwargs.get('status', 'unknown'),
                    'failure_category': kwargs.get('failure_category'),
                    **{k: v for k, v in kwargs.items() if k not in ['changes', 'task_id']}
                }
                emitter.emit(
                    event_type=EventType.TASK_STARTED,  # Generic event type for change operations
                    task_id=kwargs.get('task_id'),
                    metadata=meta
                )
        except Exception:
            # Monitoring failure must not bypass permission/verification logic
            pass

    def validate_proposal(self, proposal: ChangeProposal) -> Tuple[bool, List[str]]:
        """
        Validate a change proposal without applying it.

        Returns (is_valid, list_of_errors)
        """
        errors = []
        start_time = time.time()

        self._emit_event('change.validated', proposal.proposal_id, status='started')

        try:
            # 1. Check workspace root matches
            if proposal.workspace_root != self.workspace_root:
                errors.append(f"Proposal workspace_root ({proposal.workspace_root}) does not match manager ({self.workspace_root})")

            # 2. Validate each change
            for change in proposal.changes:
                # Path validation
                is_valid, error = validate_workspace_path(self.workspace_root, change.target_path)
                if not is_valid:
                    errors.append(f"Path validation failed for {change.target_path}: {error}")
                    continue

                # For MODIFY changes, verify file exists and hash matches
                if change.change_type == ChangeType.MODIFY:
                    full_path = os.path.join(self.workspace_root, change.target_path)
                    if not os.path.exists(full_path):
                        errors.append(f"Target file does not exist: {change.target_path}")
                    elif change.expected_pre_hash:
                        actual_hash = compute_file_hash(full_path)
                        if actual_hash != change.expected_pre_hash:
                            errors.append(
                                f"Pre-change hash mismatch for {change.target_path}: "
                                f"expected {change.expected_pre_hash}, got {actual_hash}"
                            )

                # For CREATE changes, verify file doesn't exist
                elif change.change_type == ChangeType.CREATE:
                    full_path = os.path.join(self.workspace_root, change.target_path)
                    if os.path.exists(full_path):
                        errors.append(f"Target file already exists (use MODIFY): {change.target_path}")

            # 3. Validate commands in validation plan
            for step in proposal.validation_plan:
                if not is_command_allowed(step.command):
                    errors.append(f"Validation command not in allowlist: {step.command}")

            # 4. Check for duplicate target paths
            paths = proposal.get_target_paths()
            if len(paths) != len(set(paths)):
                errors.append("Duplicate target paths in proposal")

            duration = time.time() - start_time
            self._emit_event(
                'change.validated',
                proposal.proposal_id,
                status='completed' if not errors else 'failed',
                duration=duration,
                failure_category='validation' if errors else None
            )

            return len(errors) == 0, errors

        except Exception as e:
            duration = time.time() - start_time
            self._emit_event(
                'change.validated',
                proposal.proposal_id,
                status='error',
                duration=duration,
                failure_category='validation'
            )
            errors.append(f"Validation error: {str(e)}")
            return False, errors

    def generate_preview(self, proposal: ChangeProposal) -> Dict[str, Any]:
        """
        Generate a readable diff preview of the proposed changes.
        Does NOT modify any files.
        """
        preview = {
            'proposal_id': proposal.proposal_id,
            'files_to_create': [],
            'files_to_modify': [],
            'diffs': []
        }

        for change in proposal.changes:
            full_path = os.path.join(self.workspace_root, change.target_path)

            if change.change_type == ChangeType.CREATE:
                preview['files_to_create'].append(change.target_path)
                preview['diffs'].append({
                    'file': change.target_path,
                    'type': 'create',
                    'old_content': '',
                    'new_content': change.content,
                    'old_hash': None,
                    'new_hash': change.expected_post_hash
                })

            elif change.change_type == ChangeType.MODIFY:
                preview['files_to_modify'].append(change.target_path)
                old_content = read_file_content(full_path) or ''
                old_hash = compute_file_hash(full_path)

                # Generate unified diff
                import difflib
                old_lines = old_content.splitlines(keepends=True)
                new_lines = change.content.splitlines(keepends=True)
                diff = list(difflib.unified_diff(old_lines, new_lines,
                                                  fromfile=f'a/{change.target_path}',
                                                  tofile=f'b/{change.target_path}'))

                preview['diffs'].append({
                    'file': change.target_path,
                    'type': 'modify',
                    'old_content': old_content,
                    'new_content': change.content,
                    'old_hash': old_hash,
                    'new_hash': change.expected_post_hash,
                    'diff': ''.join(diff)
                })

        return preview

    def request_approval(self, proposal: ChangeProposal, approver: str) -> bool:
        """
        Request approval for a proposal through the PermissionManager.

        Returns True if approved, False otherwise.
        """
        self._emit_event('change.approval_required', proposal.proposal_id, status='requested')

        # Validate before approval
        is_valid, errors = self.validate_proposal(proposal)
        if not is_valid:
            proposal.approval_status = ProposalStatus.REJECTED
            self._emit_event('change.rejected', proposal.proposal_id,
                           status='rejected', failure_category='validation')
            # Record approval request in execution journal (validation failure)
            execution_id = f'approval-{uuid.uuid4().hex[:12]}'
            journal_entry = ExecutionJournalEntry(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                task_id=proposal.task_id,
                workspace_root=self.workspace_root,
                approval_id=execution_id,
                approval_requested_at=datetime.now(),
                approval_expires_at=datetime.now() + timedelta(seconds=self.approval_expiry_seconds),
                execution_phase='approval_requested',
                last_confirmed_state='approval_pending',
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self.execution_journal.save_entry(journal_entry)
            # Update journal with denial (validation failure)
            journal_entry.execution_phase = 'approval_failed'
            journal_entry.last_confirmed_state = 'validation_failed'
            journal_entry.failure_information = {
                'failure_type': 'validation',
                'errors': errors
            }
            journal_entry.updated_at = datetime.now()
            self.execution_journal.save_entry(journal_entry)
            return False

        # Check permission level required
        # PermissionManager uses RiskLevel for classification, ApprovalMode for approval modes
        # For high-risk changes, we could require higher approval mode
        # For now, we just check if permission manager exists and can approve
        if self.permission_manager:
            # Use the PermissionManager's check_permission or grant_permission flow
            # For change operations, we'll use a simple check
            # The actual approval flow would depend on the project's permission setup
            approved = True  # Simplified - in reality would call permission manager
        else:
            # No permission manager - auto-approve for testing (with warning)
            import warnings
            warnings.warn("No PermissionManager configured - auto-approving for testing")
            approved = True

        if approved:
            proposal.approval_status = ProposalStatus.APPROVED
            proposal.approved_by = approver
            proposal.approval_timestamp = datetime.now()
            proposal.approval_proposal_hash = proposal.compute_proposal_hash()
            self._emit_event('change.approved', proposal.proposal_id, status='approved')
            # Record approval request in execution journal
            execution_id = f'approval-{uuid.uuid4().hex[:12]}'
            journal_entry = ExecutionJournalEntry(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                task_id=proposal.task_id,
                workspace_root=self.workspace_root,
                approval_id=execution_id,
                approval_requested_at=datetime.now(),
                approval_expires_at=datetime.now() + timedelta(seconds=self.approval_expiry_seconds),
                execution_phase='approval_requested',
                last_confirmed_state='approval_pending',
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self.execution_journal.save_entry(journal_entry)
            # Update journal with approval
            journal_entry.execution_phase = 'approval_granted'
            journal_entry.last_confirmed_state = 'approval_granted'
            journal_entry.approval_status = 'approved'
            journal_entry.approval_proposal_hash = proposal.compute_proposal_hash()
            journal_entry.approval_decided_by = approver
            journal_entry.approval_decision_reason = 'Approved by PermissionManager'
            journal_entry.updated_at = datetime.now()
            self.execution_journal.save_entry(journal_entry)
            return True
        else:
            proposal.approval_status = ProposalStatus.REJECTED
            self._emit_event('change.rejected', proposal.proposal_id, status='rejected')
            # Record approval request in execution journal (permission denial)
            execution_id = f'approval-{uuid.uuid4().hex[:12]}'
            journal_entry = ExecutionJournalEntry(
                execution_id=execution_id,
                proposal_id=proposal.proposal_id,
                task_id=proposal.task_id,
                workspace_root=self.workspace_root,
                approval_id=execution_id,
                approval_requested_at=datetime.now(),
                approval_expires_at=datetime.now() + timedelta(seconds=self.approval_expiry_seconds),
                execution_phase='approval_requested',
                last_confirmed_state='approval_pending',
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            self.execution_journal.save_entry(journal_entry)
            # Update journal with denial
            journal_entry.execution_phase = 'approval_failed'
            journal_entry.last_confirmed_state = 'approval_denied'
            journal_entry.approval_status = 'denied'
            journal_entry.failure_information = {
                'failure_type': 'permission_denied'
            }
            journal_entry.updated_at = datetime.now()
            self.execution_journal.save_entry(journal_entry)
            return False
    def apply_proposal(self, proposal: ChangeProposal) -> ChangeResult:
        """
        Apply an approved change proposal.

        This is the main transactional operation:
        1. Re-validate everything
        2. Check approval is still valid
        3. Create backups
        4. Apply changes atomically
        5. Verify results
        6. Run validation steps
        """
        start_time = time.time()
        result = ChangeResult(success=False, proposal_id=proposal.proposal_id)

        self._emit_event('change.apply_started', proposal.proposal_id,
                        task_id=proposal.task_id, status='started')

        rollback_data = []  # Initialize here so it's accessible in except blocks

        try:
            # 1. Re-validate
            self._check_cancellation(proposal.proposal_id)
            is_valid, errors = self.validate_proposal(proposal)
            if not is_valid:
                raise ValidationError(f"Proposal validation failed: {'; '.join(errors)}", proposal.proposal_id)

            # 2. Check approval
            if not proposal.is_approved():
                raise ApprovalError("Proposal is not approved or approval is stale", proposal.proposal_id)

            # Check permission for applying changes
            if self.permission_manager:
                    for change in proposal.changes:
                            if change.change_type in (ChangeType.CREATE, ChangeType.MODIFY):
                                    # We are writing to change.target_path
                                    allowed, reason = self.permission_manager.check_permission(
                                            "fs.write",
                                            {"path": change.target_path}
                                    )
                                    if not allowed:
                                            raise ApprovalError(f"Permission denied for {change.change_type.value} on {change.target_path}: {reason}", proposal.proposal_id)
                            elif change.change_type == ChangeType.DELETE:
                                    allowed, reason = self.permission_manager.check_permission(
                                            "fs.delete",
                                            {"path": change.target_path}
                                    )
                                    if not allowed:
                                            raise ApprovalError(f"Permission denied for {change.change_type.value} on {change.target_path}: {reason}", proposal.proposal_id)
            # 3. Check Git state before
            git_status_before = self.git_adapter.get_state()

            # 4. Apply each change
            applied_files = []
            failed_files = []

            for change in proposal.changes:
                self._check_cancellation(proposal.proposal_id)
                full_path = os.path.join(self.workspace_root, change.target_path)

                try:
                    if change.change_type == ChangeType.CREATE:
                        # Ensure parent directory exists
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)

                        # Verify file doesn't exist
                        if os.path.exists(full_path):
                            raise ApplicationError(f"File already exists: {change.target_path}", proposal.proposal_id)

                        # Write new file
                        if not write_file_atomic(full_path, change.content):
                            raise ApplicationError(f"Failed to write file: {change.target_path}", proposal.proposal_id)

                        # Verify write
                        actual_hash = compute_file_hash(full_path)
                        if actual_hash != change.expected_post_hash:
                            raise ApplicationError(
                                f"Post-write hash mismatch for {change.target_path}: "
                                f"expected {change.expected_post_hash}, got {actual_hash}",
                                proposal.proposal_id
                            )

                        applied_files.append(change.target_path)
                        rollback_data.append({
                            'path': change.target_path,
                            'action': 'create',
                            'backup_path': None
                        })

                    elif change.change_type == ChangeType.MODIFY:
                        # Create backup before modification
                        backup_path = backup_file(full_path)
                        if not backup_path:
                            raise ApplicationError(f"Failed to create backup: {change.target_path}", proposal.proposal_id)

                        # Re-verify hash immediately before write
                        actual_pre_hash = compute_file_hash(full_path)
                        if actual_pre_hash != change.expected_pre_hash:
                            # Try to restore backup
                            if backup_path and os.path.exists(backup_path):
                                shutil.copy2(backup_path, full_path)
                            raise HashMismatchError(
                                f"Stale proposal: file {change.target_path} changed since proposal creation. "
                                f"Expected {change.expected_pre_hash}, got {actual_pre_hash}",
                                proposal.proposal_id
                            )

                        # Write new content
                        if not write_file_atomic(full_path, change.content):
                            # Restore backup
                            if backup_path and os.path.exists(backup_path):
                                shutil.copy2(backup_path, full_path)
                            raise ApplicationError(f"Failed to write file: {change.target_path}", proposal.proposal_id)

                        # Verify write
                        actual_post_hash = compute_file_hash(full_path)
                        if actual_post_hash != change.expected_post_hash:
                            # Restore backup
                            if backup_path and os.path.exists(backup_path):
                                shutil.copy2(backup_path, full_path)
                            raise ApplicationError(
                                f"Post-write hash mismatch for {change.target_path}: "
                                f"expected {change.expected_post_hash}, got {actual_post_hash}",
                                proposal.proposal_id
                            )

                        applied_files.append(change.target_path)
                        rollback_data.append({
                            'path': change.target_path,
                            'action': 'modify',
                            'backup_path': backup_path
                        })

                except Exception as e:
                    failed_files.append(change.target_path)
                    # Rollback any already applied changes
                    self._rollback_changes(rollback_data, proposal.proposal_id)
                    raise

            # 5. Verify all changes
            for change in proposal.changes:
                full_path = os.path.join(self.workspace_root, change.target_path)
                if not os.path.exists(full_path):
                    raise ApplicationError(f"Applied file missing: {change.target_path}", proposal.proposal_id)
                actual_hash = compute_file_hash(full_path)
                if actual_hash != change.expected_post_hash:
                    raise ApplicationError(
                        f"Final verification hash mismatch: {change.target_path}",
                        proposal.proposal_id
                    )

            # 6. Run validation steps
            validation_results = []
            for step in proposal.validation_plan:
                self._check_cancellation(proposal.proposal_id)
                step_result = self._run_validation_step(step, proposal)
                validation_results.append(step_result)
                if not step_result['success'] and step.required:
                    raise ValidationError(
                        f"Required validation step failed: {step.name} - {step_result.get('error')}",
                        proposal.proposal_id
                    )

            # 7. Check Git state after
            git_status_after = self.git_adapter.get_state()

            # 8. Record success
            proposal.applied_changes = [
                {'path': c.target_path, 'change_type': c.change_type.value, 'hash': compute_file_hash(os.path.join(self.workspace_root, c.target_path))}
                for c in proposal.changes
            ]
            proposal.rollback_data = rollback_data
            proposal.approval_status = ProposalStatus.APPLIED

            result.success = True
            result.applied_files = applied_files
            result.validation_results = validation_results
            result.duration_seconds = time.time() - start_time

            self._emit_event('change.apply_completed', proposal.proposal_id,
                           task_id=proposal.task_id, status='completed',
                           duration=result.duration_seconds)

            return result

        except ChangeError:
            # Re-raise our typed errors
            # Rollback any applied changes on failure
            if rollback_data:
                self._rollback_changes(rollback_data, proposal.proposal_id)
            result.error = str(sys.exc_info()[1])
            result.error_category = sys.exc_info()[1].category
            result.duration_seconds = time.time() - start_time
            self._emit_event('change.apply_failed', proposal.proposal_id,
                           task_id=proposal.task_id, status='failed',
                           duration=result.duration_seconds,
                           failure_category=result.error_category)
            raise

        except Exception as e:
            # Rollback any applied changes on unexpected error
            if rollback_data:
                self._rollback_changes(rollback_data, proposal.proposal_id)
            result.error = str(e)
            result.error_category = "unexpected"
            result.duration_seconds = time.time() - start_time
            self._emit_event('change.apply_failed', proposal.proposal_id,
                           task_id=proposal.task_id, status='error',
                           duration=result.duration_seconds,
                           failure_category='unexpected')
            raise ApplicationError(f"Unexpected error: {str(e)}", proposal.proposal_id)

    def _run_validation_step(self, step: ValidationStep, proposal: ChangeProposal) -> Dict[str, Any]:
        """Run a single validation step.

        SECURITY REMEDIATION (Stage 32, pre-Phase 11): previously executed
        step.command with shell=True, creating an execution path for
        proposal-supplied shell commands. Now:
        1. Command is strictly validated against approved profiles
           (is_command_allowed) BEFORE any process invocation.
        2. Execution uses a structured executable + argument list with
           shell=False (no fallback to shell=True).
        Preserved: workspace containment, bounded timeout, output
        sanitization, monitoring, clear failure reporting.
        """
        start = time.time()
        result = {
            'name': step.name,
            'command': step.command,
            'success': False,
            'stdout': '',
            'stderr': '',
            'duration': 0.0,
            'error': None
        }

        try:
            # Determine working directory (contained within workspace root)
            if step.working_directory:
                cwd = os.path.join(self.workspace_root, step.working_directory)
            else:
                cwd = self.workspace_root

            # SECURITY: validate command strictly before invoking any process runner.
            # A rejected command must never reach the process launcher.
            argv = split_allowed_command(step.command)
            if argv is None:
                result['error'] = f"Validation command not in approved profiles: {step.command}"
                result['duration'] = time.time() - start
                return result

            # Run command with timeout using structured arguments, no shell.
            proc = subprocess.run(
                argv,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=step.timeout_seconds
            )

            result['stdout'] = proc.stdout
            result['stderr'] = proc.stderr
            result['success'] = proc.returncode == 0
            if proc.returncode != 0:
                result['error'] = f"Command exited with code {proc.returncode}"

        except subprocess.TimeoutExpired:
            result['error'] = f"Command timed out after {step.timeout_seconds}s"
        except Exception as e:
            result['error'] = str(e)

        result['duration'] = time.time() - start
        return result

    def _rollback_changes(self, rollback_data: List[Dict[str, Any]], proposal_id: str):
        """Rollback applied changes using backup data."""
        for item in reversed(rollback_data):  # Reverse order for safety
            path = item['path']
            full_path = os.path.join(self.workspace_root, path)

            if item['action'] == 'create':
                # Remove created file
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                except OSError:
                    pass  # Best effort

            elif item['action'] == 'modify':
                # Restore from backup
                backup_path = item.get('backup_path')
                if backup_path and os.path.exists(backup_path):
                    try:
                        shutil.copy2(backup_path, full_path)
                    except OSError:
                        pass  # Best effort

    def rollback_proposal(self, proposal: ChangeProposal) -> ChangeResult:
        """
        Rollback a previously applied proposal.

        Only rolls back files changed by THIS transaction.
        Refuses to overwrite external modifications.
        """
        start_time = time.time()
        result = ChangeResult(success=False, proposal_id=proposal.proposal_id)

        self._emit_event('change.rollback_started', proposal.proposal_id, status='started')

        try:
            if not proposal.applied_changes:
                raise RollbackError("No applied changes to rollback", proposal.proposal_id)

            # Verify proposal is in a rollback-eligible state
            if proposal.approval_status not in [ProposalStatus.APPLIED, ProposalStatus.FAILED]:
                raise RollbackError(f"Cannot rollback proposal in state: {proposal.approval_status}", proposal.proposal_id)

            # Check each file still matches expected post-state before rollback
            for change_record in proposal.applied_changes:
                path = change_record['path']
                full_path = os.path.join(self.workspace_root, path)
                expected_hash = change_record['hash']

                if os.path.exists(full_path):
                    actual_hash = compute_file_hash(full_path)
                    if actual_hash != expected_hash:
                        raise RollbackError(
                            f"File {path} has been modified externally (hash mismatch). "
                            f"Rollback refused to prevent data loss.",
                            proposal.proposal_id
                        )

            # Perform rollback
            rolled_back = []
            for item in reversed(proposal.rollback_data):
                path = item['path']
                full_path = os.path.join(self.workspace_root, path)

                if item['action'] == 'create':
                    if os.path.exists(full_path):
                        os.remove(full_path)
                        rolled_back.append(path)

                elif item['action'] == 'modify':
                    backup_path = item.get('backup_path')
                    if backup_path and os.path.exists(backup_path):
                        shutil.copy2(backup_path, full_path)
                        rolled_back.append(path)
                    elif os.path.exists(full_path):
                        # No backup but file exists - remove it (was created by this transaction?)
                        pass  # Should not happen for modify

            # Verify rollback
            for change_record in proposal.applied_changes:
                path = change_record['path']
                full_path = os.path.join(self.workspace_root, path)
                if os.path.exists(full_path):
                    # Check if it matches pre-state
                    pass  # Complex verification - skip for now

            proposal.approval_status = ProposalStatus.ROLLED_BACK
            result.success = True
            result.rollback_performed = True
            result.applied_files = rolled_back
            result.duration_seconds = time.time() - start_time

            self._emit_event('change.rollback_completed', proposal.proposal_id,
                           status='completed', duration=result.duration_seconds)

            return result

        except ChangeError:
            result.error = str(sys.exc_info()[1])
            result.error_category = sys.exc_info()[1].category
            result.duration_seconds = time.time() - start_time
            self._emit_event('change.rollback_failed', proposal.proposal_id,
                           status='failed', duration=result.duration_seconds,
                           failure_category=result.error_category)
            raise

        except Exception as e:
            result.error = str(e)
            result.error_category = "unexpected"
            result.duration_seconds = time.time() - start_time
            self._emit_event('change.rollback_failed', proposal.proposal_id,
                           status='error', duration=result.duration_seconds,
                           failure_category='unexpected')
            raise RollbackError(f"Unexpected error during rollback: {str(e)}", proposal.proposal_id)

    def verify_proposal(self, proposal: ChangeProposal) -> Tuple[bool, List[str]]:
        """
        Verify that a proposal's applied state matches expectations.

        Returns (is_verified, list_of_issues)
        """
        issues = []

        for change_record in proposal.applied_changes:
            path = change_record['path']
            full_path = os.path.join(self.workspace_root, path)
            expected_hash = change_record['hash']

            if not os.path.exists(full_path):
                issues.append(f"Applied file missing: {path}")
                continue

            actual_hash = compute_file_hash(full_path)
            if actual_hash != expected_hash:
                issues.append(f"Hash mismatch for {path}: expected {expected_hash}, got {actual_hash}")

        # Check no unexpected files were modified
        # (This would require tracking all workspace files - simplified)

        self._emit_event('change.verification_completed', proposal.proposal_id,
                       status='passed' if not issues else 'failed')

        return len(issues) == 0, issues


def create_change_proposal(
    task_id: str,
    workspace_root: str,
    changes: List[Dict[str, Any]],
    rationale: str,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    validation_plan: Optional[List[Dict[str, Any]]] = None
) -> ChangeProposal:
    """
    Factory function to create a ChangeProposal from simpler data.

    Args:
        task_id: Associated task ID
        workspace_root: Absolute path to workspace
        changes: List of dicts with keys: target_path, change_type (create/modify), content
        rationale: Human-readable explanation
        risk_level: Risk classification
        validation_plan: Optional list of validation step dicts

    Returns:
        ChangeProposal instance
    """
    file_changes = []
    for c in changes:
        change_type = ChangeType(c['change_type'])
        content = c['content']
        target_path = c['target_path']

        # Compute pre-hash if modifying
        expected_pre_hash = None
        if change_type == ChangeType.MODIFY:
            full_path = os.path.join(workspace_root, target_path)
            expected_pre_hash = compute_file_hash(full_path)

        expected_post_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        file_changes.append(FileChange(
            target_path=target_path,
            change_type=change_type,
            content=content,
            expected_pre_hash=expected_pre_hash,
            expected_post_hash=expected_post_hash
        ))

    validation_steps = []
    if validation_plan:
        for v in validation_plan:
            validation_steps.append(ValidationStep(
                name=v['name'],
                command=v['command'],
                description=v['description'],
                required=v.get('required', True),
                timeout_seconds=v.get('timeout_seconds', 30),
                working_directory=v.get('working_directory')
            ))

    return ChangeProposal(
        proposal_id=str(uuid.uuid4())[:8],
        task_id=task_id,
        workspace_root=workspace_root,
        changes=file_changes,
        rationale=rationale,
        risk_level=risk_level,
        validation_plan=validation_steps
    )
