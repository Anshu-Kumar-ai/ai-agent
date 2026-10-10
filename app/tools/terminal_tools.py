import os
import re
import subprocess
import time
from typing import Any

from app.core.state.action import Action
from app.core.state.observation import Observation, ToolStatus
from app.tools.base_tool_pc import Tool


def _normalize_and_validate_path(path: str, workspace_root: str) -> tuple[bool, str, str]:
    """
    Normalize a path and validate it's within the workspace.
    Relative paths are resolved against workspace_root.
    
    Returns: (is_valid, normalized_path_or_error, error_message)
    """
    if not path or not isinstance(path, str):
        return False, "", "Empty or invalid path"
    
    workspace_abs = os.path.abspath(workspace_root)
    
    # Normalize the path
    try:
        # Expand environment variables and user home
        expanded = os.path.expandvars(os.path.expanduser(path))
        
        # Check for drive-relative paths (e.g., C:foo) BEFORE any normalization
        # These are resolved against the current directory on that drive, which
        # can escape the workspace if the current directory on that drive is
        # outside the workspace. For a strict workspace isolation boundary,
        # we reject all drive-relative paths.
        if len(expanded) >= 2 and expanded[1] == ":" and not expanded.startswith("\\") and not (len(expanded) >= 3 and expanded[2:3] in ["\\", "/"]):
            return False, expanded, f"Drive-relative paths (e.g., 'C:foo') are not allowed for workspace isolation"
        
        # Handle root-relative paths (e.g., \path) on Windows
        # These start with a single backslash and are relative to the current drive's root
        # os.path.isabs() returns True for these, but they should be resolved against workspace
        is_root_relative = expanded.startswith("\\") and not expanded.startswith("\\\\")
        
        if is_root_relative:
            # Root-relative path - resolve against workspace drive root
            workspace_drive = os.path.splitdrive(os.path.abspath(workspace_root))[0]
            normalized = os.path.normpath(os.path.join(workspace_drive + "\\", expanded.lstrip("\\")))
        elif os.path.isabs(expanded):
            # True absolute path
            normalized = os.path.normpath(expanded)
        else:
            # Relative path - resolve against workspace root
            normalized = os.path.normpath(os.path.join(workspace_abs, expanded))
        
        # Get absolute path
        absolute = os.path.abspath(normalized)
    except Exception as e:
        return False, "", f"Path normalization failed: {e}"
    
    # Check for UNC paths (\\server\\share) - but allow root-relative paths (\\path)
    if absolute.startswith("\\\\"):
        # Count path components after the initial \\
        remainder = absolute[2:]
        parts = remainder.split("\\")
        # True UNC path has at least server and share (2+ components)
        # Root-relative path has only 1 component (e.g., \\path)
        if len(parts) >= 2 and parts[0] and parts[1]:
            return False, absolute, "UNC paths are not allowed"
        # Root-relative path (\\path) - resolve against workspace drive
        # This will be caught by the commonpath check below
    
    # Check for drive-relative paths (e.g., C:foo)
    if len(absolute) >= 2 and absolute[1] == ":" and not absolute.startswith("\\\\"):
        return False, absolute, f"Drive-relative paths (e.g., 'C:foo') are not allowed for workspace isolation"
    
    # Use commonpath to check if path is within workspace
    try:
        common = os.path.commonpath([absolute, workspace_abs])
        
        if common != workspace_abs:
            return False, absolute, f"Path '{absolute}' resolves outside workspace '{workspace_abs}'"
    except ValueError:
        # Different drives on Windows - paths can't be compared
        return False, absolute, f"Path '{absolute}' is on a different drive than workspace"
    
    # Check for symlinks/reparse points that might escape
    try:
        real_path = os.path.realpath(absolute)
        real_workspace = os.path.realpath(workspace_abs)
        common_real = os.path.commonpath([real_path, real_workspace])
        if common_real != real_workspace:
            return False, absolute, f"Path resolves via symlink to outside workspace"
    except (OSError, ValueError):
        # If we can't resolve, be conservative
        pass
    
    return True, absolute, ""


def _extract_potential_paths(cmd_list: list[str]) -> list[str]:
    """
    Extract potential file paths from command arguments.
    Handles quoted strings in Python -c commands and regular path-like arguments.
    """
    potential_paths = []
    
    for i, arg in enumerate(cmd_list):
        if not isinstance(arg, str) or not arg:
            continue
            
        # Special handling for Python -c commands
        if i > 0 and cmd_list[i-1] == '-c' and 'python' in cmd_list[0].lower():
            # Extract string literals from the Python code
            # Look for quoted strings that contain path-like content
            string_literals = re.findall(r"[\\\"\\']([^\\\"\\']*(?:[/\\\\\\\\][^\\\"\\']*)*)[\\\"\\']", arg)
            for lit in string_literals:
                if ('/' in lit or '\\' in lit or 
                    (len(lit) >= 2 and lit[1] == ':') or
                    lit.startswith('~') or
                    lit.startswith('%') or
                    lit.startswith('..') or
                    lit.startswith('./') or
                    lit.startswith('.\\')):
                    potential_paths.append(lit)
        else:
            # Regular argument - check if it looks like a path
            if ('/' in arg or '\\' in arg or 
                (len(arg) >= 2 and arg[1] == ':') or
                arg.startswith('~') or
                arg.startswith('%') or
                arg.startswith('..') or
                arg.startswith('./') or
                arg.startswith('.\\')):
                potential_paths.append(arg)
    
    return potential_paths


