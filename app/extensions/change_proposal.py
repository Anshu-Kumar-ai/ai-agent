"""



Change Proposal Contract - Stage 32 Phase 9



Defines the structured contract for proposing, validating, and applying local code changes.



"""







from dataclasses import dataclass, field



from typing import Dict, List, Optional, Any, Tuple



from enum import Enum



from datetime import datetime, timedelta



import uuid



import time



import hashlib



import shlex
import os
from app.persistence.execution_journal import ExecutionJournal
from app.persistence.execution_journal import ExecutionJournalEntry
from app.core.permissions import PermissionManager









class ChangeType(Enum):



    """Type of change operation."""



    CREATE = "create"



    MODIFY = "modify"



    # DELETE = "delete"  # Not supported in Phase 9











class ProposalStatus(Enum):



    """Status of a change proposal."""



    DRAFT = "draft"



    PROPOSED = "proposed"



    VALIDATED = "validated"



    APPROVAL_REQUIRED = "approval_required"



    APPROVED = "approved"



    REJECTED = "rejected"



    APPLYING = "applying"



    APPLIED = "applied"



    FAILED = "failed"



    ROLLED_BACK = "rolled_back"



    CANCELLED = "cancelled"











class RiskLevel(Enum):



    """Risk classification for changes."""



    LOW = "low"



    MEDIUM = "medium"



    HIGH = "high"











@dataclass



class FileChange:



    """Represents a single file change within a proposal."""



    target_path: str  # Relative to workspace root



    change_type: ChangeType



    content: str  # New content (for create/modify)



    expected_pre_hash: Optional[str] = None  # SHA256 of current content (None for create)



    expected_post_hash: Optional[str] = None  # SHA256 of expected content after change







    def __post_init__(self):



        # Compute expected post hash from content



        if self.expected_post_hash is None:



            self.expected_post_hash = hashlib.sha256(self.content.encode('utf-8')).hexdigest()







    def compute_content_hash(self, content: str) -> str:



        """Compute SHA256 hash of content."""



        return hashlib.sha256(content.encode('utf-8')).hexdigest()











@dataclass



class ValidationStep:



    """A validation step to run after applying changes."""



    name: str



    command: str  # Command to execute (from allowlist)



    description: str



    required: bool = True



    timeout_seconds: int = 30



    working_directory: Optional[str] = None  # Relative to workspace root











@dataclass



