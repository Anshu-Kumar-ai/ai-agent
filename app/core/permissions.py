from __future__ import annotations

import os
import time
import json
import hashlib
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from app.tools.executor import ToolExecutor
from app.tools.base import BaseTool


class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


class ApprovalMode(Enum):
    SAFE = auto()
    BALANCED = auto()
    AUTONOMOUS = auto()
    FULL_AUTO = auto()


@dataclass(frozen=True)
class Permission:
    """Represents a granted permission (argument‑hash based)."""
    tool_name: str
    args_hash: str
    scope: str
    granted_at: float
    expires_at: Optional[float] = None  # None means permanent
    one_time: bool = False  # If True, permission is consumed after use
    session_only: bool = False  # If True, permission expires at end of session (handled externally)


@dataclass
class _ScopePermission:
    """A granted permission that covers a whole scope (e.g. a directory prefix)."""
    tool_name: str
    action_type: str               # e.g. "read", "write", "delete", "execute"
    scope_prefix: str              # absolute path prefix that is allowed
    granted_at: float
    expires_at: Optional[float] = None   # None means permanent
    one_time: bool = False
    used: bool = False             # only relevant for one_time


def _hash_args(args: Dict[str, Any]) -> str:
    """Create a stable hash of the arguments dict."""
    # Sort keys for consistent ordering
    sorted_items = sorted(args.items())
    # Convert to JSON string for deterministic representation
    json_str = json.dumps(sorted_items, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


class PermissionManager:
    """
    Centralized risk-based permission system.

    Responsibilities:
    - Classify tool actions by risk level.
    - Check if action is already permitted.
    - Automatically allow low-risk operations.
    - Request user approval for high-risk operations.
    - Support temporary/session-scoped permissions.
    - Provide an audit log of permission decisions.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        approval_mode: ApprovalMode = ApprovalMode.BALANCED,
        audit_log_path: Optional[str] = None,
    ):
        self.workspace_root = os.path.abspath(
            workspace_root or os.getenv("HERMES_WORKSPACE", os.getcwd())
        )
        self._workspace_root_path = Path(self.workspace_root).resolve()
        self.approval_mode = approval_mode
        self.audit_log_path = audit_log_path

        # In-memory stores
        self._session_permissions: Set[Tuple[str, str]] = set()          # (tool_name, args_hash)
        self._one_time_permissions: Set[Tuple[str, str]] = set()
        self._permanent_permissions: Set[Tuple[str, str]] = set()        # loaded from disk if needed

        # NEW – scoped permissions
        self._scoped_session: List[_ScopePermission] = []
        self._scoped_one_time: List[_ScopePermission] = []
        self._scoped_permanent: List[_ScopePermission] = []

        # Audit log as list of dicts
        self._audit_log: List[Dict[str, Any]] = []

        # Load permanent permissions if audit log path is provided and file exists
        if self.audit_log_path and os.path.exists(self.audit_log_path):
            try:
                with open(self.audit_log_path, "r") as f:
                    data = json.load(f)
                for entry in data.get("permissions", []):
                    self._permanent_permissions.add(
                        (entry["tool_name"], entry["args_hash"])
                    )
            except Exception:
                pass  # ignore errors

    # --------------------------------------------------------------------- #
    # Risk classification
    # --------------------------------------------------------------------- #
    def classify_risk(self, tool_name: str, arguments: Dict[str, Any]) -> RiskLevel:
        """Determine the risk level of a tool invocation."""
        tool_name_lower = tool_name.lower()

        # Known safe tools
        if tool_name_lower in {"calculator", "time", "http.fetch", "web.search", "terminal.run"}:
            return RiskLevel.LOW

        # File system tools (heuristic based on name)
        if any(
            kw in tool_name_lower
            for kw in ("read", "list", "stat", "info", "grep", "find")
        ):
            return RiskLevel.LOW

        if any(
            kw in tool_name_lower
            for kw in ("write", "create", "update", "modify", "edit", "save")
        ):
            # Check if any argument looks like a path outside workspace
            if self._has_outside_path(arguments):
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if any(
            kw in tool_name_lower
            for kw in ("delete", "remove", "rm", "unlink", "truncate")
        ):
            return RiskLevel.HIGH

        if any(
            kw in tool_name_lower
            for kw in ("move", "rename", "cp", "copy")
        ):
            return RiskLevel.MEDIUM  # could be HIGH if overwriting important files

        if any(
            kw in tool_name_lower
            for kw in ("exec", "run", "shell", "terminal", "command")
        ):
            return RiskLevel.HIGH

        # Default to MEDIUM for unknown tools
        return RiskLevel.MEDIUM

    def _has_outside_path(self, arguments: Dict[str, Any]) -> bool:
        """Heuristic: detect if any string argument looks like a file path outside workspace."""
        for val in arguments.values():
            if isinstance(val, str):
                # Simple heuristic: if contains a path separator and not obviously a URL
                if ("/" in val or "\\" in val) and not val.startswith("http"):
                    abs_path = os.path.abspath(os.path.expanduser(val))
                    try:
                        # Check if abs_path is within workspace_root
                        common = os.path.commonpath([abs_path, self.workspace_root])
                        if common != self.workspace_root:
                            return True
                    except ValueError:
                        # paths may be on different drives on Windows, treat as outside
                        return True
            elif isinstance(val, dict):
                if self._has_outside_path(val):
                    return True
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and self._has_outside_path({"path": item}):
                        return True
                    elif isinstance(item, dict) and self._has_outside_path(item):
                        return True
        return False

    # --------------------------------------------------------------------- #
    # Permission checking
    # --------------------------------------------------------------------- #
    def check_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: Optional[RiskLevel] = None,
    ) -> Tuple[bool, str]:
        """Returns (allowed, reason). If allowed is False, the caller should request user approval."""
        if risk_level is None:
            risk_level = self.classify_risk(tool_name, arguments)

        args_hash = _hash_args(arguments)
        permission_key = (tool_name, args_hash)
        now = time.time()

        # Check if permission already granted (session, one-time, permanent) – argument‑hash based
        if permission_key in self._session_permissions:
            return True, "Session permission granted"
        if permission_key in self._one_time_permissions:
            self._one_time_permissions.remove(permission_key)
            return True, "One-time permission granted"
        if permission_key in self._permanent_permissions:
            return True, "Permanent permission granted"

        # Risk‑based hard boundaries: HIGH and CRITICAL always require approval
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return False, f"{risk_level.name}-risk action requires approval"

        # For LOW risk: auto‑allow (and grant session hash‑based permission for repeat calls)
        if risk_level == RiskLevel.LOW:
            auto_allow = True
            reason = "Low-risk auto-allowed"
            self._session_permissions.add(permission_key)
            self._log_audit(
                tool_name,
                arguments,
                risk_level,
                True,
                reason,
                scope=self._describe_scope(arguments),
            )
            return True, reason

        # For MEDIUM risk: first try scoped permissions
        if risk_level == RiskLevel.MEDIUM:
            if self._check_scoped_permission(tool_name, arguments, now):
                # Scoped permission granted
                self._log_audit(
                    tool_name,
                    arguments,
                    risk_level,
                    True,
                    "Scoped permission granted",
                    scope="within workspace",
                )
                return True, "Scoped permission granted"

        # Fall back to mode‑based auto‑allow / denial logic
        auto_allow = False
        reason = ""

        if self.approval_mode == ApprovalMode.SAFE:
            auto_allow = False
        elif self.approval_mode == ApprovalMode.BALANCED:
            # MEDIUM not auto‑allowed in BALANCED unless we have a scoped permission (handled above)
            auto_allow = False
        elif self.approval_mode == ApprovalMode.AUTONOMOUS:
            if risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):
                auto_allow = True
                reason = f"{risk_level.name}-risk auto-allowed (AUTONOMOUS mode)"
            else:
                auto_allow = False
        elif self.approval_mode == ApprovalMode.FULL_AUTO:
            if risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH):
                auto_allow = True
                reason = f"{risk_level.name}-risk auto-allowed (FULL_AUTO mode)"
            else:
                auto_allow = False

        if auto_allow:
            # Grant temporary session permission for LOW/MEDIUM? We'll grant session permission for simplicity.
            self._session_permissions.add(permission_key)
            self._log_audit(
                tool_name,
                arguments,
                risk_level,
                True,
                reason,
                scope=self._describe_scope(arguments),
            )
            return True, reason

        # Otherwise, we need to ask for approval
        reason = f"{risk_level.name}-risk action requires approval"
        return False, reason

    def _check_scoped_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        now: float,
    ) -> bool:
        """Return True if a matching scoped permission exists (and consume one‑time if applicable)."""
        action_type = self._action_type(tool_name, arguments)
        path_strings = self._extract_path_arguments(arguments)
        if not path_strings:
            return False  # nothing to scope

        # All paths must be inside the workspace for a scoped permission to apply
        for p in path_strings:
            if not self._is_within_workspace(p):
                return False

        # Normalize workspace prefix for comparison
        ws_prefix = str(self._workspace_root_path)

        # Check each scoped list
        for perm_list in (
            self._scoped_session,
            self._scoped_one_time,
            self._scoped_permanent,
        ):
            for perm in perm_list:
                if perm.tool_name != tool_name or perm.action_type != action_type:
                    continue
                if perm.scope_prefix != ws_prefix:
                    continue
                if perm.expires_at is not None and perm.expires_at < now:
                    continue  # expired
                if perm.one_time and perm.used:
                    continue  # already consumed
                # Match found
                if perm.one_time:
                    perm.used = True
                return True
        return False

    def _action_type(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Return a coarse‑grained action string used for scoping."""
        tn = tool_name.lower()

        # File‑system verbs (heuristic – matches the existing risk classification)
        if any(k in tn for k in ("read", "list", "stat", "info", "grep", "find")):
            return "read"
        if any(k in tn for k in ("write", "create", "update", "modify", "edit", "save")):
            return "write"
        if any(k in tn for k in ("delete", "remove", "rm", "unlink", "truncate")):
            return "delete"
        if any(k in tn for k in ("move", "rename", "cp", "copy")):
            return "move"
        if any(k in tn for k in ("exec", "run", "shell", "terminal", "command")):
            return "execute"

        # Default – treat the whole tool as its own action
        return tn

    def _is_within_workspace(self, path_str: str) -> bool:
        """Return True if the given path is inside the configured workspace."""
        try:
            p = Path(path_str).expanduser().resolve()
            return p.is_relative_to(self._workspace_root_path)
        except (ValueError, RuntimeError):
            # If the path cannot be resolved (e.g., invalid characters), treat as outside
            return False

    def _extract_path_arguments(self, arguments: Dict[str, Any]) -> List[str]:
        """Extract arguments that are explicitly file‑system paths.
        Prefers known keys (path, file_path, filename, directory, etc.) and falls back to heuristic.
        """
        paths: List[str] = []

        def _maybe_add(val: Any):
            if isinstance(val, str):
                # Heuristic: looks like a path if contains a separator and not a URL
                if ("/" in val or "\\" in val) and not val.startswith("http"):
                    paths.append(val)
            elif isinstance(val, dict):
                for v in val.values():
                    _maybe_add(v)
            elif isinstance(val, list):
                for v in val:
                    _maybe_add(v)

        # First, try known explicit keys
        explicit_keys = {
            "path",
            "file_path",
            "filename",
            "file",
            "directory",
            "dir",
            "target",
            "source",
            "destination",
            "new_path",
            "old_path",
        }
        for key, val in arguments.items():
            if key.lower() in explicit_keys:
                _maybe_add(val)

        # If we found any explicit paths, return them (heuristic fallback only if none found)
        if paths:
            return paths

        # Fallback: scan all values heuristically
        for val in arguments.values():
            _maybe_add(val)
        return paths

    # --------------------------------------------------------------------- #
    # Granting permissions
    # --------------------------------------------------------------------- #
    def grant_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        scope: str,
        duration: str = "session",
        one_time: bool = False,
    ) -> None:
        """Record a granted permission based on user approval.
        duration: "one_time", "session", "permanent"
        """
        action_type = self._action_type(tool_name, arguments)
        path_strings = self._extract_path_arguments(arguments)
        args_hash = _hash_args(arguments)
        permission_key = (tool_name, args_hash)

        # Determine if we can create a scoped permission:
        #   - we have at least one path‑like argument
        #   - all such paths are inside the configured workspace
        scoped_grant = False
        if path_strings:
            if all(self._is_within_workspace(p) for p in path_strings):
                scoped_grant = True
                scope_prefix = str(self._workspace_root_path)
            else:
                scoped_grant = False
        else:
            scoped_grant = False

        if scoped_grant:
            # Choose the appropriate list based on duration/one_time
            if one_time or duration == "one_time":
                self._scoped_one_time.append(
                    _ScopePermission(
                        tool_name=tool_name,
                        action_type=action_type,
                        scope_prefix=scope_prefix,
                        granted_at=time.time(),
                        expires_at=None,
                        one_time=True,
                        used=False,
                    )
                )
            elif duration == "permanent":
                self._scoped_permanent.append(
                    _ScopePermission(
                        tool_name=tool_name,
                        action_type=action_type,
                        scope_prefix=scope_prefix,
                        granted_at=time.time(),
                        expires_at=None,
                        one_time=False,
                        used=False,
                    )
                )
            else:  # session (default)
                self._scoped_session.append(
                    _ScopePermission(
                        tool_name=tool_name,
                        action_type=action_type,
                        scope_prefix=scope_prefix,
                        granted_at=time.time(),
                        expires_at=None,
                        one_time=False,
                        used=False,
                    )
                )
        else:
            # No recognizable path → fall back to the original hash‑based storage
            if one_time or duration == "one_time":
                self._one_time_permissions.add(permission_key)
            elif duration == "permanent":
                self._permanent_permissions.add(permission_key)
                # Persist to audit log file if configured
                if self.audit_log_path:
                    self._persist_permission(
                        tool_name, arguments, scope, granted_at=time.time()
                    )
            else:  # session
                self._session_permissions.add(permission_key)

        # Audit log (always)
        self._log_audit(
            tool_name,
            arguments,
            self.classify_risk(tool_name, arguments),
            True,
            f"Permission granted ({duration})",
            scope=scope,
        )

    def deny_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: str = "",
    ) -> None:
        self._log_audit(
            tool_name,
            arguments,
            self.classify_risk(tool_name, arguments),
            False,
            reason or "Permission denied",
            scope=self._describe_scope(arguments),
        )

    # --------------------------------------------------------------------- #
    # Audit logging
    # --------------------------------------------------------------------- #
    def _log_audit(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        decision: bool,
        reason: str,
        scope: str = "",
    ) -> None:
        entry = {
            "timestamp": time.time(),
            "tool": tool_name,
            "args_hash": _hash_args(arguments),
            "arguments": self._sanitize_args(arguments),
            "risk": risk_level.name,
            "decision": "allowed" if decision else "denied",
            "reason": reason,
            "scope": scope,
        }
        self._audit_log.append(entry)
        # If audit log path is set, write to file (append)
        if self.audit_log_path:
            try:
                with open(self.audit_log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass  # ignore logging errors

    def _persist_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        scope: str,
        granted_at: float,
    ) -> None:
        """Append a permanent permission entry to the audit log file."""
        if not self.audit_log_path:
            return
        entry = {
            "timestamp": granted_at,
            "tool": tool_name,
            "args_hash": _hash_args(arguments),
            "arguments": self._sanitize_args(arguments),
            "scope": scope,
        }
        try:
            # Read existing data, update, write back
            data = {"permissions": []}
            if os.path.exists(self.audit_log_path):
                with open(self.audit_log_path, "r") as f:
                    data = json.load(f)
            data["permissions"].append(entry)
            with open(self.audit_log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _sanitize_args(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Remove potentially sensitive values from arguments before logging."""
        sanitized = {}
        for key, val in arguments.items():
            if isinstance(val, str):
                # Simple redaction for common secret patterns
                lower_key = key.lower()
                if any(
                    secret in lower_key
                    for secret in ("key", "token", "secret", "password", "passwd", "auth")
                ):
                    sanitized[key] = "***REDACTED***"
                else:
                    sanitized[key] = val
            elif isinstance(val, dict):
                sanitized[key] = self._sanitize_args(val)
            elif isinstance(val, list):
                sanitized[key] = [
                    self._sanitize_args(i) if isinstance(i, dict) else i for i in val
                ]
            else:
                sanitized[key] = val
        return sanitized

    def _describe_scope(self, arguments: Dict[str, Any]) -> str:
        """Produces a human‑readable scope description from arguments."""
        # For simplicity, we just note if any paths are within workspace.
        paths = []
        for val in self._flatten_strings(arguments):
            if isinstance(val, str) and ("/" in val or "\\" in val):
                paths.append(val)
        if paths:
            # Check if first path is within workspace
            sample = paths[0]
            abs_path = os.path.abspath(os.path.expanduser(sample))
            if abs_path.startswith(self.workspace_root):
                return f"within workspace ({self.workspace_root})"
            else:
                return f"outside workspace ({abs_path})"
        return "no file paths detected"

    def _flatten_strings(self, obj: Any) -> List[str]:
        """Recursively extract all strings from a nested structure."""
        strings: List[str] = []

        def _extract(item: Any):
            if isinstance(item, str):
                strings.append(item)
            elif isinstance(item, dict):
                for v in item.values():
                    _extract(v)
            elif isinstance(item, list):
                for v in item:
                    _extract(v)

        _extract(obj)
        return strings

    # --------------------------------------------------------------------- #
    # Utility for clearing session permissions (called at session end)
    # --------------------------------------------------------------------- #
    def clear_session(self) -> None:
        """Clear session‑specific permissions (call at end of session)."""
        self._session_permissions.clear()
        self._scoped_session.clear()
        # One‑time permissions are consumed on use; permanent remain.

    # --------------------------------------------------------------------- #
    # Helper function to integrate with ToolExecutor
    # --------------------------------------------------------------------- #


def safe_execute(
    executor: ToolExecutor,
    permission_manager: PermissionManager,
    tool_name: str,
    **kwargs: Any,
) -> Any:
    """Execute a tool after checking permissions.
    Raises PermissionError if not allowed and user denies.
    """
    risk = permission_manager.classify_risk(tool_name, kwargs)
    allowed, reason = permission_manager.check_permission(tool_name, kwargs, risk)
    if not allowed:
        raise PermissionError(
            f"Permission required for {tool_name} ({risk.name}): {reason}. "
            f"Arguments: {kwargs}"
        )
    return executor.execute(tool_name, **kwargs)