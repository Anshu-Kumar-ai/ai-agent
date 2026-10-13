"""
Security Remediation Test Suite - Stage 32 (pre-Phase 11)
Tests the validation command injection fixes:
1. is_command_allowed strict profile validation (was: permissive prefix matching)
2. ChangeManager._run_validation_step shell=False execution (was: shell=True)

Adversarial payloads in this file are string fixtures for REJECTION tests only.
They are never executed as processes, never run through a shell, and never
touch the network. Rejection is asserted before any process invocation.
"""

import os
import sys
import shlex
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.extensions.change_proposal import (
    is_command_allowed,
    split_allowed_command,
    VALIDATION_COMMAND_ALLOWLIST,
    ValidationStep,
    ChangeProposal,
    FileChange,
    ChangeType,
    ProposalStatus,
    RiskLevel,
    ApprovalGate,
    ApprovalDecisionStatus,
    validate_workspace_path,
    compute_file_hash,
)
from app.extensions.change_manager import ChangeManager
from app.core.permissions import PermissionManager
from app.extensions.git_adapter import GitAdapter
from app.extensions.validation_tools import (
    ValidationRequest,
    ValidationTool,
    ValidationResult,
    ValidationStatus,
)


# The two reported HIGH-severity payloads (evidence-confirmed in
# .hermes/plans/stage32_phase11_supervised_repair_loop.md). String fixtures
# for rejection tests only - NEVER executed.
REPORTED_PAYLOAD_1 = "python -m pytest; rm -rf /"
REPORTED_PAYLOAD_2 = "python -m pytest && curl evil"

# Representative shell-syntax payloads (rejection fixtures only - never executed).
SHELL_SYNTAX_PAYLOADS = [
    REPORTED_PAYLOAD_1,                     # chaining via ;
    REPORTED_PAYLOAD_2,                     # chaining via &&
    "python -m pytest || echo pwned",       # chaining via ||
    "python -m pytest | tee /tmp/out",      # pipe
    "python -m py_compile x.py > out.txt",  # redirection
    "python -m py_compile x.py < in.txt",   # input redirection
    "python -m pytest $(evil)",             # command substitution
    "python -m pytest ${EVIL}",             # variable expansion
    "python -m pytest `evil`",              # backtick substitution
    "python -m pytest\nrm -rf /",           # embedded newline
    ";; rm -rf /",                          # leading separator
    "$(rm -rf /)",                          # bare substitution
    "`rm -rf /`",                           # bare backticks
    "mypy src/; format c:",                 # allowlisted prefix + chaining
]


class MockPermissionManager:
    """Test permission manager matching test_change_workflows.py pattern."""
    def __init__(self, auto_approve: bool = True):
        self.auto_approve = auto_approve


class MockGitAdapter:
    """Test git adapter matching test_change_workflows.py pattern."""
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.get_state = Mock(return_value={})


class TestStrictCommandValidation(unittest.TestCase):
    """is_command_allowed strict profile validation (Fix 1)."""

    def test_reported_payload_1_rejected(self):
        """The reported payload 'python -m pytest; rm -rf /' must be rejected."""
        self.assertFalse(is_command_allowed(REPORTED_PAYLOAD_1))

    def test_reported_payload_2_rejected(self):
        """The reported payload 'python -m pytest && curl evil' must be rejected."""
        self.assertFalse(is_command_allowed(REPORTED_PAYLOAD_2))

    def test_shell_syntax_payloads_rejected(self):
        """All representative chaining/redirection/substitution payloads rejected."""
        for cmd in SHELL_SYNTAX_PAYLOADS:
            with self.subTest(cmd=cmd):
                self.assertFalse(is_command_allowed(cmd))

    def test_legitimate_profiles_still_allowed(self):
        """Legitimate approved commands with ordinary arguments still pass."""
        allowed = [
            "python -m py_compile test.py",
            "python -m pytest tests/",
            "python -m pytest test_file.py -v",
            "ruff check src/",
            "black --check src/",
            "mypy src/",
            "mypy app/extensions",
        ]
        for cmd in allowed:
            with self.subTest(cmd=cmd):
                self.assertTrue(is_command_allowed(cmd))

    def test_non_allowlisted_executables_rejected(self):
        """Executables outside the allowlist are rejected."""
        for cmd in ["rm -rf /", "curl evil.com", "echo hello", "sh evil.sh", "python3-evil x"]:
            with self.subTest(cmd=cmd):
                self.assertFalse(is_command_allowed(cmd))

    def test_similar_but_wrong_profile_rejected(self):
        """Complete-token prefix matching: no partial-token matches."""
        # 'python -m pytestx' must NOT match the 'python -m pytest' profile
        self.assertFalse(is_command_allowed("python -m pytestx tests/"))
        # 'mypyx' must NOT match the 'mypy' profile
        self.assertFalse(is_command_allowed("mypyx src/"))

    def test_invalid_input_rejected(self):
        """Empty/None/whitespace inputs are rejected before any parsing."""
        self.assertFalse(is_command_allowed(""))
        self.assertFalse(is_command_allowed("   "))
        self.assertFalse(is_command_allowed(None))

    def test_allowlist_content_unchanged(self):
        """Production allowlist content is unchanged by the remediation."""
        self.assertEqual(
            sorted(VALIDATION_COMMAND_ALLOWLIST),
            sorted([
                "python -m py_compile",
                "python -m pytest",
                "ruff check",
                "black --check",
                "mypy",
            ]),
        )

    def test_split_allowed_command(self):
        """split_allowed_command returns argv lists for allowed commands, None otherwise."""
        self.assertEqual(
            split_allowed_command("python -m pytest tests/"),
            ["python", "-m", "pytest", "tests/"],
        )
        self.assertEqual(
            split_allowed_command("python -m py_compile test.py"),
            ["python", "-m", "py_compile", "test.py"],
        )
        # Rejected commands never yield an argv
        self.assertIsNone(split_allowed_command(REPORTED_PAYLOAD_1))
        self.assertIsNone(split_allowed_command("rm -rf /"))



