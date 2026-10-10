"""
GitHub Application Adapter - Stage 32 Phase 7
GitHub adapter for read-only repository intelligence.

Capabilities exposed:
- github.repo_info
- github.list_branches
- github.list_commits
- github.get_file_content
- github.list_issues
- github.get_issue
- github.list_pull_requests
- github.get_pull_request
- github.search_repositories
"""

import os
import json
import urllib.request
import urllib.error
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional, Set

from app.extensions.application_adapter import (
    ApplicationAdapterInterface,
    BaseApplicationAdapter,
    AdapterMetadata,
    AdapterState,
)
from app.tools.capabilities import CapabilityCategory, ToolCapability, SideEffectLevel


class GitHubAdapter(BaseApplicationAdapter):
    """
    GitHub application adapter for read-only operations.
    Integrates with existing security boundaries and monitoring.
    """
    
    def __init__(
        self,
        adapter_id: str = "github_adapter",
        instance_id: Optional[str] = None
    ):
        display_name = "GitHub Adapter"
        super().__init__(adapter_id, "github", display_name)
        
        self._instance_id = instance_id or str(uuid.uuid4())[:8]
        self._token = os.environ.get("GITHUB_TOKEN")
        self._api_base = "https://api.github.com"
        self._session = None  # We'll use urllib, no session needed
        self._timeout = 10  # seconds
        self._max_retries = 2
        
        # Repository allowlist configuration
        self._allowed_repositories: Optional[Set[str]] = None
        self._allowlist_configured = False
        self._load_allowlist_from_env()

    def _load_allowlist_from_env(self) -> None:
        """Load repository allowlist from environment variable."""
        allowlist_str = os.environ.get("GITHUB_ALLOWED_REPOSITORIES", "")
        if allowlist_str:
            self._allowlist_configured = True
            # Parse comma-separated list of "owner/repo" entries
            repos = set()
            for entry in allowlist_str.split(","):
                entry = entry.strip()
                if entry:
                    # Normalize to lowercase for consistent comparison
                    normalized = entry.lower()
                    # Basic validation: should contain exactly one slash
                    if normalized.count("/") == 1:
                        owner, repo = normalized.split("/", 1)
                        if owner and repo and " " not in owner and " " not in repo:
                            repos.add(normalized)
                    # Invalid entries are ignored (fail-safe behavior)
            self._allowed_repositories = repos
        else:
            self._allowlist_configured = False
            self._allowed_repositories = None

    def _is_repository_allowed(self, owner: str, repo: str) -> bool:
        """Check if a repository is allowed by the allowlist policy."""
        if not self._allowlist_configured:
            # No allowlist configured - preserve existing documented policy
            # Limited by the token's actual GitHub permissions
            return True
        
        if self._allowed_repositories is None:
            # This shouldn't happen, but fail closed for safety
            return False
        
        if len(self._allowed_repositories) == 0:
            # Empty allowlist - deny all repository-specific access
            return False
        
        # Check if the repository is in the allowlist (case-insensitive)
        normalized = f"{owner.lower()}/{repo.lower()}"
        return normalized in self._allowed_repositories

    def get_capabilities(self) -> List[str]:
        return [
            "github.repo_info",
            "github.list_branches",
            "github.list_commits",
            "github.get_file_content",
            "github.list_issues",
            "github.get_issue",
            "github.list_pull_requests",
            "github.get_pull_request",
            "github.search_repositories",
        ]
    
    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=self._adapter_id,
            application_id=self.application_id,
            display_name=self._display_name,
            version="1.0.0",
            supported_capabilities=self.get_capabilities(),
            availability_requirements=["github"],
            environment_requirements=["windows"],  # Assuming Windows, but adapter should work cross-platform
            lifecycle_requirements=["network"],
            security_metadata={
                "side_effect_level": "read",
                "risk_level": "low",  # Read-only operations
                "requires_verification": False,  # Read-only, no verification needed by default
                "permission_required": "github.read",
            },
            side_effect_level="read",
            risk_level="low",
            requires_verification=False,
            initialization_timeout=10.0,
            execution_timeout=30.0,
            cleanup_timeout=5.0,
        )
    
    def _do_initialize(self) -> bool:
        """Initialize GitHub adapter - validate token and API accessibility."""
        # We don't require token for public repositories, but we can validate format if present
        if self._token:
            # Basic token format check (GitHub tokens are long strings)
            if len(self._token) < 10:  # Arbitrary minimum length
                self._set_error("Invalid GITHUB_TOKEN format")
                return False
        # We could do a lightweight API call to check connectivity, but to avoid
        # unnecessary network usage during initialization, we'll skip it.
        # The first actual API call will reveal connectivity issues.
        self._mark_initialized()
        return True
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request to the GitHub API."""
        url = f"{self._api_base}{endpoint}"
        if params:
            # Filter out None values
            params = {k: v for k, v in params.items() if v is not None}
            if params:
                url += "?" + urllib.parse.urlencode(params)
        
        req = urllib.request.Request(url)
        if self._token:
            req.add_header("Authorization", f"token {self._token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        
        for attempt in range(self._max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as response:
                    status = response.getcode()
                    if status == 200:
                        data = json.loads(response.read().decode('utf-8'))
                        return {"success": True, "data": data}
                    elif status == 304:
                        # Not modified - we could handle caching, but for now treat as success with empty data
                        return {"success": True, "data": None}
                    else:
                        # Handle other status codes as errors
                        error_data = json.loads(response.read().decode('utf-8')) if status != 204 else {}
                        return {
                            "success": False,
                            "error": f"GitHub API error: {status}",
                            "status": status,
                            "error_data": error_data
                        }
            except urllib.error.HTTPError as e:
                # HTTP error (4xx, 5xx)
                error_data = {}
                try:
                    error_data = json.loads(e.read().decode('utf-8'))
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": f"GitHub API error: {e.code}",
                    "status": e.code,
                    "error_data": error_data
                }
            except urllib.error.URLError as e:
                # Network error
                if attempt < self._max_retries:
                    continue  # Retry on network error
                return {
                    "success": False,
                    "error": f"Network error: {str(e.reason)}"
                }
            except Exception as e:
                if attempt < self._max_retries:
                    continue
                return {
                    "success": False,
                    "error": f"Unexpected error: {str(e)}"
                }
        # Should not reach here
        return {"success": False, "error": "Max retries exceeded"}
    
    def _validate_repository(self, owner: str, repo: str) -> Optional[str]:
        """Validate owner and repository name."""
        if not owner or not repo:
            return "Owner and repository name are required"
        # Reject control characters (including newline, null byte) and other invalid characters
        if any(ord(c) < 32 or ord(c) == 127 for c in owner + repo):
            return "Invalid owner or repository name"
        # GitHub repository names: alphanumeric, hyphens, underscores, dots
        # We'll do a basic validation - reject obvious malicious input
        if not owner.isalnum() and '-' not in owner and '_' not in owner and '.' not in owner:
            # Actually, GitHub allows more characters, but we'll keep it simple for security
            # Better to rely on GitHub's validation, but we do basic sanity
            pass  # We'll let GitHub validate, just check for empty
        if '..' in owner or '..' in repo:
            return "Invalid owner or repository name"
        if '/' in owner or '/' in repo:
            return "Invalid owner or repository name"
        return None

    def _validate_repository_and_authorization(self, owner: str, repo: str) -> Optional[str]:
        """Validate owner/repository name and check authorization against allowlist."""
        # First do basic validation
        validation_error = self._validate_repository(owner, repo)
        if validation_error:
            return validation_error
        
        # Then check allowlist authorization
        if not self._is_repository_allowed(owner, repo):
            if self._allowlist_configured:
                if self._allowed_repositories is None or len(self._allowed_repositories) == 0:
                    return "Repository access denied: allowlist is empty or not configured"
                else:
                    return f"Repository access denied: {owner}/{repo} not in allowlist"
            else:
                # This case shouldn't happen due to logic above, but fail closed
                return "Repository access denied"
        
        return None

    def _do_execute(self, action: str, arguments: Dict[str, Any]) -> Any:
        """Execute a GitHub action."""
        if action == "github.repo_info":
            return self._execute_repo_info(arguments)
        elif action == "github.list_branches":
            return self._execute_list_branches(arguments)
        elif action == "github.list_commits":
            return self._execute_list_commits(arguments)
        elif action == "github.get_file_content":
            return self._execute_get_file_content(arguments)
        elif action == "github.list_issues":
            return self._execute_list_issues(arguments)
        elif action == "github.get_issue":
            return self._execute_get_issue(arguments)
        elif action == "github.list_pull_requests":
            return self._execute_list_pull_requests(arguments)
        elif action == "github.get_pull_request":
            return self._execute_get_pull_request(arguments)
        elif action == "github.search_repositories":
            return self._execute_search_repositories(arguments)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    # --- Action Implementations ---
    def _execute_repo_info(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get repository information."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        auth_error = self._validate_repository_and_authorization(owner, repo)
        if auth_error:
            return {"success": False, "error": auth_error}
        
        endpoint = f"/repos/{owner}/{repo}"
        result = self._make_request(endpoint)
        if not result["success"]:
            return result
        
        data = result["data"]
        return {
            "success": True,
            "repository": {
                "id": data.get("id"),
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "owner": data.get("owner", {}).get("login"),
                "private": data.get("private"),
                "html_url": data.get("html_url"),
                "description": data.get("description"),
                "fork": data.get("fork"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "pushed_at": data.get("pushed_at"),
                "size": data.get("size"),
                "stargazers_count": data.get("stargazers_count"),
                "watchers_count": data.get("watchers_count"),
                "language": data.get("language"),
                "has_issues": data.get("has_issues"),
                "has_projects": data.get("has_projects"),
                "has_wiki": data.get("has_wiki"),
                "license": data.get("license"),
            },
            "raw_output": data
        }
    
    def _execute_list_branches(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List repository branches."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        auth_error = self._validate_repository_and_authorization(owner, repo)
        if auth_error:
            return {"success": False, "error": auth_error}
        
        endpoint = f"/repos/{owner}/{repo}/branches"
        # Optional parameters: protected (bool), per_page (int), page (int)
        params = {}
        if arguments.get("protected") is not None:
            params["protected"] = str(arguments["protected"]).lower()
        if "per_page" in arguments:
            params["per_page"] = min(max(1, arguments["per_page"]), 100)  # Bound to 1-100
        if "page" in arguments:
            params["page"] = max(1, arguments["page"])
        
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        branches = []
        for branch in data:
            branches.append({
                "name": branch.get("name"),
                "commit": {
                    "sha": branch.get("commit", {}).get("sha"),
                    "url": branch.get("commit", {}).get("url"),
                },
                "protected": branch.get("protected", False),
            })
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "branches": branches,
            "raw_output": data
        }
    
    def _execute_list_commits(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List repository commits."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        auth_error = self._validate_repository_and_authorization(owner, repo)
        if auth_error:
            return {"success": False, "error": auth_error}
        
        endpoint = f"/repos/{owner}/{repo}/commits"
        params = {}
        if "sha" in arguments:
            params["sha"] = arguments["sha"]  # Branch or commit SHA
        if "since" in arguments:
            params["since"] = arguments["since"]
        if "until" in arguments:
            params["until"] = arguments["until"]
        if "author" in arguments:
            params["author"] = arguments["author"]
        if "per_page" in arguments:
            params["per_page"] = min(max(1, arguments["per_page"]), 100)
        if "page" in arguments:
            params["page"] = max(1, arguments["page"])
        
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        commits = []
        for commit in data:
            commits.append({
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message"),
                "author": {
                    "name": commit.get("commit", {}).get("author", {}).get("name"),
                    "email": commit.get("commit", {}).get("author", {}).get("email"),
                },
                "date": commit.get("commit", {}).get("author", {}).get("date"),
                "url": commit.get("html_url"),
            })
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "commits": commits,
            "raw_output": data
        }
    
    def _execute_get_file_content(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get content of a file in the repository."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        path = arguments.get("path")
        ref = arguments.get("ref")  # Branch, tag, or commit SHA
        auth_error = self._validate_repository_and_authorization(owner, repo)
        if auth_error:
            return {"success": False, "error": auth_error}
        if not path:
            return {"success": False, "error": "File path is required"}
        # Basic path validation: reject absolute paths and obvious traversal
        if path.startswith("/") or ".." in path:
            return {"success": False, "error": "Invalid file path"}
        
        endpoint = f"/repos/{owner}/{repo}/contents/{path}"
        params = {}
        if ref:
            params["ref"] = ref
        
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        # If it's a file, GitHub returns object with content (base64 encoded)
        # If it's a directory, returns list - we'll treat as error for this capability
        if isinstance(data, list):
            return {"success": False, "error": "Path points to a directory, not a file"}
        
        content = None
        encoding = data.get("encoding")
        if encoding == "base64":
            import base64
            content = base64.b64decode(data["content"]).decode('utf-8')
        elif data.get("content") is not None:
            content = data["content"]  # Might be plain text if not base64
        else:
            content = ""  # Empty file
        
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "file": {
                "path": path,
                "content": content,
                "sha": data.get("sha"),
                "size": data.get("size"),
                "url": data.get("html_url"),
                "git_url": data.get("git_url"),
                "download_url": data.get("download_url"),
            },
            "raw_output": data
        }
    
    def _execute_list_issues(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List repository issues."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        validation_error = self._validate_repository(owner, repo)
        if validation_error:
            return {"success": False, "error": validation_error}
        
        endpoint = f"/repos/{owner}/{repo}/issues"
        params = {}
        if "state" in arguments:
            params["state"] = arguments["state"]  # open, closed, all
        if "labels" in arguments:
            params["labels"] = arguments["labels"]  # Comma-separated
        if "sort" in arguments:
            params["sort"] = arguments["sort"]
        if "direction" in arguments:
            params["direction"] = arguments["direction"]
        if "since" in arguments:
            params["since"] = arguments["since"]
        if "per_page" in arguments:
            params["per_page"] = min(max(1, arguments["per_page"]), 100)
        if "page" in arguments:
            params["page"] = max(1, arguments["page"])
        
        # Note: This pulls both issues and PRs. To get only issues, we'd need to filter.
        # But the GitHub API for /issues includes PRs. We'll note that in documentation.
        # For simplicity, we'll return all and let the caller filter if needed.
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        issues = []
        for issue in data:
            # Skip pull requests (they appear in issues endpoint)
            if "pull_request" in issue:
                continue
            issues.append({
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "user": issue.get("user", {}).get("login"),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
                "closed_at": issue.get("closed_at"),
                "labels": [label.get("name") for label in issue.get("labels", [])],
                "assignee": issue.get("assignee", {}).get("login") if issue.get("assignee") else None,
                "html_url": issue.get("html_url"),
            })
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "issues": issues,
            "raw_output": data
        }
    
    def _execute_get_issue(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single issue."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        issue_number = arguments.get("issue_number")
        validation_error = self._validate_repository(owner, repo)
        if validation_error:
            return {"success": False, "error": validation_error}
        if issue_number is None or (isinstance(issue_number, str) and issue_number.strip() == ""):
            return {"success": False, "error": "Issue number is required"}
        try:
            issue_num = int(issue_number)
            if issue_num <= 0:
                return {"success": False, "error": "Issue number must be positive"}
        except ValueError:
            return {"success": False, "error": "Issue number must be an integer"}
        
        endpoint = f"/repos/{owner}/{repo}/issues/{issue_number}"
        result = self._make_request(endpoint)
        if not result["success"]:
            return result
        
        data = result["data"]
        # Check if it's actually a pull request
        if "pull_request" in data:
            return {"success": False, "error": "This is a pull request, not an issue"}
        
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "issue": {
                "number": data.get("number"),
                "title": data.get("title"),
                "state": data.get("state"),
                "user": data.get("user", {}).get("login"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "closed_at": data.get("closed_at"),
                "labels": [label.get("name") for label in data.get("labels", [])],
                "assignee": data.get("assignee", {}).get("login") if data.get("assignee") else None,
                "body": data.get("body"),
                "html_url": data.get("html_url"),
            },
            "raw_output": data
        }
    
    def _execute_list_pull_requests(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List repository pull requests."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        validation_error = self._validate_repository(owner, repo)
        if validation_error:
            return {"success": False, "error": validation_error}
        
        endpoint = f"/repos/{owner}/{repo}/pulls"
        params = {}
        if "state" in arguments:
            params["state"] = arguments["state"]  # open, closed, all
        if "head" in arguments:
            params["head"] = arguments["head"]  # Filter by head branch
        if "base" in arguments:
            params["base"] = arguments["base"]  # Filter by base branch
        if "sort" in arguments:
            params["sort"] = arguments["sort"]
        if "direction" in arguments:
            params["direction"] = arguments["direction"]
        if "per_page" in arguments:
            params["per_page"] = min(max(1, arguments["per_page"]), 100)
        if "page" in arguments:
            params["page"] = max(1, arguments["page"])
        
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        pull_requests = []
        for pr in data:
            pull_requests.append({
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "user": pr.get("user", {}).get("login"),
                "created_at": pr.get("created_at"),
                "updated_at": pr.get("updated_at"),
                "closed_at": pr.get("closed_at"),
                "merged_at": pr.get("merged_at"),
                "head": {
                    "ref": pr.get("head", {}).get("ref"),
                    "sha": pr.get("head", {}).get("sha"),
                    "repo": {
                        "name": pr.get("head", {}).get("repo", {}).get("name") if pr.get("head", {}).get("repo") else None,
                    }
                },
                "base": {
                    "ref": pr.get("base", {}).get("ref"),
                    "sha": pr.get("base", {}).get("sha"),
                    "repo": {
                        "name": pr.get("base", {}).get("repo", {}).get("name") if pr.get("base", {}).get("repo") else None,
                    }
                },
                "labels": [label.get("name") for label in pr.get("labels", [])],
                "assignee": pr.get("assignee", {}).get("login") if pr.get("assignee") else None,
                "html_url": pr.get("html_url"),
            })
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "pull_requests": pull_requests,
            "raw_output": data
        }
    
    def _execute_get_pull_request(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a single pull request."""
        owner = arguments.get("owner")
        repo = arguments.get("repo")
        pr_number = arguments.get("pull_request_number")
        validation_error = self._validate_repository(owner, repo)
        if validation_error:
            return {"success": False, "error": validation_error}
        if not pr_number:
            return {"success": False, "error": "Pull request number is required"}
        try:
            pr_num = int(pr_number)
            if pr_num <= 0:
                return {"success": False, "error": "Pull request number must be positive"}
        except ValueError:
            return {"success": False, "error": "Pull request number must be an integer"}
        
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        result = self._make_request(endpoint)
        if not result["success"]:
            return result
        
        data = result["data"]
        return {
            "success": True,
            "repository": f"{owner}/{repo}",
            "pull_request": {
                "number": data.get("number"),
                "title": data.get("title"),
                "state": data.get("state"),
                "user": data.get("user", {}).get("login"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "closed_at": data.get("closed_at"),
                "merged_at": data.get("merged_at"),
                "head": {
                    "ref": data.get("head", {}).get("ref"),
                    "sha": data.get("head", {}).get("sha"),
                    "repo": {
                        "name": data.get("head", {}).get("repo", {}).get("name") if data.get("head", {}).get("repo") else None,
                    }
                },
                "base": {
                    "ref": data.get("base", {}).get("ref"),
                    "sha": data.get("base", {}).get("sha"),
                    "repo": {
                        "name": data.get("base", {}).get("repo", {}).get("name") if data.get("base", {}).get("repo") else None,
                    }
                },
                "labels": [label.get("name") for label in data.get("labels", [])],
                "assignee": data.get("assignee", {}).get("login") if data.get("assignee") else None,
                "body": data.get("body"),
                "html_url": data.get("html_url"),
            },
            "raw_output": data
        }
    
    def _execute_search_repositories(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Search for repositories."""
        query = arguments.get("query")
        if not query:
            return {"success": False, "error": "Search query is required"}
        # Basic validation: reject empty or overly long queries
        if len(query) > 256:  # GitHub limit is 256 characters for query
            return {"success": False, "error": "Search query too long"}
        
        endpoint = f"/search/repositories"
        params = {"q": query}
        if "sort" in arguments:
            params["sort"] = arguments["sort"]
        if "order" in arguments:
            params["order"] = arguments["order"]
        if "per_page" in arguments:
            params["per_page"] = min(max(1, arguments["per_page"]), 100)
        if "page" in arguments:
            params["page"] = max(1, arguments["page"])
        
        result = self._make_request(endpoint, params)
        if not result["success"]:
            return result
        
        data = result["data"]
        repositories = []
        for item in data.get("items", []):
            repositories.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "full_name": item.get("full_name"),
                "owner": item.get("owner", {}).get("login"),
                "html_url": item.get("html_url"),
                "description": item.get("description"),
                "fork": item.get("fork"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "pushed_at": item.get("pushed_at"),
                "size": item.get("size"),
                "stargazers_count": item.get("stargazers_count"),
                "watchers_count": item.get("watchers_count"),
                "language": item.get("language"),
                "archived": item.get("archived"),
            })
        return {
            "success": True,
            "query": query,
            "total_count": data.get("total_count"),
            "incomplete_results": data.get("incomplete_results", False),
            "repositories": repositories,
            "raw_output": data
        }
    
    def _do_cleanup(self) -> None:
        """Clean up GitHub adapter resources."""
        # No persistent resources to clean up with urllib
        self._session = None


class GitHubAdapterFactory:
    """Factory for creating isolated GitHub adapter instances."""
    
    _instances: Dict[str, GitHubAdapter] = {}
    
    @classmethod
    def create_adapter(cls, adapter_id: str = None) -> GitHubAdapter:
        """Create a new isolated GitHub adapter instance."""
        if adapter_id is None:
            adapter_id = f"github_adapter_{str(uuid.uuid4())[:8]}"
        
        if adapter_id in cls._instances:
            return cls._instances[adapter_id]
        
        adapter = GitHubAdapter(adapter_id=adapter_id)
        cls._instances[adapter_id] = adapter
        return adapter
    
    @classmethod
    def get_adapter(cls, adapter_id: str) -> Optional[GitHubAdapter]:
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


def create_github_adapter(adapter_id: str = None) -> GitHubAdapter:
    adapter = GitHubAdapterFactory.create_adapter(adapter_id)
    if adapter.initialize():
        return adapter
    else:
        GitHubAdapterFactory.remove_adapter(adapter.adapter_id)
        raise RuntimeError(f"Failed to initialize GitHub adapter: {adapter.get_last_error()}")
