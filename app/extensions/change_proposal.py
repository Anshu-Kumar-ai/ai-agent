"""
Change Proposal Contract - Stage 32 Phase 9
Defines the structured contract for proposing, validating, and applying local code changes.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import hashlib
import os


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
    tokens = command.split()
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
    return command.split()


def validate_workspace_path(workspace_root: str, target_path: str) -> tuple[bool, str]:
    """
    Validate that a target path is within the workspace.
    
    Returns (is_valid, error_message)
    """
    # Normalize paths
    workspace_root = os.path.abspath(workspace_root)
    target_abs = os.path.abspath(os.path.join(workspace_root, target_path))
    
    # Check for UNC path FIRST (before general traversal check)
    if target_path.startswith('\\\\') or target_path.startswith('//'):
        return False, f"UNC path not allowed: {target_path}"
    
    # Check for absolute path escape
    if os.path.isabs(target_path):
        return False, f"Absolute path not allowed: {target_path}"
    
    # Check for drive-relative path (Windows)
    if len(target_path) >= 2 and target_path[1] == ':':
        return False, f"Drive-relative path not allowed: {target_path}"
    
    # Check for traversal sequences in the original path (both / and \ separators)
    if '..' in target_path.replace('\\', '/').split('/'):
        return False, f"Path traversal detected: {target_path}"
    
    # Check for path traversal via normalized path
    if not target_abs.startswith(workspace_root + os.sep) and target_abs != workspace_root:
        return False, f"Path escapes workspace: {target_path}"
    
    # Check for symlink/reparse point (best effort on Windows)
    # Note: Full symlink resolution requires os.readlink which may not be available
    try:
        if os.path.islink(target_abs):
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