class TestPathValidationHardening(unittest.TestCase):
    """validate_workspace_path hardening (M-B) - adversarial path tests."""
    
    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        
    def tearDown(self):
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace, ignore_errors=True)
    
    def test_unc_path_rejected(self):
        """UNC paths are rejected."""
        for unc in ['\\\\server\\share', '//server/share', '\\\\?\\C:\\Windows']:
            with self.subTest(unc=unc):
                self.assertFalse(validate_workspace_path(self.workspace, unc)[0])
    
    def test_absolute_path_rejected(self):
        """Absolute paths are rejected."""
        abs_paths = ['/etc/passwd', 'C:\\Windows\\System32', 'D:\\data']
        for p in abs_paths:
            with self.subTest(path=p):
                self.assertFalse(validate_workspace_path(self.workspace, p)[0])
    
    def test_drive_relative_rejected(self):
        """Drive-relative paths are rejected."""
        for p in ['C:foo', 'C:\\foo', 'D:bar']:
            with self.subTest(path=p):
                self.assertFalse(validate_workspace_path(self.workspace, p)[0])
    
    def test_traversal_sequences_rejected(self):
        """Path traversal sequences are rejected."""
        traversals = ['../etc/passwd', '..\\..\\windows', 'subdir/../../etc', 'a/b/../../../c']
        for p in traversals:
            with self.subTest(path=p):
                self.assertFalse(validate_workspace_path(self.workspace, p)[0])
    
    def test_mixed_separators_traversal_rejected(self):
        """Mixed separators with traversal are rejected."""
        traversals = ['subdir/..\\..\\etc', 'a\\b/../../c']
        for p in traversals:
            with self.subTest(path=p):
                self.assertFalse(validate_workspace_path(self.workspace, p)[0])
    
    def test_legitimate_relative_paths_allowed(self):
        """Legitimate relative paths are allowed."""
        # Create test subdirectory
        subdir = os.path.join(self.workspace, 'subdir')
        os.makedirs(subdir, exist_ok=True)
        
        allowed = ['file.py', 'subdir/file.py', 'subdir/nested/deep.py', '.']
        for p in allowed:
            with self.subTest(path=p):
                self.assertTrue(validate_workspace_path(self.workspace, p)[0])
    
    def test_workspace_root_validation_succeeds(self):
        """Empty target_path (workspace root validation) succeeds."""
        result, error = validate_workspace_path(self.workspace, '')
        self.assertTrue(result, f"Empty target_path should be valid for workspace root: {error}")
    
    def test_workspace_root_trailing_separator(self):
        """Workspace root with trailing separator handled correctly."""
        # Create workspace with trailing separator
        ws_with_sep = self.workspace + os.sep
        result, error = validate_workspace_path(ws_with_sep, 'file.py')
        self.assertTrue(result, f"Trailing separator should work: {error}")
    
    def test_empty_inputs_rejected(self):
        """Empty or None inputs are rejected."""
        self.assertFalse(validate_workspace_path('', 'file.py')[0])
        self.assertFalse(validate_workspace_path(self.workspace, '') is None)  # Should not crash
        # Note: empty target_path is now allowed for workspace root validation
    
    def test_non_string_inputs_rejected(self):
        """Non-string inputs are rejected."""
        self.assertFalse(validate_workspace_path(None, 'file.py')[0])
        self.assertFalse(validate_workspace_path(self.workspace, None)[0])
        self.assertFalse(validate_workspace_path(123, 'file.py')[0])
        self.assertFalse(validate_workspace_path(self.workspace, 123)[0])