class RunCommandTool(Tool):
    @property
    def name(self) -> str:
        return "terminal.run"

    def prepare(self, action: Action) -> Any:
        # No preparation needed
        return None

    def execute(self, action: Action, context: Any) -> Observation:
            args = action.arguments
            cmd = args.get("cmd")
            timeout = args.get("timeout", 30)  # seconds
            if cmd is None:
                return Observation.create_error("Missing 'cmd' argument for terminal.run")

            # Normalize cmd to list of strings for subprocess
            if isinstance(cmd, str):
                # Split by whitespace? We'll keep simple: treat as shell command?
                # For safety, we should not use shell=True unless necessary.
                # We'll assume cmd is a list of arguments; if string, we split.
                # However, to support complex commands, we could allow shell=True via an argument.
                # We'll keep simple: if string, we split by whitespace (not robust but okay for allowed commands).
                # Better: we require cmd to be a list in the action arguments.
                # We'll check: if it's a string, we split.
                cmd_list = cmd.split()
            elif isinstance(cmd, list):
                cmd_list = [str(c) for c in cmd]
            else:
                return Observation.create_error("'cmd' must be a string or list of strings")

            # SECURITY: Validate all potential file paths in command against workspace boundary
            if action.sandbox.fs_root:
                fs_root = action.sandbox.fs_root
                potential_paths = _extract_potential_paths(cmd_list)
                for path in potential_paths:
                    is_valid, normalized, error = _normalize_and_validate_path(path, fs_root)
                    if not is_valid:
                        return Observation.create_error(
                            f"Terminal path validation failed: {error}",
                            metadata={
                                "cmd": cmd_list,
                                "unsafe_path": path,
                                "normalized_path": normalized,
                            }
                        )

            # Determine working directory: use sandbox.fs_root if set, else current working directory
            cwd = None
            if action.sandbox.fs_root:
                fs_root = action.sandbox.fs_root
                if os.path.isdir(fs_root):
                    cwd = fs_root
                else:
                    return Observation.create_error(f"Sandbox fs_root '{fs_root}' is not a directory")

            # Prepare environment: we can pass a minimal environment, but for simplicity we inherit.
            # We could also restrict environment variables, but we skip for now.
            env = os.environ.copy()

            start_time = time.time()
            try:
                completed = subprocess.run(
                    cmd_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                    cwd=cwd,
                    env=env,
                    # We do not use shell=True to avoid injection risks.
                )
            except subprocess.TimeoutExpired:
                # Timeout
                end_time = time.time()
                return Observation.create_timeout(
                    metadata={
                        "timeout": timeout,
                        "duration": end_time - start_time,
                        "cmd": cmd_list,
                        "cwd": cwd,
                    }
                )
            except FileNotFoundError:
                # Command not found
                end_time = time.time()
                return Observation.create_error(
                    f"Command not found: '{cmd_list[0]}'",
                    metadata={
                        "cmd": cmd_list,
                        "duration": end_time - start_time,
                    }
                )
            except Exception as e:
                end_time = time.time()
                return Observation.create_error(
                    f"Error executing command: {e}",
                    metadata={
                        "cmd": cmd_list,
                        "duration": end_time - start_time,
                    }
                )

            end_time = time.time()
            duration = end_time - start_time
            stdout = completed.stdout.decode('utf-8', errors='replace')
            stderr = completed.stderr.decode('utf-8', errors='replace')
            exit_code = completed.returncode

            # Determine observation status: if we got here, the tool succeeded in running the command.
            status = ToolStatus.SUCCESS
            # However, we might want to differentiate non-zero exit as a kind of failure?
            # We'll keep SUCCESS and let the evaluator decide based on exit_code.
            return Observation.create_success(
                payload={
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                },
                metadata={
                    "cmd": cmd_list,
                    "duration": duration,
                    "cwd": cwd,
                },
                side_effects={}  # side effects are not known; the verifier can check filesystem changes if needed.
            )

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Validate the arguments for this tool."""
        cmd = arguments.get("cmd")
        if cmd is None:
            return False, "Missing 'cmd' argument"
        if isinstance(cmd, str):
            pass
        elif isinstance(cmd, list):
            for i, item in enumerate(cmd):
                if not isinstance(item, str):
                    return False, f"cmd[{i}] must be a string"
        else:
            return False, "'cmd' must be a string or list of strings"
        timeout = arguments.get("timeout")
        if timeout is not None:
            if not isinstance(timeout, (int, float)):
                return False, "'timeout' must be a number"
            if timeout <= 0:
                return False, "'timeout' must be positive"
        return True, ""
    def cleanup(self, action: Action, context: Any) -> None:
        pass