class ChangeProposal:



    """



    Structured proposal for local code changes.







    All fields are required for a complete proposal except where noted.



    The proposal must describe intended changes BEFORE any file is modified.



    """



    # Identity



    proposal_id: str



    task_id: str







    # Workspace context



    workspace_root: str  # Absolute path to workspace root







    # Changes



    changes: List[FileChange]  # List of file changes







    # Metadata



    rationale: str  # Human-readable explanation of why this change



    risk_level: RiskLevel







    # Validation



    validation_plan: List[ValidationStep] = field(default_factory=list)







    # Approval



    approval_status: ProposalStatus = ProposalStatus.DRAFT



    approved_by: Optional[str] = None



    approval_timestamp: Optional[datetime] = None



    approval_proposal_hash: Optional[str] = None  # Hash of proposal at approval time



    approval_id: Optional[str] = None







    # Timestamps



    created_at: datetime = field(default_factory=datetime.now)



    updated_at: datetime = field(default_factory=datetime.now)







    # Execution tracking



    applied_changes: List[Dict[str, Any]] = field(default_factory=list)  # Track what was actually applied



    rollback_data: List[Dict[str, Any]] = field(default_factory=list)  # Backup data for rollback







    def compute_proposal_hash(self) -> str:



        """Compute a deterministic hash of the proposal content (excluding mutable fields)."""



        import json



        # Create a stable representation



        data = {



            "proposal_id": self.proposal_id,



            "task_id": self.task_id,



            "workspace_root": self.workspace_root,



            "changes": [



                {



                    "target_path": c.target_path,



                    "change_type": c.change_type.value,



                    "content": c.content,



                    "expected_pre_hash": c.expected_pre_hash,



                    "expected_post_hash": c.expected_post_hash,



                }



                for c in self.changes



            ],



            "rationale": self.rationale,



            "risk_level": self.risk_level.value,



            "validation_plan": [



                {



                    "name": v.name,



                    "command": v.command,



                    "description": v.description,



                    "required": v.required,



                    "timeout_seconds": v.timeout_seconds,



                    "working_directory": v.working_directory,



                }



                for v in self.validation_plan



            ],



        }



        # Sort keys for deterministic hashing



        return hashlib.sha256(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()







    def get_target_paths(self) -> List[str]:



        """Get all target file paths (relative to workspace)."""



        return [c.target_path for c in self.changes]







    def is_approved(self) -> bool:



        """Check if proposal is approved and approval is still valid."""



        if self.approval_status != ProposalStatus.APPROVED:



            return False



        if self.approval_proposal_hash is None:



            return False



        # Verify proposal hasn't changed since approval



        return self.compute_proposal_hash() == self.approval_proposal_hash







    def to_dict(self) -> Dict[str, Any]:



        """Convert to dictionary for serialization."""



        return {



            "proposal_id": self.proposal_id,



            "task_id": self.task_id,



            "workspace_root": self.workspace_root,



            "changes": [



                {



                    "target_path": c.target_path,



                    "change_type": c.change_type.value,



                    "content": c.content,



                    "expected_pre_hash": c.expected_pre_hash,



                    "expected_post_hash": c.expected_post_hash,



                }



                for c in self.changes



            ],



            "rationale": self.rationale,



            "risk_level": self.risk_level.value,



            "validation_plan": [



                {



                    "name": v.name,



                    "command": v.command,



                    "description": v.description,



                    "required": v.required,



                    "timeout_seconds": v.timeout_seconds,



                    "working_directory": v.working_directory,



                }



                for v in self.validation_plan



            ],



            "approval_status": self.approval_status.value,



            "approved_by": self.approved_by,



            "approval_timestamp": self.approval_timestamp.isoformat() if self.approval_timestamp else None,



            "approval_proposal_hash": self.approval_proposal_hash,



            "created_at": self.created_at.isoformat(),



            "updated_at": self.updated_at.isoformat(),



        }







    @classmethod



    def from_dict(cls, data: Dict[str, Any]) -> 'ChangeProposal':



        """Create from dictionary."""



        changes = [



            FileChange(



                target_path=c["target_path"],



                change_type=ChangeType(c["change_type"]),



                content=c["content"],



                expected_pre_hash=c.get("expected_pre_hash"),



                expected_post_hash=c.get("expected_post_hash"),



            )



            for c in data.get("changes", [])



        ]







        validation_plan = [



            ValidationStep(



                name=v["name"],



                command=v["command"],



                description=v["description"],



                required=v.get("required", True),



                timeout_seconds=v.get("timeout_seconds", 30),



                working_directory=v.get("working_directory"),



            )



            for v in data.get("validation_plan", [])



        ]







        proposal = cls(



            proposal_id=data["proposal_id"],



            task_id=data["task_id"],



            workspace_root=data["workspace_root"],



            changes=changes,



            rationale=data["rationale"],



            risk_level=RiskLevel(data["risk_level"]),



            validation_plan=validation_plan,



            approval_status=ProposalStatus(data.get("approval_status", "draft")),



            approved_by=data.get("approved_by"),



            approval_timestamp=datetime.fromisoformat(data["approval_timestamp"]) if data.get("approval_timestamp") else None,



            approval_proposal_hash=data.get("approval_proposal_hash"),



            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),



            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),



        )







        return proposal











# Validation command allowlist for security



# SECURITY REMEDIATION (Stage 32, pre-Phase 11): command validation hardened from



# permissive prefix matching (command.startswith(allowed)) to strict profile-based



# validation. Prefix matching accepted shell-injection payloads such as



# "python -m pytest; rm -rf /" and "python -m pytest && curl evil" (verified by



# execution). The allowlist CONTENT is unchanged; only authorization strictness changed.



VALIDATION_COMMAND_ALLOWLIST = [



    "python -m py_compile",  # Syntax check



    "python -m pytest",      # Unit tests



    "ruff check",            # Linting



    "black --check",         # Format check



    "mypy",                  # Type checking



]







# Shell syntax that must never appear in a validation command argument profile.



# This is NOT a dangerous-character blacklist for securing arbitrary shell strings



# (that approach is unsound); it is a boundary definition: validation commands are



# plain argument lists, and any shell control syntax means the input is not a valid



# argument profile for an approved command.



_SHELL_SYNTAX_TOKENS = (";", "|", "&", "`", "$(", "${", ">", "<", "\n", "\r")











