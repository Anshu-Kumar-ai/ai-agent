"""
Unit and integration tests for SupervisedRepairLoop and related components.
"""

import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.extensions.repair_loop import (
    RepairLoopState,
    RepairLoopOutcome,
    RepairLoopReport,
    convert_repair_to_change_proposal,
    SupervisedRepairLoop,
)
from app.extensions.repair_proposal import (
    RepairProposal,
    RepairProposalRequest,
    RepairRiskLevel,
    ValidationStep as RepairValidationStep,
    FileChange,
    ConfidenceLevel,
)
from app.extensions.change_proposal import (
    ChangeProposal,
    FileChange,
    ChangeType,
    ProposalStatus,
    RiskLevel,
    ValidationStep as ChangeValidationStep,
)
from app.extensions.validation_tools import (
    ValidationRequest,
    ValidationResult,
    ValidationStatus,
)
from app.extensions.failure_analyzer import (
    FailureAnalysisResult,
)


class TestRepairProposalToChangeProposalConverter(unittest.TestCase):
    """Test the RepairProposal to ChangeProposal converter."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.workspace_root = tempfile.mkdtemp()
        self.task_id = "test-task-001"
        
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.workspace_root):
            shutil.rmtree(self.workspace_root)
    
    def _make_repair_proposal(self, changes=None, code_change_justified=True):
        """Create a test RepairProposal."""
        if changes is None:
            changes = [
                FileChange(
                    target_path="test_file.py",
                    change_type=ChangeType.MODIFY,
                    content="# Fixed content\n",
                    expected_pre_hash="abc123",
                    expected_post_hash="def456",
                )
            ]
        
        failure_analysis = FailureAnalysisResult(
            analysis_id="analysis-001",
            task_id=self.task_id,
            failure_summary="Syntax error in test_file.py",
            evidence=["line 10: missing colon"],
            affected_files=["test_file.py"],
            likely_cause="missing_colon",
            hypotheses=["missing colon after if statement"],
            confidence_level=ConfidenceLevel.HIGH,
            suggested_next_step="Add missing colon",
            code_change_justified=code_change_justified,
        )
        
        validation_result = ValidationResult(
            validation_id="val-001",
            task_id=self.task_id,
            status=ValidationStatus.FAILED,
            validation_request=Mock(),
        )
        
        return RepairProposal(
            proposal_id="repair-001",
            request_id="req-001",
            task_id=self.task_id,
            workspace_root=self.workspace_root,
            changes=changes,
            rationale="Fix missing colon",
            risk_level=RepairRiskLevel.LOW,
            validation_plan=[
                RepairValidationStep(
                    name="syntax_check",
                    command="python -m py_compile test_file.py",
                    description="Verify syntax",
                    required=True,
                    timeout_seconds=30,
                )
            ],
            observed_failure=validation_result,
            failure_analysis=failure_analysis,
            expected_success_criteria=["Syntax check passes"],
            rollback_strategy="standard",
        )
    
    def test_converter_preserves_hashes_paths_and_validation(self):
        """Test that converter produces ChangeProposal with identical hashes, paths, validation plan."""
        repair_proposal = self._make_repair_proposal()
        
        change_proposal = convert_repair_to_change_proposal(
            repair_proposal, self.task_id, self.workspace_root
        )
        
        # Check identity preservation
        self.assertEqual(change_proposal.task_id, self.task_id)
        self.assertEqual(change_proposal.workspace_root, self.workspace_root)
        self.assertEqual(len(change_proposal.changes), 1)
        
        # Check path preservation
        self.assertEqual(change_proposal.changes[0].target_path, "test_file.py")
        self.assertEqual(change_proposal.changes[0].change_type, ChangeType.MODIFY)
        self.assertEqual(change_proposal.changes[0].content, "# Fixed content\n")
        self.assertEqual(change_proposal.changes[0].expected_pre_hash, "abc123")
        self.assertEqual(change_proposal.changes[0].expected_post_hash, "def456")
        
        # Check validation plan conversion
        self.assertEqual(len(change_proposal.validation_plan), 1)
        self.assertEqual(change_proposal.validation_plan[0].name, "syntax_check")
        self.assertEqual(change_proposal.validation_plan[0].command, "python -m py_compile test_file.py")
        
        # Check hash stability
        hash1 = change_proposal.compute_proposal_hash()
        hash2 = change_proposal.compute_proposal_hash()
        self.assertEqual(hash1, hash2)
        
        # Check hash changes with content mutation
        original_rationale = change_proposal.rationale
        change_proposal.rationale = "Different rationale"
        hash3 = change_proposal.compute_proposal_hash()
        self.assertNotEqual(hash1, hash3)
        
        # Restore and verify hash matches again
        change_proposal.rationale = original_rationale
        hash4 = change_proposal.compute_proposal_hash()
        self.assertEqual(hash1, hash4)
    
    def test_converter_rejects_empty_changes(self):
        """Test that converter rejects proposals with empty changes."""
        repair_proposal = self._make_repair_proposal(changes=[])
        
        with self.assertRaises(ValueError) as cm:
            convert_repair_to_change_proposal(repair_proposal, self.task_id, self.workspace_root)
        
        self.assertIn("empty changes", str(cm.exception).lower())
    
    def test_converter_rejects_unjustified_code_change(self):
        """Test that converter rejects proposals where code_change_justified is False."""
        repair_proposal = self._make_repair_proposal(code_change_justified=False)
        
        with self.assertRaises(ValueError) as cm:
            convert_repair_to_change_proposal(repair_proposal, self.task_id, self.workspace_root)
        
        self.assertIn("code_change_justified is False", str(cm.exception))


class TestSyntaxFixPrecedenceBug(unittest.TestCase):
    """Test the fix for the _attempt_syntax_fix precedence bug."""
    
    def test_missing_colon_after_if_without_comment(self):
        """Test that missing colon after if is detected and fixed."""
        from app.extensions.repair_proposal import RepairProposalGenerator
        
        generator = RepairProposalGenerator()
        
        content = """def test():
    if True
        print("hello")
