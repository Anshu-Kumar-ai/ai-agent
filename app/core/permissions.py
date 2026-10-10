from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

import yaml


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
    """Represents a granted permission (argument-hash based)."""
    tool_name: str
    args_hash: str
    scope: str
    granted_at: float
    expires_at: float | None = None  # None means permanent
    one_time: bool = False  # If True, permission is consumed after use
    session_only: bool = False  # If True, permission expires at end of session (handled externally)


@dataclass
class _ScopePermission:
    """A granted permission that covers a whole scope (e.g. a directory prefix)."""
    tool_name: str
    action_type: str               # e.g. "read", "write", "delete", "execute"
    scope_prefix: str              # absolute path prefix that is allowed
    pattern: str | None = None     # glob/regex pattern for finer control
    pattern_type: str = "prefix"   # "prefix", "glob", "regex"
    granted_at: float = field(default_factory=time.time)
    expires_at: float | None = None   # None means permanent (or use TTL)
    ttl_seconds: float | None = None  # Time-to-live in seconds
    one_time: bool = False
    used: bool = False             # only relevant for one_time
    metadata: dict[str, Any] = field(default_factory=dict)  # extensible metadata

    def is_expired(self, now: float | None = None) -> bool:
        """Check if this permission has expired."""
        if self.ttl_seconds is not None:
            if time.time() - self.granted_at > self.ttl_seconds:
                return True
        if self.expires_at is not None:
            if now is None:
                now = time.time()
            if now > self.expires_at:
                return True
        return False

    def matches_path(self, path: str) -> bool:
        """Check if the given path matches this permission's scope/pattern."""
        # Normalize paths for comparison (handle both / and \ separators, and drive letters)
        def normalize(p: str) -> str:
            # Convert backslashes to forward slashes
            p = p.replace("\\", "/")
            # Remove drive letter prefix (e.g., "C:/project" -> "/project")
            if len(p) >= 3 and p[1] == ":" and p[2] == "/":
                p = p[2:]
            return p

        normalized_path = normalize(path)
        normalized_prefix = normalize(self.scope_prefix)

        if self.pattern_type == "prefix":
            return normalized_path.startswith(normalized_prefix)
        elif self.pattern_type == "glob":
            return fnmatch.fnmatch(normalized_path, normalize(self.pattern or self.scope_prefix))
        elif self.pattern_type == "regex":
            if self.pattern:
                return re.search(self.pattern, normalized_path) is not None
            return normalized_path.startswith(normalized_prefix)
        return normalized_path.startswith(normalized_prefix)


