"""
Git Application Adapter - Stage 32 Phase 6
Git is primarily a command-line/application adapter.

Do NOT bypass the existing terminal security pipeline.
Expose a focused capability set with read-focused operations first.

Capabilities:
- git.status
- git.log
- git.diff
- git.branch_list
- git.branch_create
- git.add
- git.commit
- git.checkout
"""

import os
import subprocess
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    BaseApplicationAdapter,
    AdapterMetadata,
    AdapterState,
)
from app.tools.capabilities import CapabilityCategory, ToolCapability, SideEffectLevel


@dataclass
class GitRepoInfo:
    """Information about a Git repository."""
    path: str
    is_repo: bool
    branch: str = ""
    remote_url: str = ""
    has_changes: bool = False


class GitAdapter(BaseApplicationAdapter):
    """
    Git application adapter using subprocess with argument arrays (no shell=True).
    Integrates with workspace security boundaries and terminal execution controls.
    """
    
    def __init__(
        self,
        adapter_id: str = "git_adapter",
        workspace_root: Optional[str] = None,
        instance_id: Optional[str] = None
    ):
        display_name = "Git Adapter"
        super().__init__(adapter_id, "git", display_name)
        
        self._instance_id = instance_id or str(uuid.uuid4())[:8]
        self._workspace_root = workspace_root or os.getcwd()
        self._git_executable = self._find_git_executable()
        self._repo_info: Optional[GitRepoInfo] = None
        self._initialized = False
        self._available = False
    
    def _find_git_executable(self) -> Optional[str]:
        """Find Git executable."""
        possible_paths = [
            r"C:\Users\anshu\AppData\Local\hermes\tools\git-2.53.0+3-win32-x64\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
            r"C:\Program Files (x86)\Git\bin\git.exe",
            "git",  # In PATH
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue
        return None
    
    def get_capabilities(self) -> List[str]:
        return [
            "git.status",
            "git.log",
            "git.diff",
            "git.branch_list",
            "git.branch_create",
            "git.add",
            "git.commit",
            "git.checkout",
        ]
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self.application_id,
            display_name=self._display_name,
            version="1.0.0",
            supported_capabilities=self.get_capabilities(),
            availability_requirements=["git"],
            environment_requirements=["git", "windows"],
            lifecycle_requirements=["git_repo"],
            security_metadata={
                "side_effect_level": "write",
                "risk_level": "medium",
                "requires_verification": True,
                "permission_required": "terminal.run",
            },
            side_effect_level="write",
            risk_level="medium",
            requires_verification=True,
            initialization_timeout=10.0,
            execution_timeout=30.0,
            cleanup_timeout=5.0,
        )
    
    def _do_initialize(self) -> bool:
        """Initialize Git adapter - detect Git and repository."""
        if not self._git_executable:
            self._set_error("Git executable not found")
            return False
        
        try:
            # Detect repository in workspace
            self._repo_info = self._detect_repository(self._workspace_root)
            if not self._repo_info or not self._repo_info.is_repo:
                self._set_error(f"No Git repository found in workspace: {self._workspace_root}")
                return False
            
            self._mark_initialized()
            return True
        except Exception as e:
            self._set_error(f"Initialization failed: {e}")
            return False
    
    def _detect_repository(self, path: str) -> Optional[GitRepoInfo]:
        """Safely detect Git repository."""
        if not path or not os.path.exists(path):
            return None
        
        try:
            # Check if it's a Git repo
            result = subprocess.run(
                [self._git_executable, "rev-parse", "--is-inside-work-tree"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0 or result.stdout.strip() != "true":
                return GitRepoInfo(path=path, is_repo=False)
            
            # Get current branch
            branch_result = subprocess.run(
                [self._git_executable, "branch", "--show-current"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
            
            # Get remote URL
            remote_result = subprocess.run(
                [self._git_executable, "config", "--get", "remote.origin.url"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )
            remote_url = remote_result.stdout.strip() if remote_result.returncode == 0 else ""
            
            # Check for changes
            status_result = subprocess.run(
                [self._git_executable, "status", "--porcelain"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10
            )
            has_changes = bool(status_result.stdout.strip()) if status_result.returncode == 0 else False
            
            return GitRepoInfo(
                path=path,
                is_repo=True,
                branch=branch,
                remote_url=remote_url,
                has_changes=has_changes
            )
        except Exception as e:
            return GitRepoInfo(path=path, is_repo=False)
    
    def _validate_workspace_path(self, path: str) -> bool:
        """Validate that path is within workspace boundaries."""
        try:
            workspace = os.path.abspath(self._workspace_root)
            target = os.path.abspath(path)
            common = os.path.commonpath([workspace, target])
            return common == workspace
        except Exception:
            return False
    
    def _run_git_command(self, args: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
        """Run a Git command safely with argument array (no shell=True)."""
        if not self._git_executable:
            return {"success": False, "error": "Git executable not available"}
        
        work_dir = cwd or self._workspace_root
        
        # Security: Validate working directory is within workspace
        if not self._validate_workspace_path(work_dir):
            return {"success": False, "error": f"Working directory '{work_dir}' outside workspace"}
        
        try:
            # Use subprocess with argument array - no shell=True
            cmd = [self._git_executable] + args
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Git command timed out"}
        except Exception as e:
            return {"success": False, "error": f"Git command failed: {e}"}
    
    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute a Git action."""
        if action == "git.status":
            return self._execute_status(arguments)
        elif action == "git.log":
            return self._execute_log(arguments)
        elif action == "git.diff":
            return self._execute_diff(arguments)
        elif action == "git.branch_list":
            return self._execute_branch_list(arguments)
        elif action == "git.branch_create":
            return self._execute_branch_create(arguments)
        elif action == "git.add":
            return self._execute_add(arguments)
        elif action == "git.commit":
            return self._execute_commit(arguments)
        elif action == "git.checkout":
            return self._execute_checkout(arguments)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    def _execute_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get Git status."""
        result = self._run_git_command(["status", "--porcelain"])
        
        if not result["success"]:
            return result
        
        # Parse status output
        files = []
        for line in result["stdout"].strip().split('\n'):
            if line:
                status_code = line[:2]
                filepath = line[3:]
                files.append({
                    "status": status_code.strip(),
                    "path": filepath,
                })
        
        return {
            "success": True,
            "repository": self._repo_info.path if self._repo_info else "",
            "branch": self._repo_info.branch if self._repo_info else "",
            "has_changes": len(files) > 0,
            "files": files,
            "raw_output": result["stdout"],
        }
    
    def _execute_log(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get Git log."""
        count = arguments.get("count", 10)
        oneline = arguments.get("oneline", True)
        
        args = ["log"]
        if oneline:
            args.append("--oneline")
        args.extend(["-n", str(count)])
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        commits = []
        for line in result["stdout"].strip().split('\n'):
            if line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                    })
                else:
                    commits.append({"raw": line})
        
        return {
            "success": True,
            "repository": self._repo_info.path if self._repo_info else "",
            "commits": commits,
            "raw_output": result["stdout"],
        }
    
    def _execute_diff(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get Git diff."""
        staged = arguments.get("staged", False)
        filepath = arguments.get("path", "")
        
        args = ["diff"]
        if staged:
            args.append("--cached")
        if filepath:
            # Security: Validate path
            if not self._validate_workspace_path(os.path.join(self._workspace_root, filepath)):
                return {"success": False, "error": f"Path '{filepath}' outside workspace"}
            args.append("--")
            args.append(filepath)
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        return {
            "success": True,
            "repository": self._repo_info.path if self._repo_info else "",
            "diff": result["stdout"],
            "staged": staged,
            "path": filepath,
        }
    
    def _execute_branch_list(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List Git branches."""
        remote = arguments.get("remote", False)
        
        args = ["branch"]
        if remote:
            args.append("-r")
        else:
            args.append("--list")
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        branches = []
        for line in result["stdout"].strip().split('\n'):
            if line:
                line = line.strip()
                is_current = line.startswith('*')
                if is_current:
                    line = line[1:].strip()
                branches.append({
                    "name": line,
                    "current": is_current,
                })
        
        return {
            "success": True,
            "repository": self._repo_info.path if self._repo_info else "",
            "current_branch": self._repo_info.branch if self._repo_info else "",
            "branches": branches,
        }
    
    def _execute_branch_create(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Git branch."""
        branch_name = arguments.get("name", "")
        start_point = arguments.get("start_point", "")
        
        if not branch_name:
            return {"success": False, "error": "Missing required argument: name"}
        
        # Security: Validate branch name (no shell metacharacters)
        if any(c in branch_name for c in [';', '&', '|', '`', '$', '(', ')', '<', '>']):
            return {"success": False, "error": "Invalid branch name: contains shell metacharacters"}
        
        args = ["branch", branch_name]
        if start_point:
            args.append(start_point)
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        # Verify branch was created
        verify_result = self._run_git_command(["branch", "--list", branch_name])
        if verify_result["success"] and branch_name in verify_result["stdout"]:
            return {
                "success": True,
                "branch_created": branch_name,
                "verified": True,
            }
        
        return {
            "success": True,
            "branch_created": branch_name,
            "verified": False,
            "warning": "Branch creation reported success but verification failed",
        }
    
    def _execute_add(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Stage files in Git."""
        files = arguments.get("files", [])
        all_files = arguments.get("all", False)
        
        if all_files:
            args = ["add", "."]
        elif files:
            # Security: Validate each file path
            for f in files:
                if not self._validate_workspace_path(os.path.join(self._workspace_root, f)):
                    return {"success": False, "error": f"File '{f}' outside workspace"}
            args = ["add"] + files
        else:
            return {"success": False, "error": "Must specify files or all=true"}
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        # Verify by checking status
        status_result = self._run_git_command(["status", "--porcelain"])
        staged_files = []
        if status_result["success"]:
            for line in status_result["stdout"].strip().split('\n'):
                if line and line[0] in ['A', 'M', 'D', 'R', 'C']:
                    staged_files.append(line[3:])
        
        return {
            "success": True,
            "staged_files": staged_files,
            "repository": self._repo_info.path if self._repo_info else "",
        }
    
    def _execute_commit(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a Git commit."""
        message = arguments.get("message", "")
        
        if not message:
            return {"success": False, "error": "Missing required argument: message"}
        
        # Security: Message is passed as argument, not shell string
        args = ["commit", "-m", message]
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        # Verify commit was created
        log_result = self._run_git_command(["log", "--oneline", "-1"])
        verified = False
        commit_hash = ""
        if log_result["success"] and log_result["stdout"].strip():
            commit_hash = log_result["stdout"].strip().split(' ')[0]
            if message in log_result["stdout"]:
                verified = True
        
        return {
            "success": True,
            "commit_hash": commit_hash,
            "message": message,
            "verified": verified,
            "repository": self._repo_info.path if self._repo_info else "",
        }
    
    def _execute_checkout(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Checkout a branch or commit."""
        target = arguments.get("target", "")
        create = arguments.get("create", False)
        
        if not target:
            return {"success": False, "error": "Missing required argument: target"}
        
        # Security: Validate target (no shell metacharacters)
        if any(c in target for c in [';', '&', '|', '`', '$', '(', ')', '<', '>']):
            return {"success": False, "error": "Invalid target: contains shell metacharacters"}
        
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(target)
        
        result = self._run_git_command(args)
        
        if not result["success"]:
            return result
        
        # Verify checkout
        branch_result = self._run_git_command(["branch", "--show-current"])
        verified = False
        current_branch = ""
        if branch_result["success"]:
            current_branch = branch_result["stdout"].strip()
            if current_branch == target or (create and current_branch == target):
                verified = True
        
        return {
            "success": True,
            "checked_out": target,
            "current_branch": current_branch,
            "verified": verified,
            "repository": self._repo_info.path if self._repo_info else "",
        }
    
    def _do_cleanup(self) -> None:
        """Clean up Git adapter resources."""
        self._repo_info = None
        self._initialized = False
        self._available = False


class GitAdapterFactory:
    """Factory for creating isolated Git adapter instances."""
    
    _instances: Dict[str, GitAdapter] = {}
    
    @classmethod
    def create_adapter(cls, adapter_id: str = None, workspace_root: str = None) -> GitAdapter:
        """Create a new isolated Git adapter instance."""
        if adapter_id is None:
            adapter_id = f"git_adapter_{str(uuid.uuid4())[:8]}"
        
        if adapter_id in cls._instances:
            return cls._instances[adapter_id]
        
        adapter = GitAdapter(adapter_id=adapter_id, workspace_root=workspace_root)
        cls._instances[adapter_id] = adapter
        return adapter
    
    @classmethod
    def get_adapter(cls, adapter_id: str) -> Optional[GitAdapter]:
        return cls._instances.get(adapter_id)
    
    @classmethod
    def remove_adapter(cls, adapter_id: str) -> bool:
        adapter = cls._instances.pop(adapter_id, None)
        if adapter:
            adapter.cleanup()
            return True
        return False
    
    @classmethod
    def list_instances(cls) -> List[str]:
        return list(cls._instances.keys())
    
    @classmethod
    def cleanup_all(cls) -> None:
        for adapter in cls._instances.values():
            try:
                adapter.cleanup()
            except Exception:
                pass
        cls._instances.clear()


def create_git_adapter(adapter_id: str = None, workspace_root: str = None) -> GitAdapter:
    """Create and initialize a Git adapter."""
    adapter = GitAdapterFactory.create_adapter(adapter_id, workspace_root)
    if adapter.initialize():
        return adapter
    else:
        GitAdapterFactory.remove_adapter(adapter.adapter_id)
        raise RuntimeError(f"Failed to initialize Git adapter: {adapter.get_last_error()}")