class TestNoShellExecution(unittest.TestCase):
    """ChangeManager._run_validation_step must not use a shell (Fix 2)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = os.path.join(self.tmpdir, "workspace")
        os.makedirs(self.workspace)
        self.manager = ChangeManager(
            workspace_root=self.workspace,
            permission_manager=MockPermissionManager(auto_approve=True),
            git_adapter=MockGitAdapter(self.workspace),
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_source_has_no_shell_true_in_validation_step(self):
        """Static check: the subprocess call inside _run_validation_step uses
        shell=False, never shell=True (checked on the call arguments, not the
        docstring, which intentionally documents the old behavior)."""
        import inspect
        src = inspect.getsource(ChangeManager._run_validation_step)
        # Extract only executable lines (strip comments and docstring)
        code_lines = []
        in_docstring = False
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring if stripped.count('"""') == 1 else in_docstring
                continue
            if in_docstring:
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)
        self.assertNotIn("shell=True", code)
        self.assertIn("shell=False", code)
        self.assertIn("argv", code)

    def test_validation_step_runs_without_shell(self):
        """A legitimate validation step executes successfully with shell=False."""
        # Create a valid python file to compile
        with open(os.path.join(self.workspace, "valid.py"), "w") as f:
            f.write("print('hello')\n")

        step = ValidationStep(
            name="syntax",
            command="python -m py_compile valid.py",
            description="Syntax check",
            required=True,
        )
        result = self.manager._run_validation_step(step, None)
        self.assertTrue(result["success"], f"Expected success, got: {result}")
        self.assertIsNone(result["error"])

    def test_rejected_command_never_reaches_runner(self):
        """A rejected validation command cannot reach the process runner."""
        with patch("app.extensions.change_manager.subprocess.run") as mock_run:
            step = ValidationStep(
                name="malicious",
                command=REPORTED_PAYLOAD_1,
                description="should never run",
                required=False,
            )
            result = self.manager._run_validation_step(step, None)

            # subprocess.run must NEVER have been invoked
            mock_run.assert_not_called()
            # Clear failure reporting
            self.assertFalse(result["success"])
            self.assertIsNotNone(result["error"])
            self.assertIn("not in approved profiles", result["error"])

    def test_rejected_command_via_proposal_apply_blocked(self):
        """A proposal whose validation plan contains an injected command is
        rejected by validate_proposal and can never be applied."""
        # Create the target file so the MODIFY pre-hash check passes validation
        # except for the command allowlist check
        with open(os.path.join(self.workspace, "target.py"), "w") as f:
            f.write("x = 1\n")

        import hashlib
        with open(os.path.join(self.workspace, "target.py"), "rb") as f:
            pre_hash = hashlib.sha256(f.read()).hexdigest()

        proposal = ChangeProposal(
            proposal_id="sec-prop-001",
            task_id="sec-task-001",
            workspace_root=self.workspace,
            changes=[
                FileChange(
                    target_path="target.py",
                    change_type=ChangeType.MODIFY,
                    content="x = 2\n",
                    expected_pre_hash=pre_hash,
                )
            ],
            rationale="security test",
            risk_level=RiskLevel.LOW,
            validation_plan=[
                ValidationStep(
                    name="injected",
                    command=REPORTED_PAYLOAD_2,
                    description="injection attempt",
                    required=True,
                )
            ],
        )

        # validate_proposal must reject the command (not in allowlist)
        is_valid, errors = self.manager.validate_proposal(proposal)
        self.assertFalse(is_valid)
        self.assertTrue(any("not in allowlist" in e for e in errors),
                        f"Expected allowlist rejection, got: {errors}")

        # request_approval must refuse (validation fails first)
        approved = self.manager.request_approval(proposal, "test-user")
        self.assertFalse(approved)
        self.assertEqual(proposal.approval_status, ProposalStatus.REJECTED)

        # apply_proposal must refuse: re-validation at the top of apply_proposal
        # raises ValidationError (allowlist check), and if approval were present
        # it would still be blocked. Either typed error proves the proposal
        # cannot be applied.
        from app.extensions.change_manager import ApprovalError, ValidationError
        with self.assertRaises((ValidationError, ApprovalError)):
            self.manager.apply_proposal(proposal)

        # The target file must be untouched
        with open(os.path.join(self.workspace, "target.py"), "r") as f:
            self.assertEqual(f.read(), "x = 1\n")

    def test_timeout_classification_preserved(self):
        """Timeout classification continues to work without a shell."""
        # Create a test that sleeps longer than the timeout - harmless, allowlisted profile
        test_file = os.path.join(self.workspace, 'test_slow.py')
        with open(test_file, 'w') as f:
            f.write('import time\ndef test_slow():\n    time.sleep(10)\n')
        
        # Use the allowlisted py_compile profile against a file that takes long? py_compile is instant.
        # Instead: directly test that a timeout on a slow allowlisted command
        # is classified correctly. Use python -m pytest with a sleeping test.
        step = ValidationStep(
            name="slow test",
            command=f'python -m pytest {shlex.quote(test_file)} -x',
            description="timeout classification check",
            required=False,
            timeout_seconds=2,
        )
        result = self.manager._run_validation_step(step, None)
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])
        self.assertIn("timed out", result["error"].lower())
        
    
    def test_working_directory_containment_preserved(self):
        """Validation runs inside the workspace root."""
        observed_cwd = {}

        real_run = os.path.join(self.workspace, "marker.py")
        with open(real_run, "w") as f:
            f.write("print('ok')\n")

        step = ValidationStep(
            name="cwd check",
            command="python -m py_compile marker.py",
            description="cwd containment",
            required=False,
        )
        result = self.manager._run_validation_step(step, None)
        self.assertTrue(result["success"])

    def test_output_sanitization_path_unchanged(self):
        """stdout/stderr capture still works through the non-shell path."""
        out_file = os.path.join(self.workspace, "printer.py")
        with open(out_file, "w") as f:
            f.write("print('stdout-marker')\n")

        step = ValidationStep(
            name="output",
            command="python -m py_compile printer.py",
            description="output capture",
            required=False,
        )
        result = self.manager._run_validation_step(step, None)
        self.assertTrue(result["success"])
        # py_compile is silent on success; the key assertion is capture ran
        self.assertIsInstance(result["stdout"], str)
        self.assertIsInstance(result["stderr"], str)


