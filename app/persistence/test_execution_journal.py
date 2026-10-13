"""
Test for execution journal persistence.
"""

import tempfile
import os
from app.persistence.execution_journal import ExecutionJournal, ExecutionJournalEntry
from app.extensions.change_proposal import ApprovalDecisionStatus
from datetime import datetime, timedelta

def test_execution_journal():
    """Test the execution journal persistence."""
    with tempfile.TemporaryDirectory() as temp_dir:
        journal = ExecutionJournal(journal_dir=os.path.join(temp_dir, "journal"))

        # Create a test entry
        entry = ExecutionJournalEntry(
            execution_id="test-exec-001",
            proposal_id="prop-123",
            task_id="task-456",
            workspace_root="/tmp/test",
            approval_id="approval-789",
            approval_status=ApprovalDecisionStatus.APPROVED.value,  # Store the enum value
            execution_phase="applying_changes",
            last_confirmed_state="files_prepared",
            expected_file_hashes={"file1.txt": "abc123"},
            proposed_file_hashes={"file1.txt": "def456"},
            per_file_status={"file1.txt": "pending"},
            validation_status="pending"
        )

        # Save the entry
        journal.save_entry(entry)
        assert journal.list_entries() == ["test-exec-001"]

        # Load the entry
        loaded_entry = journal.load_entry("test-exec-001")
        assert loaded_entry is not None
        assert loaded_entry.execution_id == "test-exec-001"
        assert loaded_entry.proposal_id == "prop-123"
        # approval_status is stored as string, so we compare to the enum value
        assert loaded_entry.approval_status == ApprovalDecisionStatus.APPROVED.value
        assert loaded_entry.execution_phase == "applying_changes"
        assert loaded_entry.expected_file_hashes == {"file1.txt": "abc123"}

        # Delete the entry
        assert journal.delete_entry("test-exec-001") == True
        assert journal.list_entries() == []

        # Try to load deleted entry
        assert journal.load_entry("test-exec-001") is None

        print("✓ All execution journal tests passed")

if __name__ == "__main__":
    test_execution_journal()
