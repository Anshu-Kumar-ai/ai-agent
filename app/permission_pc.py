from abc import ABC, abstractmethod
from typing import Any, List, Optional
from ..core.state.action import Action, SandboxSpec
import os
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class PermissionLayer(ABC):
    """Interface for checking permissions before tool execution."""
    @abstractmethod
    def authorize(self, action: Action, sandbox: SandboxSpec) -> bool:
        """Return True if action is allowed, False otherwise."""
        pass

    @abstractmethod
    def log_decision(self, action: Action, allowed: bool, reason: str = "") -> None:
        """Optional logging of the decision."""
        pass


class FilesystemAndTerminalPermissionLayer(PermissionLayer):
    """
    A permission layer that:
    - Denies all actions by default (default-deny).
    - Allows filesystem actions only within explicitly allowed roots.
    - Allows terminal actions only for explicitly allowed commands.
    - Provides useful denial reasons.
    - Logs all decisions.
    """

    def __init__(
        self,
        allowed_roots: Optional[List[str]] = None,
        allowed_commands: Optional[List[str]] = None,
    ):
        """
        Args:
            allowed_roots: List of absolute paths that are allowed for filesystem access.
                If None or empty, no filesystem actions are allowed.
            allowed_commands: List of allowed command strings (the command to execute, e.g., "ls", "cat").
                If None or empty, no terminal actions are allowed.
        """
        self.allowed_roots = [os.path.abspath(r) for r in (allowed_roots or [])]
        self.allowed_commands = set(allowed_commands or [])
        # Ensure logger has a handler if not configured
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

    def authorize(self, action: Action, sandbox: SandboxSpec) -> bool:
        tool_name = action.tool_name
        args = action.arguments

        if tool_name.startswith("fs."):
            return self._authorize_filesystem(action, sandbox)
        elif tool_name == "terminal.run":
            return self._authorize_terminal(action, sandbox)
        else:
            # Unknown tool: deny by default
            self.log_decision(action, False, f"Unknown tool '{tool_name}'")
            return False

    def _authorize_filesystem(self, action: Action, sandbox: SandboxSpec) -> bool:
        # Determine which paths are involved based on the tool
        args = action.arguments
        paths_to_check = []
        if action.tool_name == "fs.read":
            path = args.get("path")
            if path is None:
                self.log_decision(action, False, "Missing 'path' argument for fs.read")
                return False
            paths_to_check.append(path)
        elif action.tool_name == "fs.write":
            path = args.get("path")
            if path is None:
                self.log_decision(action, False, "Missing 'path' argument for fs.write")
                return False
            paths_to_check.append(path)
        elif action.tool_name == "fs.move":
            src = args.get("src")
            dst = args.get("dst")
            if src is None:
                self.log_decision(action, False, "Missing 'src' argument for fs.move")
                return False
            if dst is None:
                self.log_decision(action, False, "Missing 'dst' argument for fs.move")
                return False
            paths_to_check.extend([src, dst])
        elif action.tool_name == "fs.list":
            path = args.get("path")
            if path is None:
                self.log_decision(action, False, "Missing 'path' argument for fs.list")
                return False
            paths_to_check.append(path)
        else:
            self.log_decision(action, False, f"Unsupported filesystem tool '{action.tool_name}'")
            return False

        # Check each path
        for path in paths_to_check:
            if not self._is_path_allowed(path, sandbox):
                self.log_decision(
                    action,
                    False,
                    f"Path '{path}' is not within allowed roots: {self.allowed_roots}",
                )
                return False

        # If all checks pass, we can optionally restrict the sandbox further
        # For simplicity, we leave the sandbox as is; the tool itself should still validate.
        self.log_decision(action, True, "Filesystem action allowed")
        return True

    def _authorize_terminal(self, action: Action, sandbox: SandboxSpec) -> bool:
        args = action.arguments
        cmd = args.get("cmd")
        if cmd is None:
            self.log_decision(action, False, "Missing 'cmd' argument for terminal.run")
            return False
        # Normalize cmd to a string (first element if list)
        if isinstance(cmd, list):
            if not cmd:
                self.log_decision(action, False, "Empty command list")
                return False
            cmd_str = cmd[0]
        else:
            cmd_str = str(cmd)

        if cmd_str not in self.allowed_commands:
            self.log_decision(
                action,
                False,
                f"Command '{cmd_str}' is not in allowed commands: {sorted(self.allowed_commands)}",
            )
            return False

        self.log_decision(action, True, f"Terminal command '{cmd_str}' allowed")
        return True

    def _is_path_allowed(self, path: str, sandbox: SandboxSpec) -> bool:
        """
        Return True if the given path (after resolving relative to sandbox.fs_root if any)
        is within one of the allowed roots.
        """
        # Convert to absolute path, considering sandbox.fs_root as the base if path is relative
        if not os.path.isabs(path):
            if sandbox.fs_root:
                base = sandbox.fs_root
            else:
                # If no sandbox root, treat as relative to current working directory?
                # For safety, we deny if no sandbox root and path is relative.
                # But we can also treat as relative to the process cwd.
                # We'll allow but then check against allowed roots.
                base = os.getcwd()
            abs_path = os.path.abspath(os.path.join(base, path))
        else:
            abs_path = os.path.abspath(path)

        # Normalize path (resolve symlinks and '..' components)
        try:
            abs_path = os.path.realpath(abs_path)
        except Exception:
            # If realpath fails (e.g., path does not exist), we still use the absolute path
            # for checking against allowed roots (to avoid TOCTOU issues, we still deny if not under allowed root)
            pass

        # Check if the absolute path is within any allowed root
        for root in self.allowed_roots:
            # Ensure root ends with separator for proper prefix check
            if not root.endswith(os.sep):
                root += os.sep
            if abs_path.startswith(root):
                return True
        return False

    def log_decision(self, action: Action, allowed: bool, reason: str = "") -> None:
        if allowed:
            logger.info(f"Permission ALLOWED: action={action.action_id} tool={action.tool_name} reason={reason}")
        else:
            logger.warning(f"Permission DENIED: action={action.action_id} tool={action.tool_name} reason={reason}")
