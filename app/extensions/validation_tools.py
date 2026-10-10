"""
Validation Tools - Stage 32 Phase 10
Provides bounded validation command execution for test-guided repair workflows.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import subprocess
import os
import tempfile
import shutil
import hashlib
import json
import signal
import psutil
from pathlib import Path

from app.extensions.dynamic_tools import (
    ToolInterface,
    ToolMetadata,
    ToolResult,
    ToolResultStatus,
    EnhancedToolMetadata,
    ToolAvailability,
    ToolLifecycleState,
)
from app.extensions.change_proposal import (
    ValidationStep,
    is_command_allowed,
    validate_workspace_path,
    compute_file_hash,
)
from app.core.permissions import PermissionManager


class ValidationStatus(Enum):
    """Validation execution status."""
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class ValidationRequest:
    """Request for validation execution."""
    validation_id: str
    task_id: str
    workspace_root: str
    approved_command: str  # Pre-approved validation command/profile
    target_paths: List[str] = field(default_factory=list)  # Specific paths to validate, if applicable
    timeout_seconds: int = 30
    max_output_size: int = 10000  # Maximum stdout/stderr size to capture
    max_retry_count: int = 0
    expected_result: ValidationStatus = ValidationStatus.PASSED
    cancellation_token: Optional[Any] = None
    created_at: datetime = field(default_factory=datetime.now)
@dataclass
class ValidationResult:
    """Result of validation execution."""
    validation_id: str
    task_id: str
    status: ValidationStatus
    exit_code: Optional[int] = None
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    structured_failures: List[Dict[str, Any]] = field(default_factory=list)
    test_counts: Dict[str, int] = field(default_factory=dict)
    truncated: bool = False
    sanitized_diagnostics: str = ""
    validation_request: Optional[ValidationRequest] = None
    executed_at: datetime = field(default_factory=datetime.now)


class ValidationTool(ToolInterface):
    """
    Tool for executing bounded validation commands.
    Integrates with existing DynamicToolRegistry and PermissionManager.
    """

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.permission_manager = permission_manager
        self._metadata = EnhancedToolMetadata(
            name="validation_executor",
            description="Execute bounded validation commands for test-guided repair workflows",
            capability="validation.execute",
            arguments={
                "type": "object",
                "properties": {
                    "validation_request": {
                        "type": "object",
                        "properties": {
                            "validation_id": {"type": "string"},
                            "task_id": {"type": "string"},
                            "workspace_root": {"type": "string"},
                            "target_paths": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "approved_command": {"type": "string"},
                            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                            "max_output_size": {"type": "integer", "minimum": 1000, "maximum": 50000},
                            "max_retry_count": {"type": "integer", "minimum": 0, "maximum": 5},
                            "expected_result": {
                                "type": "string",
                                "enum": ["passed", "failed", "timed_out", "cancelled", "rejected", "unavailable", "error"]
                            }
                        },
                        "required": ["validation_id", "task_id", "workspace_root", "approved_command"]
                    }
                },
                "required": ["validation_request"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "validation_result": {
                        "type": "object",
                        "properties": {
                            "validation_id": {"type": "string"},
                            "task_id": {"type": "string"},
                            "status": {"type": "string"},
                            "exit_code": {"type": ["integer", "null"]},
                            "duration_seconds": {"type": "number"},
                            "stdout": {"type": "string"},
                            "stderr": {"type": "string"},
                            "structured_failures": {"type": "array"},
                            "test_counts": {"type": "object"},
                            "truncated": {"type": "boolean"},
                            "sanitized_diagnostics": {"type": "string"}
                        }
                    }
                },
                "required": ["validation_result"]
            },
            risk_level="low",
            side_effects=["process_execution", "temporary_file_creation"],
            permission_required="validation.execute",
            verification_required=True,
            availability_requirements=[],
            lifecycle_state=ToolLifecycleState.REGISTERED,
            emits_monitoring=True
        )

    def get_metadata(self) -> EnhancedToolMetadata:
        return self._metadata

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute a validation request with full bounding and security."""
        # Validate input arguments
        if "validation_request" not in arguments:
            raise ValueError("Missing validation_request in arguments")
        
        # Convert dict to ValidationRequest
        req_data = arguments["validation_request"]
        # Convert expected_result string to ValidationStatus enum if it's a string
        if "expected_result" in req_data and isinstance(req_data["expected_result"], str):
            try:
                req_data["expected_result"] = ValidationStatus(req_data["expected_result"])
            except ValueError:
                # If it's not a valid status, set to ERROR
                req_data["expected_result"] = ValidationStatus.ERROR
        validation_request = ValidationRequest(**req_data)
        
        # Execute the validation
        result = self._execute_validation(validation_request)
        
        # Return structured result
        return {"validation_result": self._result_to_dict(result)}

    def is_available(self) -> bool:
        """Check if validation tool is available."""
        return True  # Always available if dependencies are met

    def _execute_validation(self, request: ValidationRequest) -> ValidationResult:
        """Execute a bounded validation command."""
        start_time = datetime.utcnow()
        result = ValidationResult(
            validation_id=request.validation_id,
            task_id=request.task_id,
            status=ValidationStatus.ERROR,  # Default to error, will be updated
            validation_request=request
        )

        try:
            # 1. Validate workspace path
            is_valid, error = validate_workspace_path(request.workspace_root, "")
            if not is_valid:
                result.status = ValidationStatus.ERROR
                result.stderr = f"Invalid workspace: {error}"
                return result

            # 2. Validate target paths if specified
            for target_path in request.target_paths:
                is_valid, error = validate_workspace_path(request.workspace_root, target_path)
                if not is_valid:
                    result.status = ValidationStatus.ERROR
                    result.stderr = f"Invalid target path {target_path}: {error}"
                    return result

            # 3. Check if command is approved/allowed
            if not is_command_allowed(request.approved_command):
                result.status = ValidationStatus.REJECTED
                result.stderr = f"Command not in validation allowlist: {request.approved_command}"
                return result

            # 4. Check permissions
            if self.permission_manager:
                # In a real implementation, we would check specific validation permissions
                # For now, we'll assume the permission manager handles this through its normal flow
                pass

            # 5. Execute command with bounds
            env = os.environ.copy()
            # Limit environment to prevent leakage
            safe_env = {
                k: v for k, v in env.items() 
                if not any(sensitive in k.lower() for sensitive in 
                          ['key', 'token', 'secret', 'password', 'auth', 'credential'])
            }
            safe_env.update({
                'PATH': os.environ.get('PATH', ''),
                'HOME': os.environ.get('HOME', ''),
                'USER': os.environ.get('USER', ''),
                'LANG': os.environ.get('LANG', 'C.UTF-8'),
                'LC_ALL': os.environ.get('LC_ALL', 'C.UTF-8')
            })

            # Prepare process
            proc = None
            try:
                # Use Popen for better control over timeout and output bounding
                proc = subprocess.Popen(
                    request.approved_command.split(),
                    cwd=request.workspace_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=safe_env,
                    bufsize=1,  # Line buffered
                    universal_newlines=True
                )

                # Monitor output with size bounding
                stdout_lines = []
                stderr_lines = []
                stdout_truncated = False
                stderr_truncated = False

                def read_output(pipe, lines_list, max_size, truncated_flag):
                    """Read output from pipe with size bounding."""
                    size_so_far = 0
                    try:
                        for line in iter(pipe.readline, ''):
                            lines_list.append(line)
                            size_so_far += len(line.encode('utf-8'))
                            if size_so_far >= max_size:
                                truncated_flag[0] = True
                                # Consume remaining output without storing
                                for _ in pipe:
                                    pass
                                break
                    except Exception:
                        pass

                # Use threads to read stdout and stderr concurrently
                import threading
                stdout_truncated_flag = [False]
                stderr_truncated_flag = [False]
                
                stdout_thread = threading.Thread(
                    target=read_output, 
                    args=(proc.stdout, stdout_lines, request.max_output_size // 2, stdout_truncated_flag)
                )
                stderr_thread = threading.Thread(
                    target=read_output, 
                    args=(proc.stderr, stderr_lines, request.max_output_size // 2, stderr_truncated_flag)
                )
                
                stdout_thread.start()
                stderr_thread.start()

                # Wait for completion with timeout
                try:
                    proc.wait(timeout=request.timeout_seconds)
                    stdout_thread.join(timeout=5)
                    stderr_thread.join(timeout=5)
                except subprocess.TimeoutExpired:
                    # Timeout exceeded
                    result.status = ValidationStatus.TIMED_OUT
                    # Try to terminate the process tree
                    self._terminate_process_tree(proc.pid)
                    result.stderr = f"Validation timed out after {request.timeout_seconds} seconds"
                    result.stdout = ''.join(stdout_lines)
                    result.stderr += ''.join(stderr_lines)
                    result.truncated = stdout_truncated_flag[0] or stderr_truncated_flag[0]
                    result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
                    return result

                # Get final output
                stdout_content = ''.join(stdout_lines)
                stderr_content = ''.join(stderr_lines)
                result.stdout = stdout_content
                result.stderr = stderr_content
                result.truncated = stdout_truncated_flag[0] or stderr_truncated_flag[0]
                result.exit_code = proc.returncode
                result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()

                # Determine status based on exit code and expected result
                if proc.returncode == 0:
                    result.status = ValidationStatus.PASSED
                else:
                    result.status = ValidationStatus.FAILED

                # Check if result matches expected
                if result.status != request.expected_result:
                    # Note this in diagnostics but don't change status - the actual result is what matters
                    result.sanitized_diagnostics = f"Expected {request.expected_result.value}, got {result.status.value}"

                # Parse test output if it looks like test results
                result.test_counts = self._parse_test_counts(stdout_content, stderr_content)
                result.structured_failures = self._parse_structured_failures(stdout_content, stderr_content)
                result.sanitized_diagnostics += self._sanitize_diagnostics(stdout_content, stderr_content)

                return result

            except Exception as e:
                result.status = ValidationStatus.ERROR
                result.stderr = f"Validation execution error: {str(e)}"
                result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
                if proc and proc.poll() is None:
                    self._terminate_process_tree(proc.pid)
                return result

        except Exception as e:
            result.status = ValidationStatus.ERROR
            result.stderr = f"Validation setup error: {str(e)}"
            result.duration_seconds = (datetime.utcnow() - start_time).total_seconds()
            return result

    def _terminate_process_tree(self, pid: int):
        """Terminate a process and its children."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            parent.terminate()
            gone, alive = psutil.wait_procs(children + [parent], timeout=3)
            for p in alive:
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # Process already gone or no permission

    def _parse_test_counts(self, stdout: str, stderr: str) -> Dict[str, int]:
        """Parse test counts from output."""
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        combined = stdout + stderr
        
        # Look for common test result patterns
        import re
        
        # pytest style: "=== 5 passed, 2 failed, 1 skipped in 0.12s ==="
        pytest_match = re.search(r'(\d+)\s+passed[^\d]*(\d+)\s+failed[^\d]*(\d+)\s+skipped', combined, re.IGNORECASE)
        if pytest_match:
            counts["passed"] = int(pytest_match.group(1))
            counts["failed"] = int(pytest_match.group(2))
            counts["skipped"] = int(pytest_match.group(3))
            return counts
            
        # unittest style: "Ran 5 tests in 0.001s\n\nOK" or "FAILED (failures=2, errors=1)"
        if "OK" in combined and "FAILED" not in combined:
            # Extract number of tests from "Ran X tests"
            ran_match = re.search(r'Ran\s+(\d+)\s+tests', combined)
            if ran_match:
                counts["passed"] = int(ran_match.group(1))
        elif "FAILED" in combined:
            failure_match = re.search(r'failures=(\d+)', combined)
            error_match = re.search(r'errors=(\d+)', combined)
            ran_match = re.search(r'Ran\s+(\d+)\s+tests', combined)
            if ran_match:
                total = int(ran_match.group(1))
                counts["failed"] = int(failure_match.group(1)) if failure_match else 0
                counts["errors"] = int(error_match.group(1)) if error_match else 0
                counts["passed"] = total - counts["failed"] - counts["errors"]
                
        return counts

    def _parse_structured_failures(self, stdout: str, stderr: str) -> List[Dict[str, Any]]:
        """Parse structured failure information."""
        failures = []
        combined = stdout + stderr
        
        # Extract failure details from tracebacks or assertion errors
        lines = combined.split('\n')
        current_failure = {}
        
        for i, line in enumerate(lines):
            if "FAILED" in line or "AssertionError" in line or line.strip().startswith("E   "):
                # Start of a failure
                if current_failure:
                    failures.append(current_failure)
                current_failure = {
                    "raw": line.strip(),
                    "line_number": i,
                    "type": "assertion_failure" if "AssertionError" in line else "test_failure"
                }
            elif current_failure and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                # End of current failure block
                failures.append(current_failure)
                current_failure = {}
            elif current_failure:
                current_failure["raw"] = current_failure.get("raw", "") + "\n" + line.strip()
                
        if current_failure:
            failures.append(current_failure)
            
        return failures[:10]  # Limit to prevent excessive output

    def _sanitize_diagnostics(self, stdout: str, stderr: str) -> str:
        """Sanitize diagnostic output by removing sensitive information."""
        # Remove potential secrets, tokens, keys
        import re
        
        # Patterns for common secret formats
        patterns = [
            (r'[a-zA-Z0-9_-]{20,}', '[REDACTED_TOKEN]'),  # Long alphanumeric strings (tokens/keys)
            (r'[\w.-]+@[\w.-]+\.\w+', '[REDACTED_EMAIL]'),  # Email addresses
            (r'https?://[^\s]+', '[REDACTED_URL]'),  # URLs
            (r'AKIA[0-9A-Z]{16}', '[REDACTED_AWS_KEY]'),  # AWS access key pattern
            (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[REDACTED_UUID]'),  # UUIDs
        ]
        
        sanitized_stdout = stdout
        sanitized_stderr = stderr
        
        for pattern, replacement in patterns:
            sanitized_stdout = re.sub(pattern, replacement, sanitized_stdout, flags=re.IGNORECASE)
            sanitized_stderr = re.sub(pattern, replacement, sanitized_stderr, flags=re.IGNORECASE)
            
        # Truncate if too large
        max_size = 2000
        if len(sanitized_stdout) > max_size:
            sanitized_stdout = sanitized_stdout[:max_size//2] + "\n... [TRUNCATED] ...\n" + sanitized_stdout[-max_size//2:]
        if len(sanitized_stderr) > max_size:
            sanitized_stderr = sanitized_stderr[:max_size//2] + "\n... [TRUNCATED] ...\n" + sanitized_stderr[-max_size//2:]
            
        return f"STDOUT: {sanitized_stdout}\nSTDERR: {sanitized_stderr}"

    def _result_to_dict(self, result: ValidationResult) -> Dict[str, Any]:
        """Convert ValidationResult to dictionary for serialization."""
        return {
            "validation_id": result.validation_id,
            "task_id": result.task_id,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "structured_failures": result.structured_failures,
            "test_counts": result.test_counts,
            "truncated": result.truncated,
            "sanitized_diagnostics": result.sanitized_diagnostics
        }


def create_validation_tool(permission_manager: Optional[PermissionManager] = None) -> ValidationTool:
    """Factory function to create a validation tool instance."""
    return ValidationTool(permission_manager)


# Register the validation tool with the dynamic tool system when imported
def register_validation_tool(dynamic_registry):
    """Register the validation tool with a dynamic tool registry."""
    tool = create_validation_tool()
    dynamic_registry.register_tool(tool)
    return tool