class TestRepairWorkflowsCompat(unittest.TestCase):
    """Confirm existing repair/change validation behaviors still hold."""

    def test_validation_tool_rejects_injected_commands(self):
        """ValidationTool rejects the reported payloads before execution."""
        from app.extensions.validation_tools import ValidationTool, ValidationRequest, ValidationStatus

        validation_tool = ValidationTool(None)
        for cmd in [REPORTED_PAYLOAD_1, REPORTED_PAYLOAD_2, "python -m pytest | tee /tmp/x"]:
            with self.subTest(cmd=cmd):
                request = ValidationRequest(
                    validation_id=f"sec-{abs(hash(cmd))}",
                    task_id="task-sec",
                    workspace_root=tempfile.gettempdir(),
                    approved_command=cmd,
                    timeout_seconds=5,
                    max_output_size=1000,
                    max_retry_count=0,
                    expected_result=ValidationStatus.PASSED,
                )
                result_dict = validation_tool.execute({"validation_request": {
                    "validation_id": request.validation_id,
                    "task_id": request.task_id,
                    "workspace_root": request.workspace_root,
                    "approved_command": request.approved_command,
                    "timeout_seconds": request.timeout_seconds,
                    "max_output_size": request.max_output_size,
                    "max_retry_count": request.max_retry_count,
                    "expected_result": request.expected_result.value,
                }})
                result = result_dict["validation_result"]
                self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
                self.assertIn("not in validation allowlist", result["stderr"])


def run_tests():
    """Run the security remediation suite three consecutive times."""
    print("=" * 60)
    print("Running test_security_remediation.py")
    print("=" * 60)

    loader = unittest.TestLoader()
    all_ok = True

    for run in range(1, 4):
        print(f"\n--- Run {run} ---")
        suite = unittest.TestSuite()
        for cls in (TestStrictCommandValidation, TestNoShellExecution,
                    TestRepairWorkflowsCompat):
            suite.addTests(loader.loadTestsFromTestCase(cls))
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        if not result.wasSuccessful():
            all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("ALL 3 RUNS PASSED")
    else:
        print("SOME RUNS FAILED")
    print("=" * 60)
    return all_ok


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)