def _hash_args(args: dict[str, Any] | None) -> str:
    """Create a stable hash of the arguments dict."""
    if args is None:
        args = {}
    sorted_items = sorted(args.items())
    json_str = json.dumps(sorted_items, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


class PermissionManager:
    """Manages tool execution permissions with risk classification and scoped grants."""

    def __init__(
        self,
        workspace_root: str | None = None,
        approval_mode: ApprovalMode = ApprovalMode.BALANCED,
        audit_log_path: str | None = None,
        policy_path: str | None = None,
    ):
        # Resolve workspace_root to absolute path for cross-platform compatibility
        if workspace_root is None:
            workspace_root = os.getcwd()
        else:
            workspace_root = os.path.abspath(os.path.expanduser(workspace_root))

        self.workspace_root = workspace_root
        self._workspace_root_path = Path(self.workspace_root).resolve()
        self.approval_mode = approval_mode
        self.audit_log_path = audit_log_path
        self.policy_path = policy_path

        # Hash-based permissions (argument-specific)
        self._session_permissions: set[tuple[str, str]] = set()
        self._one_time_permissions: set[tuple[str, str]] = set()
        self._permanent_permissions: set[tuple[str, str]] = set()

        # Scope-based permissions
        self._scoped_session: list[_ScopePermission] = []
        self._scoped_one_time: list[_ScopePermission] = []
        self._scoped_permanent: list[_ScopePermission] = []

        # Audit log
        self._audit_log: list[dict[str, Any]] = []

        # Load policy if provided
        if policy_path and os.path.exists(policy_path):
            self._load_policy(policy_path)

    def _load_policy(self, policy_path: str) -> None:
        """Load permission policy from YAML file."""
        with open(policy_path) as f:
            policy = yaml.safe_load(f)

        for rule in policy.get("rules", []):
            tool = rule.get("tool")
            action = rule.get("action", "allow")
            if action == "allow":
                # Add to permanent permissions
                # For simplicity, we'll store the rule for later matching
                pass

    def _save_policy(self, target: str | None = None) -> None:
        """Save current permissions as a policy file."""
        target = target or self.policy_path
        if not target:
            return
        policy = {"rules": []}
        for perm in self._scoped_permanent:
            policy["rules"].append({
                "tool": perm.tool_name,
                "action_type": perm.action_type,
                "scope_prefix": perm.scope_prefix,
                "pattern": perm.pattern,
                "pattern_type": perm.pattern_type,
                "duration": "permanent",
                "metadata": perm.metadata,
            })
        try:
            with open(target, "w") as f:
                yaml.dump(policy, f, indent=2)
        except Exception as e:
            print(f"[PermissionManager] Warning: Failed to save policy to {target}: {e}")

    # --------------------------------------------------------------------- #
    # Risk classification
    # --------------------------------------------------------------------- #
    def classify_risk(self, tool_name: str, arguments: dict[str, Any]) -> RiskLevel:
        """Determine the risk level of a tool invocation."""
        tool_name_lower = tool_name.lower()

        # Known safe tools
        if tool_name_lower in {"calculator", "time", "http.fetch", "web.search"}:
            return RiskLevel.LOW

        # Code execution tools - HIGH risk
        if tool_name_lower in {"python.exec"}:
            return RiskLevel.HIGH

        # Browser automation tools - HIGH risk
        if tool_name_lower in {"browser.navigate", "browser.click", "browser.type", "browser.screenshot", "browser.content", "browser.evaluate", "browser.close"}:
            return RiskLevel.HIGH

        # Advanced browser agent tools - HIGH risk
        if tool_name_lower in {"browser_agent.execute", "browser_session.manage", "browser.observe", "browser.action"}:
            return RiskLevel.HIGH

        # Desktop automation tools - HIGH risk
        if tool_name_lower in {"desktop.list_windows", "desktop.focus_window", "desktop.get_window_info", "desktop.click", "desktop.type", "desktop.key_press", "desktop.screenshot"}:
            return RiskLevel.HIGH

        # Multi-agent orchestration - HIGH risk
        if tool_name_lower in {"orchestrator.delegate"}:
            return RiskLevel.HIGH

        # RAG tools - MEDIUM risk
        if tool_name_lower in {"rag.query", "rag.add", "rag.stats"}:
            return RiskLevel.MEDIUM

        # Terminal - HIGH risk
        if tool_name_lower in {"terminal.run"}:
            return RiskLevel.HIGH

        # File system tools (heuristic based on name) - support both old (write_file, read_file) and new (fs.write, fs.read) names
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

    def _has_outside_path(self, arguments: dict[str, Any]) -> bool:
        """Heuristic: detect if any string argument looks like a file path outside workspace."""
        for val in arguments.values():
            if isinstance(val, str):
                # Simple heuristic: if contains a path separator and not obviously a URL
                if ("/" in val or "\\" in val) and not val.startswith("http"):
                    try:
                        abs_path = os.path.abspath(os.path.expanduser(val))
                        # Check if abs_path is within workspace_root
                        common = os.path.commonpath([abs_path, self.workspace_root])
                        if common != self.workspace_root:
                            return True
                    except ValueError:
                        # paths may be on different drives on Windows
                        # If the path starts with "/" (Unix-style absolute path) and we're on Windows,
                        # treat it as outside the workspace
                        if val.startswith("/"):
                            return True
                        # For other cross-drive cases, we can't reliably determine
                        pass
            elif isinstance(val, dict):
                if self._has_outside_path(val):
                    return True
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and self._has_outside_path({"path": item}) or isinstance(item, dict) and self._has_outside_path(item):
                        return True
        return False

    # --------------------------------------------------------------------- #
    # Permission checking
    # --------------------------------------------------------------------- #
    def check_permission(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        risk_level: RiskLevel | None = None,
    ) -> tuple[bool, str]:
        """Returns (allowed, reason). If allowed is False, the caller should request user approval."""
        if risk_level is None:
            risk_level = self.classify_risk(tool_name, arguments)

        args_hash = _hash_args(arguments)
        permission_key = (tool_name, args_hash)
        now = time.time()

        # Check if permission already granted (session, one-time, permanent) - argument-hash based
        if permission_key in self._session_permissions:
            return True, "Session permission granted"
        if permission_key in self._one_time_permissions:
            self._one_time_permissions.remove(permission_key)
            return True, "One-time permission granted"
        if permission_key in self._permanent_permissions:
            return True, "Permanent permission granted"

        # Risk-based hard boundaries: CRITICAL always requires approval
        # HIGH risk requires approval unless in FULL_AUTO mode
        if risk_level == RiskLevel.CRITICAL:
            self._log_audit(
                tool_name,
                arguments,
                risk_level,
                False,
                f"{risk_level.name}-risk action requires approval",
                scope=self._describe_scope(arguments),
            )
            return False, f"{risk_level.name}-risk action requires approval"

        if risk_level == RiskLevel.HIGH:
            if self.approval_mode != ApprovalMode.FULL_AUTO:
                self._log_audit(
                    tool_name,
                    arguments,
                    risk_level,
                    False,
                    f"{risk_level.name}-risk action requires approval",
                    scope=self._describe_scope(arguments),
                )
                return False, f"{risk_level.name}-risk action requires approval"

        # For LOW risk: auto-allow (and grant session hash-based permission for repeat calls)
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

        # Fall back to mode-based auto-allow / denial logic
        auto_allow = False
        reason = ""

        if self.approval_mode == ApprovalMode.SAFE:
            auto_allow = False
        elif self.approval_mode == ApprovalMode.BALANCED:
            # MEDIUM not auto-allowed in BALANCED unless we have a scoped permission (handled above)
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
        self._log_audit(
            tool_name,
            arguments,
            risk_level,
            False,
            reason,
            scope=self._describe_scope(arguments),
        )
        return False, reason

    def _check_scoped_permission(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        now: float,
    ) -> bool:
        """Return True if a matching scoped permission exists (and consume one-time if applicable)."""
        action_type = self._action_type(tool_name, arguments)
        path_strings = self._extract_path_arguments(arguments)
        if not path_strings:
            return False  # nothing to scope

        # All paths must be inside the workspace for a scoped permission to apply
        for p in path_strings:
            if not self._is_within_workspace(p):
                return False

        # Check each scoped list
        for perm_list in (
            self._scoped_session,
            self._scoped_one_time,
            self._scoped_permanent,
        ):
            for perm in perm_list:
                if perm.tool_name != tool_name or perm.action_type != action_type:
                    continue
                if perm.is_expired(now):
                    continue  # expired
                if perm.one_time and perm.used:
                    continue  # already consumed
                # Check if any of the paths match this permission
                matched = False
                for p in path_strings:
                    if perm.matches_path(p):
                        matched = True
                        break
                if not matched:
                    continue
                # Match found
                if perm.one_time:
                    perm.used = True
                return True
        return False

    def _action_type(self, tool_name: str, arguments: dict[str, Any] | None) -> str:
        """Extract action type from tool name and arguments."""
        if tool_name.startswith("fs."):
            if "write" in tool_name:
                return "write"
            elif "read" in tool_name:
                return "read"
            elif "list" in tool_name:
                return "list"
            elif "move" in tool_name:
                return "move"
            elif "delete" in tool_name:
                return "delete"
            else:
                return "unknown"
        elif tool_name.startswith("terminal."):
            return "execute"
        elif tool_name.startswith("browser."):
            return "browser"
        elif tool_name.startswith("python."):
            return "execute"
        return "unknown"

    def _extract_path_arguments(self, arguments: dict[str, Any] | None) -> list[str]:
        """Extract path-like arguments from tool arguments."""
        if arguments is None:
            return []
        paths: list[str] = []

        def _maybe_add(val: Any) -> None:
            if isinstance(val, str) and ("/" in val or "\\" in val) and not val.startswith("http"):
                paths.append(val)
            elif isinstance(val, dict):
                for v in val.values():
                    _maybe_add(v)
            elif isinstance(val, list):
                for item in val:
                    _maybe_add(item)

        # Explicit path keys
        explicit_keys = {"path", "src", "dst", "source", "destination", "file", "directory", "dir"}
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

    def _is_within_workspace(self, path: str) -> bool:
        """Check if a path is within the workspace root."""
        try:
            abs_path = os.path.abspath(os.path.expanduser(path))
            common = os.path.commonpath([abs_path, self.workspace_root])
            return common == self.workspace_root
        except ValueError:
            # Cross-drive paths on Windows
            return False

    # --------------------------------------------------------------------- #
    # Granting permissions
    # --------------------------------------------------------------------- #
    def grant_permission(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        scope: str,
        duration: str = "session",
        one_time: bool = False,
        pattern: str | None = None,
        pattern_type: str = "prefix",
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a granted permission based on user approval.
        duration: "one_time", "session", "permanent"
        pattern: glob/regex pattern for path matching
        pattern_type: "prefix", "glob", "regex"
        ttl_seconds: time-to-live in seconds (None = no TTL)
        metadata: extensible metadata dict
        """
        action_type = self._action_type(tool_name, arguments)
        path_strings = self._extract_path_arguments(arguments)
        args_hash = _hash_args(arguments)
        permission_key = (tool_name, args_hash)

        # Determine if we can create a scoped permission:
        #   - we have at least one path-like argument
        #   - all such paths are inside the configured workspace
        scoped_grant = False
        if path_strings:
            if all(self._is_within_workspace(p) for p in path_strings):
                scoped_grant = True
                scope_prefix = str(self._workspace_root_path)
            else:
                scoped_grant = False

        if scoped_grant:
            perm = _ScopePermission(
                tool_name=tool_name,
                action_type=action_type,
                scope_prefix=scope_prefix,
                pattern=pattern,
                pattern_type=pattern_type,
                one_time=one_time or duration == "one_time",
                ttl_seconds=ttl_seconds,
                metadata=metadata or {},
            )
            if duration == "permanent":
                self._scoped_permanent.append(perm)
            elif duration == "one_time" or one_time:
                self._scoped_one_time.append(perm)
            else:  # session
                self._scoped_session.append(perm)

        # Also record the hash-based permission for the specific arguments
        if duration == "permanent":
            self._permanent_permissions.add(permission_key)
            # Persist to audit log file if configured
            if self.audit_log_path:
                self._persist_permission(
                    tool_name, arguments, scope, granted_at=time.time()
                )
        elif duration == "one_time" or one_time:
            self._one_time_permissions.add(permission_key)
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
        arguments: dict[str, Any] | None,
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
    # Audit log
    # --------------------------------------------------------------------- #
    def _describe_scope(self, arguments: dict[str, Any] | None) -> str:
        """Produces a human-readable scope description from arguments."""
        if arguments is None:
            return "no file paths detected"
        for val in arguments.values():
            if isinstance(val, str) and ("/" in val or "\\" in val):
                return f"path: {val}"
        return "no file paths detected"

    def _log_audit(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        risk_level: RiskLevel,
        allowed: bool,
        reason: str,
        scope: str,
    ) -> None:
        """Record an audit entry."""
        if arguments is None:
            arguments = {}
        entry = {
            "timestamp": time.time(),
            "tool": tool_name,
            "arguments_hash": _hash_args(arguments),
            "risk": risk_level.name,
            "decision": "allowed" if allowed else "denied",
            "reason": reason,
            "scope": scope,
        }
        self._audit_log.append(entry)

        if self.audit_log_path:
            self._persist_audit(entry)

    def _persist_audit(self, entry: dict[str, Any]) -> None:
        """Append a single audit entry to the log file."""
        try:
            data = {"entries": []}
            if os.path.exists(self.audit_log_path):
                with open(self.audit_log_path) as f:
                    data = json.load(f)
            data["entries"].append(entry)
            with open(self.audit_log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # ignore logging errors

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return a copy of the audit log."""
        return list(self._audit_log)

    def clear_session_permissions(self) -> None:
        """Clear session-based permissions (hash-based and scoped)."""
        self._session_permissions.clear()
        self._scoped_session.clear()

    def get_scoped_permissions(self) -> list[dict[str, Any]]:
        """Get a summary of all scoped permissions."""
        result = []
        for perm in (
            self._scoped_session + self._scoped_one_time + self._scoped_permanent
        ):
            result.append({
                "tool_name": perm.tool_name,
                "action_type": perm.action_type,
                "scope_prefix": perm.scope_prefix,
                "pattern": perm.pattern,
                "pattern_type": perm.pattern_type,
                "one_time": perm.one_time,
                "ttl_seconds": perm.ttl_seconds,
                "used": perm.used,
                "metadata": perm.metadata,
            })
        return result

    def safe_execute(self, executor, tool_name: str, **kwargs) -> Any:
        """Execute a tool after checking permissions.

        Args:
            executor: A ToolExecutor instance
            tool_name: Name of the tool to execute
            **kwargs: Arguments for the tool

        Returns:
            Tool result if allowed

        Raises:
            PermissionError: If permission is denied
        """
        allowed, reason = self.check_permission(tool_name, kwargs)
        if not allowed:
            raise PermissionError(f"Permission denied for {tool_name}: {reason}")
        return executor.execute(tool_name, **kwargs)

    def _persist_permission(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        scope: str,
        granted_at: float,
    ) -> None:
        """Persist a permanent permission grant."""
        if not self.audit_log_path:
            return
        try:
            data = {"permissions": []}
            if os.path.exists(self.audit_log_path):
                with open(self.audit_log_path) as f:
                    data = json.load(f)
            data["permissions"].append({
                "tool_name": tool_name,
                "arguments": arguments,
                "scope": scope,
                "granted_at": granted_at,
            })
            with open(self.audit_log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def safe_execute(permission_manager, executor, tool_name: str, **kwargs) -> Any:
    """Standalone function for executing a tool with permission checking.

    This is a convenience wrapper around PermissionManager.safe_execute().

    Args:
        permission_manager: A PermissionManager instance
        executor: A ToolExecutor instance
        tool_name: Name of the tool to execute
        **kwargs: Arguments for the tool

    Returns:
        Tool result if allowed

    Raises:
        PermissionError: If permission is denied
    """
    return permission_manager.safe_execute(executor, tool_name, **kwargs)