def is_command_allowed(command: str) -> bool:



    """Check if a validation command matches an approved command profile.







    Strict validation (Security Remediation, Stage 32 pre-Phase 11):



    1. Command must be a non-empty string.



    2. Command must not contain shell control syntax (chaining, pipes,



       redirection, substitution, newlines). This rejects, not blacklists:



       shell syntax in a validation argument profile is invalid by definition.



    3. First token must match the first token of some allowlist entry



       (derived at call time, so test-scoped runtime entries added to



       VALIDATION_COMMAND_ALLOWLIST — e.g. the documented 'sleep' test



       allowance — continue to work as designed in Phase 10).



    4. The command must start with an allowlisted profile as a complete-token



       prefix (e.g. "python -m pytest" matches "python -m pytest tests/",



       but "python -m pytestx" does not; "python -m pytest; rm -rf /" is



       rejected earlier by the shell-syntax boundary).







    Returns True only for commands safe to pass to a non-shell process runner.



    """



    if not isinstance(command, str) or not command.strip():



        return False







    command = command.strip()







    # 1. Shell-syntax boundary: reject chaining, pipes, redirection,



    #    substitution, and embedded newlines before anything else.



    for token in _SHELL_SYNTAX_TOKENS:



        if token in command:



            return False







    # 2. First token must match an allowlist entry's executable (runtime-derived).



    tokens = shlex.split(command)



    if not tokens:



        return False



    if not any(



        allowed.split() and allowed.split()[0] == tokens[0]



        for allowed in VALIDATION_COMMAND_ALLOWLIST



    ):



        return False







    # 3. Must start with an allowlisted profile as a complete-token prefix.



    for allowed in VALIDATION_COMMAND_ALLOWLIST:



        allowed_tokens = allowed.split()



        if len(tokens) >= len(allowed_tokens) and tokens[:len(allowed_tokens)] == allowed_tokens:



            return True



    return False











def split_allowed_command(command: str) -> Optional[list]:



    """Split an approved validation command into an executable + argument list.







    Returns None if the command is not allowed or cannot be parsed.



    Use with subprocess (shell=False) for safe execution.



    """



    if not is_command_allowed(command):



        return None



    return shlex.split(command)











def validate_workspace_path(workspace_root: str, target_path: str) -> tuple[bool, str]:



    """



    Validate that a target path is within the workspace.







    Security-hardened version (M-B): Uses canonical paths for symlink detection,



    checks all parent directories, and validates against workspace boundaries.







    Returns (is_valid, error_message)



    """



    if not isinstance(workspace_root, str) or not isinstance(target_path, str):



        return False, "Invalid input types"







    if not workspace_root:



        return False, "Empty workspace root not allowed"







    # Empty target_path is allowed - it means "validate the workspace root itself"







    # Normalize workspace root - strip trailing separators for consistent comparison



    workspace_root = os.path.abspath(workspace_root).rstrip(os.sep)







    # Join and get absolute path of target



    target_abs = os.path.abspath(os.path.join(workspace_root, target_path))







    # 1. Check for UNC path FIRST (before general traversal check)



    # UNC paths start with \\ or // on Windows



    if target_path.startswith('\\\\') or target_path.startswith('//'):



        return False, f"UNC path not allowed: {target_path}"







    # 2. Check for absolute path escape in the original target_path



    if os.path.isabs(target_path):



        return False, f"Absolute path not allowed: {target_path}"







    # 3. Check for drive-relative path (Windows) e.g., C:foo or C:\foo



    if len(target_path) >= 2 and target_path[1] == ':':



        return False, f"Drive-relative path not allowed: {target_path}"







    # 4. Check for traversal sequences in the original path (both / and \ separators)



    # Normalize separators and check each component



    normalized_original = target_path.replace('\\', '/')



    for component in normalized_original.split('/'):



        if component == '..':



            return False, f"Path traversal detected: {target_path}"



        if component == '' and normalized_original.startswith('/'):



            # Leading slash indicates absolute path



            return False, f"Absolute path not allowed: {target_path}"







    # 5. Resolve canonical paths for symlink detection



    # Use realpath to resolve any symlinks in the path



    try:



        workspace_real = os.path.realpath(workspace_root)



        target_real = os.path.realpath(target_abs)



    except OSError:



        # If realpath fails, fall back to abspath



        workspace_real = workspace_root



        target_real = target_abs







    # 6. Check if any parent directory of target is a symlink pointing outside workspace



    # Walk up from target to workspace, checking each level for symlinks



    check_path = target_real



    while check_path != os.path.dirname(check_path):  # Until root



        try:



            if os.path.islink(check_path):



                # Get the symlink target



                link_target = os.readlink(check_path)



                link_abs = os.path.abspath(os.path.join(os.path.dirname(check_path), link_target))



                # Check if symlink points outside workspace



                if not link_abs.startswith(workspace_real + os.sep) and link_abs != workspace_real:



                    return False, f"Symlink escapes workspace: {target_path}"



        except OSError:



            pass  # Can't read link, continue



        if check_path == workspace_real:



            break



        check_path = os.path.dirname(check_path)







    # 7. Check for path traversal via canonical paths



    if not target_real.startswith(workspace_real + os.sep) and target_real != workspace_real:



        return False, f"Path escapes workspace (canonical): {target_path}"







    # 8. Check for symlink/reparse point on the final target (Windows best effort)



    try:



        if os.path.islink(target_real):



            return False, f"Symlink not allowed: {target_path}"



    except OSError:



        pass  # If we can't check, proceed







    return True, ""











