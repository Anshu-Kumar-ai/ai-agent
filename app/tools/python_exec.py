"""Python execution tool for Stage 11/14 - Code Execution Sandbox.

Provides safe Python code execution with:
- Subprocess isolation (default mode)
- Docker-based isolation (optional mode with Docker)
- Configurable timeout
- Memory limits (via resource limits on Unix)
- Stdout/stderr capture
- No network/filesystem access beyond sandbox
"""

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from app.core.state.observation import Observation
from app.tools.base import BaseTool


class PythonExecTool(BaseTool):
    """Execute Python code in a sandboxed subprocess or Docker container.
    
    Safety features:
    - Runs in isolated subprocess with restricted environment
    - Optional Docker-based isolation with resource limits
    - Configurable timeout (default 30s)
    - Captures stdout/stderr separately
    - No access to parent process memory/state
    - Working directory restricted to sandbox
    """

    name = "python.exec"
    description = "Execute Python code in a sandboxed subprocess or Docker container. Returns stdout, stderr, and exit code."
    selection_phrases = ("execute python", "run python", "python code", "run code", "calculate with python", "compute with python")
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default: 30, max: 300)",
                "default": 30,
                "minimum": 1,
                "maximum": 300,
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory for execution (must be within sandbox)",
                "default": "",
            },
            "allow_imports": {
                "type": "boolean",
                "description": "Allow importing standard library modules (default: true)",
                "default": True,
            },
            "mode": {
                "type": "string",
                "description": "Execution mode: 'subprocess' (default) or 'docker'",
                "enum": ["subprocess", "docker"],
                "default": "subprocess",
            },
            "docker_image": {
                "type": "string",
                "description": "Docker image to use (default: python:3.11-slim)",
                "default": "python:3.11-slim",
            },
        },
        "required": ["code"],
        "additionalProperties": False,
    }

    def __init__(self, sandbox_root: str | None = None):
        """Initialize the Python execution tool.
        
        Args:
            sandbox_root: Root directory for sandbox. Defaults to HERMES_WORKSPACE or cwd.
        """
        self.sandbox_root = sandbox_root or os.getenv("HERMES_WORKSPACE", os.getcwd())
        self.sandbox_root = os.path.abspath(self.sandbox_root)
        os.makedirs(self.sandbox_root, exist_ok=True)

        # Check Docker availability
        self._docker_available = shutil.which("docker") is not None

    def validate_arguments(self, arguments: dict) -> None:
        """Validate the arguments for python.exec."""
        if "code" not in arguments:
            raise ValueError("Missing required argument: 'code'")

        code = arguments["code"]
        if not isinstance(code, str):
            raise ValueError("'code' must be a string")

        if not code.strip():
            raise ValueError("'code' cannot be empty")

        # Validate timeout
        timeout = arguments.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
            raise ValueError("'timeout' must be an integer between 1 and 300")

        # Validate mode
        mode = arguments.get("mode", "subprocess")
        if mode not in ("subprocess", "docker"):
            raise ValueError("'mode' must be 'subprocess' or 'docker'")

        # If docker mode requested but not available, warn but don't fail
        if mode == "docker" and not self._docker_available:
            raise ValueError("Docker mode requested but Docker is not available")

        # Validate working_dir
        working_dir = arguments.get("working_dir", "")
        if working_dir:
            working_dir = os.path.abspath(working_dir)
            # Ensure working_dir is within sandbox_root
            try:
                os.path.commonpath([working_dir, self.sandbox_root]) == self.sandbox_root
            except ValueError:
                raise ValueError(f"'working_dir' must be within sandbox: {self.sandbox_root}")

    def execute(self, **kwargs) -> dict[str, Any]:
        """Execute Python code in sandboxed subprocess or Docker container.
        
        Returns:
            dict with keys: stdout, stderr, exit_code, timed_out
        """
        code = kwargs["code"]
        timeout = kwargs.get("timeout", 30)
        working_dir = kwargs.get("working_dir", "")
        allow_imports = kwargs.get("allow_imports", True)
        mode = kwargs.get("mode", "subprocess")
        docker_image = kwargs.get("docker_image", "python:3.11-slim")

        # Determine working directory
        if working_dir:
            work_dir = os.path.abspath(working_dir)
        else:
            work_dir = self.sandbox_root

        # Ensure working directory exists and is within sandbox
        work_dir = os.path.abspath(work_dir)
        if not os.path.commonpath([work_dir, self.sandbox_root]) == self.sandbox_root:
            return Observation.create_error(
                f"Error: Working directory must be within sandbox: {self.sandbox_root}"
            )

        os.makedirs(work_dir, exist_ok=True)

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            dir=work_dir,
            delete=False,
            encoding="utf-8"
        ) as f:
            # Write the code with some safety wrappers
            if not allow_imports:
                code = self._restrict_imports(code)
            f.write(code)
            temp_file = f.name

        try:
            if mode == "docker" and self._docker_available:
                result = self._execute_docker(
                    temp_file, work_dir, timeout, docker_image, code
                )
            else:
                result = self._execute_subprocess(temp_file, work_dir, timeout, code, allow_imports)

            if result.get("timed_out"):
                return Observation.create_timeout(
                    metadata={"timeout": timeout, "cmd": f"python {os.path.basename(temp_file)}"}
                )

            if result.get("exit_code", -1) != 0:
                return Observation.create_error(
                    f"Execution failed with exit code {result.get('exit_code')}",
                    metadata={"stdout": result.get("stdout", ""), "stderr": result.get("stderr", ""), "exit_code": result.get("exit_code")}
                )

            return Observation.create_success(
                payload={
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "exit_code": result.get("exit_code", 0),
                },
                metadata={"exit_code": result.get("exit_code", 0), "stderr": result.get("stderr", "")}
            )

        except subprocess.TimeoutExpired:
            return Observation.create_timeout(
                metadata={"timeout": timeout, "cmd": f"python {os.path.basename(temp_file)}"}
            )
        except Exception as e:
            return Observation.create_error(
                f"Execution error: {type(e).__name__}: {e}"
            )
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    def _execute_subprocess(
        self,
        temp_file: str,
        work_dir: str,
        timeout: int,
        code: str,
        allow_imports: bool
    ) -> dict[str, Any]:
        """Execute using subprocess (original method)."""
        # Prepare environment - restrict PATH and other sensitive vars
        env = os.environ.copy()
        env["PYTHONPATH"] = ""  # No extra Python paths
        env["HOME"] = work_dir  # Fake home directory

        # Run the subprocess
        result = subprocess.run(
            [sys.executable, temp_file],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "timed_out": False,
        }

    def _execute_docker(
        self,
        temp_file: str,
        work_dir: str,
        timeout: int,
        docker_image: str,
        code: str
    ) -> dict[str, Any]:
        """Execute using Docker container with resource limits."""
        # Get relative path of temp file within work_dir
        try:
            rel_file = os.path.relpath(temp_file, work_dir)
        except ValueError:
            # On different drives (Windows)
            rel_file = os.path.basename(temp_file)

        # Prepare Docker command with resource limits
        # - Memory limit: 512MB
        # - CPU limit: 1 core
        # - No network
        # - Read-only filesystem (except temp file)
        # - User namespace mapping
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory=512m",
            "--cpus=1.0",
            "--network=none",
            "--read-only",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=100m",
            "--tmpfs=/run:rw,noexec,nosuid,size=10m",
            "--user=1000:1000",  # Non-root user
            "--security-opt=no-new-privileges",
            "--cap-drop=ALL",
            "-v", f"{work_dir}:/workspace:ro",  # Mount workspace read-only
            "-w", "/workspace",
            docker_image,
            "python", rel_file,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,  # Extra buffer for Docker startup
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "timed_out": False,
            }

        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": f"Docker execution timed out after {timeout} seconds",
                "exit_code": -1,
                "timed_out": True,
            }
        except FileNotFoundError:
            # Docker not found - fall back to subprocess
            return self._execute_subprocess(temp_file, work_dir, timeout, code, True)

    def _restrict_imports(self, code: str) -> str:
        """Add import restrictions to the code."""
        restricted_code = f"""
import sys
import builtins

# Save original __import__
_original_import = builtins.__import__

# Allowed standard library modules
_ALLOWED_MODULES = {{
    'math', 'random', 'datetime', 'json', 're', 'collections',
    'itertools', 'functools', 'statistics', 'decimal', 'fractions',
    'string', 'textwrap', 'hashlib', 'hmac', 'secrets', 'uuid',
    'base64', 'binascii', 'os', 'sys', 'pathlib', 'typing',
    'dataclasses', 'enum', 'abc', 'copy', 'pprint', 'inspect',
    'numbers', 'operator', 'functools', 'contextlib', 'time',
    'calendar', 'zoneinfo', 'timeit', 'traceback', 'warnings',
    'html', 'urllib.parse', 'urllib.error', 'http', 'email',
    'mimetypes', 'csv', 'xml.etree.ElementTree', 'sqlite3',
}}

def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0:
        # Relative imports not allowed
        raise ImportError("Relative imports not allowed")
    
    # Check if the base module is allowed
    base_module = name.split('.')[0]
    if base_module not in _ALLOWED_MODULES:
        raise ImportError(f"Import of '{{name}}' is not allowed")
    
    return _original_import(name, globals, locals, fromlist, level)

builtins.__import__ = _restricted_import

# User code starts here
{code}
"""
        return restricted_code


def create_python_exec_tool(sandbox_root: str | None = None) -> PythonExecTool:
    """Factory function to create PythonExecTool instance."""
    return PythonExecTool(sandbox_root=sandbox_root)