"""
        fixed = generator._attempt_syntax_fix(content, "missing_colon")
        self.assertIn("if True:", fixed)
    
    def test_missing_colon_after_if_with_comment(self):
        """Test that missing colon after if with comment is handled correctly."""
        from app.extensions.repair_proposal import RepairProposalGenerator
        
        generator = RepairProposalGenerator()
        
        content = """def test():
    if True  # some comment
        print("hello")
"""
        fixed = generator._attempt_syntax_fix(content, "missing_colon")
        # Should NOT add colon because there's already a colon in the code part (there isn't one)
        # Actually this line doesn't have a colon in the code part, so it SHOULD add one
        # But the bug was that the precedence was wrong
        # With the fix, it should correctly detect no colon in code part and add one
        self.assertIn("if True  # some comment:", fixed)
    
    def test_existing_colon_not_duplicated(self):
        """Test that existing colons are not duplicated."""
        from app.extensions.repair_proposal import RepairProposalGenerator
        
        generator = RepairProposalGenerator()
        
        content = """def test():
    if True:
        print("hello")
"""
        fixed = generator._attempt_syntax_fix(content, "missing_colon")
        # Should not add another colon
        self.assertEqual(fixed.count("if True:"), 1)
    
    def test_missing_colon_for_various_constructs(self):
        """Test missing colon detection for various Python constructs."""
        from app.extensions.repair_proposal import RepairProposalGenerator
        
        generator = RepairProposalGenerator()
        
        constructs = [
            "if True",
            "elif False",
            "else",  # special case - no space after
            "for i in range(10)",
            "while True",
            "def func()",
            "class MyClass",
            "try:",  # try is special - usually followed by : directly
            "except ValueError",  # this one works
            "finally:",  # finally is special
            "with open('test')",
        ]
        
        for construct in constructs:
            content = f"{construct}\n    pass\n"
            fixed = generator._attempt_syntax_fix(content, "missing_colon")
            # Should add colon to the construct line
            if construct == "else":
                self.assertIn("else:", fixed)
            elif construct == "try:":
                self.assertIn("try:", fixed)
            elif construct == "finally:":
                self.assertIn("finally:", fixed)
            else:
                self.assertIn(f"{construct}:", fixed)


class TestSupervisedRepairLoopBasic(unittest.TestCase):
    """Basic tests for SupervisedRepairLoop initialization and state."""
    
    def setUp(self):
        self.workspace_root = tempfile.mkdtemp()
        self.task_id = "test-task-002"
    
    def tearDown(self):
        if os.path.exists(self.workspace_root):
            shutil.rmtree(self.workspace_root)
    
    def test_initialization(self):
        """Test that SupervisedRepairLoop initializes correctly."""
        loop = SupervisedRepairLoop(
            workspace_root=self.workspace_root,
            task_id=self.task_id,
            max_iterations=2,
        )
        
        self.assertEqual(loop.workspace_root, self.workspace_root)
        self.assertEqual(loop.task_id, self.task_id)
        self.assertEqual(loop.max_iterations, 2)
        self.assertEqual(loop.state, RepairLoopState.INIT)
        self.assertIsNotNone(loop.loop_id)
        self.assertIsNotNone(loop.report)
        self.assertEqual(loop.report.task_id, self.task_id)
        self.assertEqual(loop.report.workspace_root, self.workspace_root)
    
    def test_state_machine_transitions(self):
        """Test that state machine transitions work."""
        loop = SupervisedRepairLoop(
            workspace_root=self.workspace_root,
            task_id=self.task_id,
        )
        
        loop._update_state(RepairLoopState.VALIDATION_RUNNING)
        self.assertEqual(loop.state, RepairLoopState.VALIDATION_RUNNING)
        
        loop._update_state(RepairLoopState.ANALYSIS_RUNNING)
        self.assertEqual(loop.state, RepairLoopState.ANALYSIS_RUNNING)
        
        loop._update_state(RepairLoopState.APPROVAL_REQUIRED)
        self.assertEqual(loop.state, RepairLoopState.APPROVAL_REQUIRED)
    
    def test_cancellation_check(self):
        """Test cancellation token checking."""
        cancelled = False
        
        def cancel_token():
            return cancelled
        
        loop = SupervisedRepairLoop(
            workspace_root=self.workspace_root,
            task_id=self.task_id,
            cancellation_token=cancel_token,
        )
        
        self.assertFalse(loop._check_cancellation())
        
        cancelled = True
        self.assertTrue(loop._check_cancellation())
    
    def test_report_structure(self):
        """Test that RepairLoopReport has correct structure."""
        loop = SupervisedRepairLoop(
            workspace_root=self.workspace_root,
            task_id=self.task_id,
        )
        
        report = loop.report
        self.assertEqual(report.task_id, self.task_id)
        self.assertEqual(report.workspace_root, self.workspace_root)
        self.assertEqual(report.max_iterations, 2)
        self.assertIsNone(report.outcome)
        self.assertEqual(report.iteration_count, 0)
        self.assertIsInstance(report.validation_results, list)
        self.assertIsInstance(report.applied_changes, list)
        self.assertIsInstance(report.evidence, list)
        self.assertIsInstance(report.uncertainties, list)


class TestRepairLoopReportSerialization(unittest.TestCase):
    """Test RepairLoopReport serialization."""
    
    def test_to_dict(self):
        """Test report serialization to dict."""
        report = RepairLoopReport(
            task_id="test-001",
            workspace_root="/tmp/test",
            loop_id="loop-abc123",
            start_time=datetime.now(),
            outcome=RepairLoopOutcome.COMPLETED,
            iteration_count=1,
        )
        
        d = report.to_dict()
        
        self.assertEqual(d["task_id"], "test-001")
        self.assertEqual(d["workspace_root"], "/tmp/test")
        self.assertEqual(d["loop_id"], "loop-abc123")
        self.assertEqual(d["outcome"], "completed")
        self.assertEqual(d["iteration_count"], 1)
        self.assertIn("start_time", d)
        self.assertIn("end_time", d)
        self.assertIsNone(d["end_time"])


if __name__ == "__main__":
    unittest.main()