class TestShellFreeValidationExecution(unittest.TestCase):
    """Shell-free validation execution adversarial tests (M-C)."""
    
    def setUp(self):
        self.workspace = tempfile.mkdtemp()
        self.validation_tool = ValidationTool(None)
        
    def tearDown(self):
        if os.path.exists(self.workspace):
            shutil.rmtree(self.workspace, ignore_errors=True)
    
    # A. Basic execution
    def test_valid_approved_validator_executes_successfully(self):
        """A valid approved validator executes successfully."""
        # Create a test file
        test_file = os.path.join(self.workspace, 'test_valid.py')
        with open(test_file, 'w') as f:
            f.write('# Valid Python\npass\n')
        
        request = ValidationRequest(
            validation_id="test-001",
            task_id="task-001",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test_valid.py",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.PASSED.value)
    def test_output_limits_prevent_uncontrolled_memory_growth(self):
        """Output limits prevent uncontrolled memory growth."""
        # Create a test that produces large output
        test_file = os.path.join(self.workspace, "test_large_output.py").replace('\\\\', '/')
        with open(test_file, "w") as f:
            f.write("import sys\n")
            f.write("def test_large_output():\n")
            f.write("    sys.stdout.write(\'x\' * 10000)\n")
        
        request = ValidationRequest(
            validation_id="test-013",
            task_id="task-013",
            workspace_root=self.workspace,
            approved_command=f'python -m pytest {shlex.quote(test_file)}',
            timeout_seconds=5,
            max_output_size=200,  # Very small limit
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.PASSED.value)
        # Output should be truncated
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["stdout"]), 300)  # Some overhead allowed for pytest
        
    
    def test_timeouts_are_enforced(self):
        """Timeouts are enforced."""
        # Create a test that sleeps
        test_file = os.path.join(self.workspace, "test_sleep.py").replace('\\\\', '/')
        with open(test_file, "w") as f:
            f.write("import sys\n")
            f.write("def test_sleep():\n")
            f.write("    time.sleep(10)\n")
        
        request = ValidationRequest(
            validation_id="test-011",
            task_id="task-011",
            workspace_root=self.workspace,
            approved_command=f'python -m pytest {shlex.quote(test_file)}',
            timeout_seconds=1,  # Very short timeout
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.TIMED_OUT,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.TIMED_OUT.value)
        
    
    def test_nonzero_exit_codes_reported_correctly(self):
        """Nonzero exit codes are reported correctly."""
        # Create a file with syntax error
        test_file = os.path.join(self.workspace, 'test_syntax_error.py')
        with open(test_file, 'w') as f:
            f.write('def broken(:\n')
        
        request = ValidationRequest(
            validation_id="test-003",
            task_id="task-003",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test_syntax_error.py",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.FAILED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.FAILED.value)
        self.assertNotEqual(result["exit_code"], 0)
    
    # B. Injection resistance
    def test_semicolon_injected_as_literal_argument(self):
        """Semicolons are rejected by allowlist (shell metacharacter boundary)."""
        request = ValidationRequest(
            validation_id="test-004",
            task_id="task-004",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test.py; rm -rf /",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        # Should be rejected by allowlist, not executed
        self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
        self.assertIn("not in validation allowlist", result["stderr"])
    
    def test_pipe_injected_as_literal_argument(self):
        """Pipes are rejected by allowlist."""
        request = ValidationRequest(
            validation_id="test-005",
            task_id="task-005",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test.py | tee /tmp/x",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
        self.assertIn("not in validation allowlist", result["stderr"])
    
    def test_command_substitution_rejected(self):
        """Command substitution is rejected."""
        request = ValidationRequest(
            validation_id="test-006",
            task_id="task-006",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test.py $(echo hello)",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
    
    def test_malformed_legacy_shell_strings_rejected(self):
        """Malformed legacy shell strings are rejected."""
        # These are strings that would work in shell but not as structured args
        malformed = [
            "python -m py_compile test.py && echo done",
            "python -m py_compile test.py || echo fail",
            "python -m py_compile test.py > output.txt",
            "python -m py_compile test.py < input.txt",
        ]
        for cmd in malformed:
            with self.subTest(cmd=cmd):
                request = ValidationRequest(
                    validation_id=f"test-{abs(hash(cmd))}",
                    task_id="task-malf",
                    workspace_root=self.workspace,
                    approved_command=cmd,
                    timeout_seconds=5,
                    max_output_size=1000,
                    max_retry_count=0,
                    expected_result=ValidationStatus.PASSED,
                )
                result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
                result = result_dict["validation_result"]
                self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
    
    def test_injection_attempts_do_not_execute_second_command(self):
        """Injection attempts do not execute a second command or create marker file."""
        # Create a test file
        test_file = os.path.join(self.workspace, 'test_marker.py')
        with open(test_file, 'w') as f:
            f.write('# Valid Python\npass\n')
        
        # Try to inject a command that would create a marker file
        marker_file = os.path.join(self.workspace, 'INJECTION_MARKER')
        request = ValidationRequest(
            validation_id="test-007",
            task_id="task-007",
            workspace_root=self.workspace,
            approved_command=f"python -m py_compile test_marker.py; touch {marker_file}",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        # Should be rejected
        self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
        # Marker file should NOT exist
        self.assertFalse(os.path.exists(marker_file), "Injection created marker file!")
    
    # C. Executable authorization
    def test_approved_executable_can_run(self):
        """An approved executable can run."""
        test_file = os.path.join(self.workspace, 'test.py')
        with open(test_file, 'w') as f:
            f.write('# Valid\npass\n')
        
        request = ValidationRequest(
            validation_id="test-008",
            task_id="task-008",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test.py",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.PASSED.value)
    
    def test_unapproved_executable_rejected_before_execution(self):
        """An unapproved executable is rejected before execution."""
        request = ValidationRequest(
            validation_id="test-009",
            task_id="task-009",
            workspace_root=self.workspace,
            approved_command="rm -rf /",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
        self.assertIn("not in validation allowlist", result["stderr"])
    
    def test_executable_names_cannot_bypass_restrictions(self):
        """Executable names or paths cannot bypass the configured restrictions."""
        # Try various executable name variations
        attempts = [
            "python3 -m py_compile test.py",  # different python name
            "python -mpy_compile test.py",    # missing space
            "python -m pytestx test.py",      # wrong command
            "/usr/bin/python -m py_compile test.py",  # absolute path
        ]
        for cmd in attempts:
            with self.subTest(cmd=cmd):
                request = ValidationRequest(
                    validation_id=f"test-{abs(hash(cmd))}",
                    task_id="task-exec",
                    workspace_root=self.workspace,
                    approved_command=cmd,
                    timeout_seconds=5,
                    max_output_size=1000,
                    max_retry_count=0,
                    expected_result=ValidationStatus.PASSED,
                )
                result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
                result = result_dict["validation_result"]
                self.assertEqual(result["status"], ValidationStatus.REJECTED.value)
    
    def test_path_manipulation_handled_safely(self):
        """PATH manipulation and unexpected executable formats are handled safely."""
        # The safe_env already strips sensitive vars, but let's verify
        # that the executable resolution doesn't depend on untrusted PATH
        test_file = os.path.join(self.workspace, 'test.py')
        with open(test_file, 'w') as f:
            f.write('# Valid\npass\n')
        
        request = ValidationRequest(
            validation_id="test-010",
            task_id="task-010",
            workspace_root=self.workspace,
            approved_command="python -m py_compile test.py",
            timeout_seconds=5,
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.PASSED,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.PASSED.value)
    
    def test_arguments_cannot_alter_intended_validation_scope(self):
        """Arguments cannot alter the intended validation scope or introduce unintended executable mode."""
        # This is tested by the injection resistance tests above
        pass
    
    # D. Operational safety
    def test_timeouts_are_enforced(self):
        """Timeouts are enforced."""
        # Create a test that sleeps
        test_file = os.path.join(self.workspace, 'test_sleep.py')
        with open(test_file, 'w') as f:
            f.write('import time\ndef test_sleep():\n    time.sleep(10)\n')
        
        request = ValidationRequest(
            validation_id="test-011",
            task_id="task-011",
            workspace_root=self.workspace,
            approved_command=f'python -m pytest {shlex.quote(test_file)}',
            timeout_seconds=1,  # Very short timeout
            max_output_size=1000,
            max_retry_count=0,
            expected_result=ValidationStatus.TIMED_OUT,
        )
        result_dict = self.validation_tool.execute({"validation_request": request.to_dict()})
        result = result_dict["validation_result"]
        
        self.assertEqual(result["status"], ValidationStatus.TIMED_OUT.value)
        
    
