"""
Execution journal for durable approval and repair execution state.

Provides atomic JSON-based persistence for recovery after crashes or restarts.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID, uuid4

class FileLock:
    """A simple file-based lock using directory creation for atomicity."""
    def __init__(self, lock_path, timeout=1.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.acquired = False

    def acquire(self):
        """Acquire the lock, waiting up to timeout seconds."""
        import time
        start = time.time()
        while True:
            try:
                os.mkdir(self.lock_path)
                self.acquired = True
                return
            except FileExistsError:
                if self.timeout is not None and time.time() - start > self.timeout:
                    raise TimeoutError(f"Could not acquire lock on {self.lock_path}")
                time.sleep(0.01)  # 10 ms
            except Exception as e:
                # Re-raise other exceptions (e.g., permission denied)
                raise

    def release(self):
        """Release the lock."""
        if self.acquired:
            os.rmdir(self.lock_path)
            self.acquired = False


class ExecutionJournalEntry:
    """A single execution record in the journal."""
    def __init__(
        self,
        execution_id: str,
        proposal_id: str,
        task_id: str,
        workspace_root: str,
        approval_id: Optional[str] = None,
        approval_status: Optional[str] = None,  # Stores ApprovalDecisionStatus.value (string): pending, approved, rejected, claimed
        approval_requested_at: Optional[datetime] = None,
        approval_expires_at: Optional[datetime] = None,
        approval_decided_by: Optional[str] = None,
        approval_decided_at: Optional[datetime] = None,
        approval_decision_reason: Optional[str] = None,
        approval_proposal_hash: Optional[str] = None,  # Hash of the proposal at request time
        approval_consumed: bool = False,
        approval_consumed_at: Optional[datetime] = None,
        approval_claimed: bool = False,
        approval_claimed_at: Optional[datetime] = None,
        proposal_summary: str = "",
        affected_paths: Optional[List[str]] = None,
        validation_plan_summary: str = "",
        permission_scope: str = "",
        risk_level: Optional[str] = None,  # Stores RiskLevel.value (string): low, medium, high, critical
        execution_phase: str = "initiated",
        last_confirmed_state: str = "",
        expected_file_hashes: Optional[Dict[str, Any]] = None,
        proposed_file_hashes: Optional[Dict[str, Any]] = None,
        per_file_status: Optional[Dict[str, Any]] = None,
        validation_status: Optional[str] = None,
        cancellation_requested: bool = False,
        timeout_occurred: bool = False,
        failure_information: Optional[Dict[str, Any]] = None,
        recovery_status: str = "none",
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Create an execution journal entry."""
        self.execution_id = execution_id
        self.proposal_id = proposal_id
        self.task_id = task_id
        self.workspace_root = workspace_root
        self.approval_id = approval_id
        self.approval_status = approval_status
        self.approval_requested_at = approval_requested_at
        self.approval_expires_at = approval_expires_at
        self.approval_decided_by = approval_decided_by
        self.approval_decided_at = approval_decided_at
        self.approval_decision_reason = approval_decision_reason
        self.approval_proposal_hash = approval_proposal_hash
        self.approval_consumed = approval_consumed
        self.approval_consumed_at = approval_consumed_at
        self.approval_claimed = approval_claimed
        self.approval_claimed_at = approval_claimed_at
        self.proposal_summary = proposal_summary
        self.affected_paths = affected_paths
        self.validation_plan_summary = validation_plan_summary
        self.permission_scope = permission_scope
        self.risk_level = risk_level
        self.execution_phase = execution_phase
        self.last_confirmed_state = last_confirmed_state
        self.expected_file_hashes = expected_file_hashes
        self.proposed_file_hashes = proposed_file_hashes
        self.per_file_status = per_file_status
        self.validation_status = validation_status
        self.cancellation_requested = cancellation_requested
        self.timeout_occurred = timeout_occurred
        self.failure_information = failure_information
        self.recovery_status = recovery_status
        self.created_at = created_at if created_at is not None else datetime.now()
        self.updated_at = updated_at if updated_at is not None else self.created_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'execution_id': self.execution_id,
            'proposal_id': self.proposal_id,
            'task_id': self.task_id,
            'workspace_root': self.workspace_root,
            'approval_id': self.approval_id,
            'approval_status': self.approval_status,
            'approval_requested_at': self.approval_requested_at.isoformat() if self.approval_requested_at else None,
            'approval_expires_at': self.approval_expires_at.isoformat() if self.approval_expires_at else None,
            'approval_decided_by': self.approval_decided_by,
            'approval_decided_at': self.approval_decided_at.isoformat() if self.approval_decided_at else None,
            'approval_decision_reason': self.approval_decision_reason,
            'approval_proposal_hash': self.approval_proposal_hash,
            'approval_consumed': self.approval_consumed,
            'approval_consumed_at': self.approval_consumed_at.isoformat() if self.approval_consumed_at else None,
            'approval_claimed': self.approval_claimed,
            'approval_claimed_at': self.approval_claimed_at.isoformat() if self.approval_claimed_at else None,
            'proposal_summary': self.proposal_summary,
            'affected_paths': self.affected_paths,
            'validation_plan_summary': self.validation_plan_summary,
            'permission_scope': self.permission_scope,
            'risk_level': self.risk_level,
            'execution_phase': self.execution_phase,
            'last_confirmed_state': self.last_confirmed_state,
            'expected_file_hashes': self.expected_file_hashes,
            'proposed_file_hashes': self.proposed_file_hashes,
            'per_file_status': self.per_file_status,
            'validation_status': self.validation_status,
            'cancellation_requested': self.cancellation_requested,
            'timeout_occurred': self.timeout_occurred,
            'failure_information': self.failure_information,
            'recovery_status': self.recovery_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionJournalEntry':
        """Create from dictionary (JSON deserialization)."""
        return cls(
            execution_id=data['execution_id'],
            proposal_id=data['proposal_id'],
            task_id=data['task_id'],
            workspace_root=data['workspace_root'],
            approval_id=data.get('approval_id'),
            approval_status=data.get('approval_status'),
            approval_requested_at=datetime.fromisoformat(data['approval_requested_at']) if data.get('approval_requested_at') else None,
            approval_expires_at=datetime.fromisoformat(data['approval_expires_at']) if data.get('approval_expires_at') else None,
            approval_decided_by=data.get('approval_decided_by'),
            approval_decided_at=datetime.fromisoformat(data['approval_decided_at']) if data.get('approval_decided_at') else None,
            approval_decision_reason=data.get('approval_decision_reason'),
            approval_proposal_hash=data.get('approval_proposal_hash'),
            approval_consumed=data.get('approval_consumed', False),
            approval_consumed_at=datetime.fromisoformat(data['approval_consumed_at']) if data.get('approval_consumed_at') else None,
            approval_claimed=data.get('approval_claimed', False),
            approval_claimed_at=datetime.fromisoformat(data['approval_claimed_at']) if data.get('approval_claimed_at') else None,
            proposal_summary=data.get('proposal_summary', ''),
            affected_paths=data.get('affected_paths', []),
            validation_plan_summary=data.get('validation_plan_summary', ''),
            permission_scope=data.get('permission_scope', ''),
            risk_level=data.get('risk_level'),
            execution_phase=data.get('execution_phase', 'initiated'),
            last_confirmed_state=data.get('last_confirmed_state', ''),
            expected_file_hashes=data.get('expected_file_hashes', {}),
            proposed_file_hashes=data.get('proposed_file_hashes', {}),
            per_file_status=data.get('per_file_status', {}),
            validation_status=data.get('validation_status'),
            cancellation_requested=data.get('cancellation_requested', False),
            timeout_occurred=data.get('timeout_occurred', False),
            failure_information=data.get('failure_information', {}),
            recovery_status=data.get('recovery_status', 'none'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None,
        )


class ExecutionJournal:
    """A collection of execution journal entries stored as JSON files."""
    def __init__(self, journal_dir: str = ".hermes/execution_journal"):
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    def _get_entry_path(self, execution_id: str) -> Path:
        """Get the file path for an execution journal entry."""
        return self.journal_dir / f"{execution_id}.json"

    def _get_lock_path(self, execution_id: str) -> str:
        """Get the file path for the lock file associated with an execution ID."""
        return str(self._get_entry_path(execution_id)) + ".lock"

    def _load_entry_unlocked(self, execution_id: str) -> Optional[ExecutionJournalEntry]:
        """Load an execution journal entry by ID without locking."""
        entry_path = self._get_entry_path(execution_id)
        if not entry_path.exists():
            return None
        with open(entry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ExecutionJournalEntry.from_dict(data)

    def _save_entry_unlocked(self, entry: ExecutionJournalEntry) -> None:
        """Save an execution journal entry atomically without locking."""
        entry.updated_at = datetime.now()
        entry_path = self._get_entry_path(entry.execution_id)
        temp_path = entry_path.with_suffix(".json.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2, sort_keys=True)
        # Atomic replace
        temp_path.replace(entry_path)

    def save_entry(self, entry: ExecutionJournalEntry) -> None:
        """Save an execution journal entry atomically with locking."""
        lock_path = self._get_lock_path(entry.execution_id)
        lock = FileLock(lock_path, timeout=1.0)
        try:
            lock.acquire()
            self._save_entry_unlocked(entry)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise
        finally:
            lock.release()

    def load_entry(self, execution_id: str) -> Optional[ExecutionJournalEntry]:
        """Load an execution journal entry by ID with locking."""
        lock_path = self._get_lock_path(execution_id)
        lock = FileLock(lock_path, timeout=1.0)
        try:
            lock.acquire()
            return self._load_entry_unlocked(execution_id)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Corrupted journal entry - treat as missing
            return None
        finally:
            lock.release()

    def update_entry(self, execution_id: str, modifier: callable) -> None:
        """Load an entry, apply a modifier function, and save it atomically under lock."""
        lock_path = self._get_lock_path(execution_id)
        lock = FileLock(lock_path, timeout=1.0)
        try:
            lock.acquire()
            entry = self._load_entry_unlocked(execution_id)
            if entry is None:
                raise ValueError(f"Entry not found: {execution_id}")
            modifier(entry)
            self._save_entry_unlocked(entry)
        finally:
            lock.release()

    def delete_entry(self, execution_id: str) -> bool:
        """Delete an execution journal entry with locking."""
        entry_path = self._get_entry_path(execution_id)
        if not entry_path.exists():
            return False
        lock_path = self._get_lock_path(execution_id)
        lock = FileLock(lock_path, timeout=1.0)
        try:
            lock.acquire()
            entry_path.unlink()
            return True
        finally:
            lock.release()

    def list_entries(self) -> List[str]:
        """List all execution IDs in the journal."""
        if not self.journal_dir.exists():
            return []
        return [f.stem for f in self.journal_dir.glob("*.json") if not f.name.endswith('.tmp')]

    def cleanup_old_entries(self, max_age_days: int = 30) -> int:
        """Remove journal entries older than max_age_days."""
        cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        removed_count = 0
        for entry_path in self.journal_dir.glob("*.json"):
            if entry_path.name.endswith('.tmp'):
                continue
            try:
                if entry_path.stat().st_mtime < cutoff_time:
                    entry_path.unlink()
                    removed_count += 1
            except OSError:
                # Skip files we can't access
                continue
        return removed_count
