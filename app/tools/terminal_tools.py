import os
import subprocess
import time
from typing import Any

from app.core.state.action import Action
from app.core.state.observation import Observation, ToolStatus
from app.tools.base_tool_pc import Tool


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
            return Observation.error("Missing 'cmd' argument for terminal.run")

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
            return Observation.error("'cmd' must be a string or list of strings")

        # Determine working directory: use sandbox.fs_root if set, else current working directory
        cwd = None
        if action.sandbox.fs_root:
            fs_root = action.sandbox.fs_root
            if os.path.isdir(fs_root):
                cwd = fs_root
            else:
                return Observation.error(f"Sandbox fs_root '{fs_root}' is not a directory")

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
            return Observation(
                status=ToolStatus.TIMEOUT,
                payload={},
                metadata={
                    "timeout": timeout,
                    "duration": end_time - start_time,
                    "cmd": cmd_list,
                    "cwd": cwd,
                },
                side_effects={},
                raw="",  # we could capture partial output? subprocess doesn't provide on timeout easily.
            )
        except FileNotFoundError:
            # Command not found
            end_time = time.time()
            return Observation.error(
                f"Command not found: '{cmd_list[0]}'",
                metadata={
                    "cmd": cmd_list,
                    "duration": end_time - start_time,
                }
            )
        except Exception as e:
            end_time = time.time()
            return Observation.error(
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
        return Observation.success(
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