def compute_file_hash(filepath: str) -> Optional[str]:



    """Compute SHA256 hash of a file."""



    try:



        with open(filepath, 'rb') as f:



            return hashlib.sha256(f.read()).hexdigest()



    except (OSError, IOError):



        return None











def read_file_content(filepath: str) -> Optional[str]:



    """Read file content as UTF-8 text."""



    try:



        with open(filepath, 'r', encoding='utf-8') as f:



            return f.read()



    except (OSError, IOError, UnicodeDecodeError):



        return None











def write_file_atomic(filepath: str, content: str) -> bool:



    """



    Write file atomically using temp file + rename.



    Returns True on success.



    """



    try:



        import tempfile



        # Create temp file in same directory for atomic rename



        dirpath = os.path.dirname(filepath)



        with tempfile.NamedTemporaryFile(mode='wb', dir=dirpath, delete=False) as tmp:



            tmp.write(content.encode('utf-8'))



            tmp_path = tmp.name



        # Atomic rename



        os.replace(tmp_path, filepath)



        return True



    except (OSError, IOError):



        # Clean up temp file on failure



        try:



            if 'tmp_path' in locals():



                os.unlink(tmp_path)



        except OSError:



            pass



        return False











def backup_file(filepath: str) -> Optional[str]:



    """Create a backup of a file and return backup path."""



    try:



        import tempfile



        backup_path = filepath + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"



        with open(filepath, 'rb') as src, open(backup_path, 'wb') as dst:



            dst.write(src.read())



        return backup_path



    except (OSError, IOError):



        return None











# =============================================================================



# M-E: Real Approval Gate - Approval Contract



# =============================================================================







class ApprovalDecisionStatus(Enum):



    """Status of an approval decision."""



    PENDING = "pending"



    APPROVED = "approved"



    CLAIMED = "claimed"



    REJECTED = "rejected"



    EXPIRED = "expired"



    CANCELLED = "cancelled"



    INVALIDATED = "invalidated"



    CONSUMED = "consumed"











@dataclass



class ApprovalRequest:



    """Request for human approval of a change proposal."""



    approval_id: str



    proposal_id: str



    proposal_hash: str  # Hash of the proposal at request time



    task_id: str



    workspace_root: str



    operation_type: str  # e.g., "repair", "change", "validation"



    risk_level: RiskLevel



    approval_status: ApprovalDecisionStatus = ApprovalDecisionStatus.PENDING



    created_at: datetime = field(default_factory=datetime.now)



    expires_at: Optional[datetime] = None



    decided_at: Optional[datetime] = None



    decided_by: Optional[str] = None



    decision: Optional[str] = None  # "approved", "rejected"



    proposal_summary: str = ""



    affected_paths: List[str] = field(default_factory=list)



    validation_plan_summary: str = ""



    permission_scope: str = ""











@dataclass



class ApprovalDecision:



    """Record of an approval decision."""



    approval_id: str



    proposal_id: str



    proposal_hash: str



    decision: str  # "approved", "rejected"



    decided_by: str



    decided_at: datetime = field(default_factory=datetime.now)



    status: ApprovalDecisionStatus = ApprovalDecisionStatus.APPROVED



    reason: str = ""



    consumed: bool = False



    consumed_at: Optional[datetime] = None











class ApprovalGate:
    """Real approval gate for change proposals, backed by the execution journal."""

    def __init__(
        self,
        permission_manager: Optional[PermissionManager] = None,
        default_expiry_seconds: int = 3600,  # 1 hour
        approval_callback: Optional[callable] = None,
        execution_journal: Optional[ExecutionJournal] = None,
    ):
        self.permission_manager = permission_manager
        self.default_expiry_seconds = default_expiry_seconds
        self.approval_callback = approval_callback
        if execution_journal is None:
            self.execution_journal = ExecutionJournal()
        else:
            self.execution_journal = execution_journal

    def _get_entry(self, approval_id: str) -> Optional[ExecutionJournalEntry]:
        """Load the journal entry for the given approval ID.
        Uses approval_id as the execution_id in the journal."""
        return self.execution_journal.load_entry(approval_id)

    def _save_entry(self, entry: ExecutionJournalEntry) -> None:
        """Save the journal entry atomically."""
        self.execution_journal.save_entry(entry)

    def request_approval(self, proposal: ChangeProposal, task_id: str) -> ApprovalRequest:
        """Create an approval request for a proposal."""
        import uuid
        from datetime import datetime, timedelta

        approval_id = f"approval-{uuid.uuid4().hex[:12]}"
        expires_at = datetime.now() + timedelta(seconds=self.default_expiry_seconds)
        proposal_hash = proposal.compute_proposal_hash()

        # Create the journal entry
        entry = ExecutionJournalEntry(
            execution_id=approval_id,
            proposal_id=proposal.proposal_id,
            task_id=task_id,
            workspace_root=proposal.workspace_root,
            approval_id=approval_id,
            approval_status=ApprovalDecisionStatus.PENDING.value,
            approval_requested_at=datetime.now(),
            approval_expires_at=expires_at,
            approval_proposal_hash=proposal_hash,
            proposal_summary=proposal.rationale,
            affected_paths=proposal.get_target_paths(),
            validation_plan_summary=f"{len(proposal.validation_plan)} validation steps",
            permission_scope=f"change.{proposal.risk_level.value}",
            risk_level=proposal.risk_level.value,
        )
        self._save_entry(entry)

        # Return an ApprovalRequest object (mirroring the entry)
        return ApprovalRequest(
            approval_id=approval_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=proposal_hash,
            task_id=task_id,
            workspace_root=proposal.workspace_root,
            operation_type="change_application",
            risk_level=proposal.risk_level,
            approval_status=ApprovalDecisionStatus.PENDING,
            created_at=entry.approval_requested_at,
            expires_at=entry.approval_expires_at,
            decided_at=None,
            decided_by=None,
            decision=None,
            proposal_summary=proposal.rationale,
            affected_paths=proposal.get_target_paths(),
            validation_plan_summary=f"{len(proposal.validation_plan)} validation steps",
            permission_scope=f"change.{proposal.risk_level.value}",
        )

    def wait_for_approval(self, approval_id: str, cancellation_token: Optional[callable] = None, timeout: Optional[float] = None) -> ApprovalDecision:
        """Wait for an approval decision."""
        import time
        from datetime import datetime

        if timeout is None:
            timeout = self.default_expiry_seconds
        deadline = time.monotonic() + timeout

        while True:
            # Check for cancellation
            if cancellation_token and callable(cancellation_token):
                if cancellation_token():
                    # Cancel the request
                    entry = self._get_entry(approval_id)
                    if entry:
                        entry.approval_status = ApprovalDecisionStatus.CANCELLED.value
                        entry.approval_decided_by = "system"
                        entry.approval_decided_at = datetime.now()
                        entry.approval_decision_reason = "Cancelled by caller"
                        self._save_entry(entry)
                    decision = ApprovalDecision(
                        approval_id=approval_id,
                        proposal_id="",  # will be filled from entry if available
                        proposal_hash="",
                        decision="cancelled",
                        decided_by="system",
                        decided_at=datetime.now(),
                        status=ApprovalDecisionStatus.CANCELLED,
                        reason="Cancelled by caller",
                    )
                    return decision

            entry = self._get_entry(approval_id)
            if entry is None:
                raise ValueError(f"Approval request not found: {approval_id}")

            # Check expiration
            if entry.approval_expires_at and datetime.now() >= entry.approval_expires_at:
                entry.approval_status = ApprovalDecisionStatus.EXPIRED.value
                entry.approval_decided_by = "system"
                entry.approval_decided_at = datetime.now()
                entry.approval_decision_reason = "Approval request expired"
                self._save_entry(entry)
                decision = ApprovalDecision(
                    approval_id=approval_id,
                    proposal_id=entry.proposal_id,
                    proposal_hash=entry.approval_proposal_hash or "",
                    decision="expired",
                    decided_by="system",
                    decided_at=datetime.now(),
                    status=ApprovalDecisionStatus.EXPIRED,
                    reason="Approval request expired",
                )
                return decision

            # Check if decision already made
            if entry.approval_status in (ApprovalDecisionStatus.APPROVED.value, ApprovalDecisionStatus.REJECTED.value):
                decision = ApprovalDecision(
                    approval_id=approval_id,
                    proposal_id=entry.proposal_id,
                    proposal_hash=entry.approval_proposal_hash or "",
                    decision=entry.approval_status.lower(),  # "approved" or "rejected"
                    decided_by=entry.approval_decided_by or "",
                    decided_at=entry.approval_decided_at,
                    status=ApprovalDecisionStatus(entry.approval_status),
                    reason=entry.approval_decision_reason or "",
                )
                if decision.consumed:
                    raise RuntimeError(f"Approval {approval_id} already consumed")
                return decision

            # Check timeout
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Approval wait timed out after {timeout}s")

            # Small sleep to avoid busy wait
            time.sleep(0.1)

    def record_decision(self, approval_id: str, decision: str, decided_by: str, reason: str = "") -> ApprovalDecision:
        """Record an approval decision."""
        from datetime import datetime

        entry = self._get_entry(approval_id)
        if entry is None:
            raise ValueError(f"Approval request not found: {approval_id}")
        if entry.approval_status != ApprovalDecisionStatus.PENDING.value:
            raise RuntimeError(f"Decision already recorded for {approval_id}")
        if decision not in ("approved", "rejected"):
            raise ValueError(f"Invalid decision: {decision}")

        now = datetime.now()
        entry.approval_status = decision  # APPROVED or REJECTED
        entry.approval_decided_by = decided_by
        entry.approval_decided_at = now
        entry.approval_decision_reason = reason
        self._save_entry(entry)

        decision_record = ApprovalDecision(
            approval_id=approval_id,
            proposal_id=entry.proposal_id,
            proposal_hash=entry.approval_proposal_hash or "",
            decision=decision,
            decided_by=decided_by,
            decided_at=now,
            status=ApprovalDecisionStatus.APPROVED if decision == "approved" else ApprovalDecisionStatus.REJECTED,
            reason=reason,
        )
        return decision_record

    def consume_approval(self, approval_id: str) -> bool:
        """Mark an approval as consumed.

        Returns True if the approval was successfully consumed, False otherwise.
        This method is atomic under the journal's locking mechanism.
        """
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            # Mark as consumed
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception:
            return False
    def claim_approval(self, approval_id: str, proposal: Optional[ChangeProposal] = None) -> bool:
        """Claim an approval for execution, marking it as claimed and consumed.

        Returns True if the approval was successfully claimed, False otherwise.
        This method is atomic under the journal's locking mechanism.
        """
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, "approval_claimed", False):
                raise RuntimeError("Approval already claimed")
            # Check expiration
            if entry.approval_expires_at and datetime.now() >= entry.approval_expires_at:
                raise RuntimeError("Approval expired")
            # Check proposal hash if proposal provided
            if proposal is not None:
                if proposal.compute_proposal_hash() != entry.approval_proposal_hash:
                    raise RuntimeError("Proposal hash mismatch - proposal may have been modified")
                if proposal.proposal_id != entry.proposal_id:
                    raise RuntimeError("Proposal ID mismatch")
            # Mark as claimed and consumed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, "approval_claimed", False):
                raise RuntimeError("Approval already claimed")
            # Check expiration
            if entry.approval_expires_at and datetime.now() >= entry.approval_expires_at:
                raise RuntimeError("Approval expired")
            # Mark as claimed and consumed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, "approval_claimed", False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed and consumed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, "approval_claimed", False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, "approval_consumed", False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, "approval_claimed", False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed and consumed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Debug print
            print(f"DEBUG: claim_approval for {approval_id}: entry.approval_status={entry.approval_status}, entry.approval_claimed={getattr(entry, 'approval_claimed', 'NOT SET')}")
            # Check that the approval is approved and not already claimed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, 'approval_claimed', False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            print(f"DEBUG: claim_approval failed: {e}")
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, 'approval_claimed', False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
        def modifier(entry: ExecutionJournalEntry) -> None:
            # Check that the approval is approved and not already claimed or consumed
            if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
                raise RuntimeError(f"Approval is not approved: {entry.approval_status}")
            if getattr(entry, 'approval_consumed', False):
                raise RuntimeError("Approval already consumed")
            if getattr(entry, 'approval_claimed', False):
                raise RuntimeError("Approval already claimed")
            # Mark as claimed and consumed
            entry.approval_claimed = True
            entry.approval_claimed_at = datetime.now()
            entry.approval_consumed = True
            entry.approval_consumed_at = datetime.now()
            # Update the execution phase
            entry.execution_phase = 'execution_claimed'
            entry.last_confirmed_state = 'execution_claimed'

        try:
            self.execution_journal.update_entry(approval_id, modifier)
            return True
        except Exception as e:
            # Log the error if needed
            return False
    def get_decision(self, approval_id: str) -> Optional[ApprovalDecision]:
        """Get a recorded decision."""
        entry = self._get_entry(approval_id)
        if entry is None:
            return None
        if entry.approval_status not in (ApprovalDecisionStatus.APPROVED.value, ApprovalDecisionStatus.REJECTED.value):
            return None
        return ApprovalDecision(
            approval_id=approval_id,
            proposal_id=entry.proposal_id,
            proposal_hash=entry.approval_proposal_hash or "",
            decision=entry.approval_status.lower(),
            decided_by=entry.approval_decided_by or "",
            decided_at=entry.approval_decided_at,
            status=ApprovalDecisionStatus(entry.approval_status),
            reason=entry.approval_decision_reason or "",
        )

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Get a recorded approval request (regardless of status)."""
        entry = self._get_entry(approval_id)
        if entry is None:
            return None
        return ApprovalRequest(
            approval_id=approval_id,
            proposal_id=entry.proposal_id,
            proposal_hash=entry.approval_proposal_hash or "",
            task_id=entry.task_id,
            workspace_root=entry.workspace_root,
            operation_type="change_application",
            risk_level=RiskLevel(entry.risk_level) if entry.risk_level else RiskLevel.LOW,
            approval_status=ApprovalDecisionStatus(entry.approval_status),
            created_at=entry.approval_requested_at,
            expires_at=entry.approval_expires_at,
            decided_at=entry.approval_decided_at,
            decided_by=entry.approval_decided_by,
            decision=entry.approval_status.lower() if entry.approval_status in (ApprovalDecisionStatus.APPROVED.value, ApprovalDecisionStatus.REJECTED.value) else None,
            proposal_summary=entry.proposal_summary,
            affected_paths=entry.affected_paths,
            validation_plan_summary=entry.validation_plan_summary,
            permission_scope=entry.permission_scope,
        )

    def validate_approval(self, approval_id: str, proposal: ChangeProposal, expected_approver: Optional[str] = None) -> Tuple[bool, str]:
        """Validate that an approval is valid for the given proposal."""
        entry = self._get_entry(approval_id)
        if entry is None:
            return False, "No decision recorded"
        if entry.approval_status != ApprovalDecisionStatus.APPROVED.value:
            return False, f"Decision status: {entry.approval_status}"
        # Check consumption
        if getattr(entry, 'approval_consumed', False):
            return False, "Approval already consumed"
        # Check proposal hash matches
        if proposal.compute_proposal_hash() != entry.approval_proposal_hash:
            return False, "Proposal hash mismatch - proposal may have been modified"
        # Check proposal ID matches
        if proposal.proposal_id != entry.proposal_id:
            return False, "Proposal ID mismatch"
        # Check approver if specified
        if expected_approver and entry.approval_decided_by != expected_approver:
            return False, f"Approver mismatch: expected {expected_approver}, got {entry.approval_decided_by}"
        # Check expiration
        if entry.approval_expires_at and datetime.now() >= entry.approval_expires_at:
            return False, "Approval expired"
        return True, ""
