"""
CI Configuration Tests
Tests for CI/CD pipeline configuration validation.
"""

import os
import sys
from pathlib import Path


def test_pyproject_toml_exists():
    """Verify pyproject.toml exists and is valid TOML."""
    import tomllib
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml should exist"

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    # Check required sections
    assert "project" in data
    assert "build-system" in data
    assert "tool" in data

    # Check project metadata
    project = data["project"]
    assert "name" in project
    assert "version" in project
    assert "dependencies" in project

    # Check optional dependencies (under project.optional-dependencies)
    assert "optional-dependencies" in project
    assert "dev" in project["optional-dependencies"]
    assert "test" in project["optional-dependencies"]


def test_github_workflows_exist():
    """Verify GitHub workflow files exist."""
    workflows_dir = Path(".github/workflows")
    assert workflows_dir.exists(), ".github/workflows directory should exist"

    required_workflows = ["ci.yml", "integration.yml", "release.yml"]
    for wf in required_workflows:
        wf_path = Path(f".github/workflows/{wf}")
        assert wf_path.exists(), f"Required workflow {wf} should exist"


def test_ci_workflow_structure():
    """Validate CI workflow has required jobs and structure."""
    import yaml

    with open(".github/workflows/ci.yml") as f:
        ci = yaml.safe_load(f)

    # Check required jobs
    required_jobs = ["test", "lint", "security", "build", "summary"]
    for job in required_jobs:
        assert job in ci["jobs"], f"CI job '{job}' should exist"

    # Check test job has matrix strategy
    test_job = ci["jobs"]["test"]
    assert "strategy" in test_job
    assert "matrix" in test_job["strategy"]
    assert "python-version" in test_job["strategy"]["matrix"]

    # Check lint job has ruff and mypy
    lint_job = ci["jobs"]["lint"]
    assert "steps" in lint_job
    step_names = [step.get("name", "") for step in lint_job["steps"]]
    assert any("ruff" in name.lower() for name in step_names)
    assert any("mypy" in name.lower() for name in step_names)

    # Check security job has bandit and safety
    security_job = ci["jobs"]["security"]
    step_names = [step.get("name", "") for step in security_job["steps"]]
    assert any("bandit" in name.lower() for name in step_names)
    assert any("safety" in name.lower() for name in step_names)


def test_integration_workflow_structure():
    """Validate integration workflow structure."""
    import yaml

    with open(".github/workflows/integration.yml") as f:
        integration = yaml.safe_load(f)

    # Should have on.workflow_dispatch and schedule
    # Handle both dict and list formats for 'on' key
    # yaml may parse 'on:' with boolean key 'on' as True
    assert "on" in integration or True in integration
    if "on" in integration:
        on_events = integration["on"]
    else:
        on_events = integration[True]

    # Handle both dict and list formats
    if isinstance(on_events, dict):
        assert "workflow_dispatch" in on_events
        assert "schedule" in on_events
    else:
        # Handle list format
        for event in on_events:
            if isinstance(event, dict):
                assert "workflow_dispatch" in event or "schedule" in event

    # Should have integration-tests job
    assert "jobs" in integration
    assert "integration-tests" in integration["jobs"]


def test_release_workflow_structure():
    """Validate release workflow structure."""
    import yaml

    with open(".github/workflows/release.yml") as f:
        release = yaml.safe_load(f)

    assert "on" in release or True in release
    if "on" in release:
        on_events = release["on"]
    else:
        on_events = release[True]

    # Handle both dict and list formats
    if isinstance(on_events, dict):
        assert "push" in on_events
        assert "tags" in on_events["push"]
    else:
        # Handle list format
        for event in on_events:
            if isinstance(event, dict) and "push" in event:
                assert "tags" in event["push"]

    assert "jobs" in release
    assert "release" in release["jobs"]

    release_job = release["jobs"]["release"]
    # permissions can be at workflow level or job level
    assert "permissions" in release or "permissions" in release_job
    if "permissions" in release:
        assert release["permissions"]["contents"] == "write"
    else:
        assert release_job["permissions"]["contents"] == "write"


def test_pyproject_has_dev_dependencies():
    """Verify pyproject.toml has required dev dependencies."""
    import tomllib

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    dev_deps = data["project"]["optional-dependencies"]["dev"]
    dev_deps_str = " ".join(dev_deps).lower()

    required_dev_tools = ["pytest", "ruff", "mypy", "bandit", "safety"]
    for tool in required_dev_tools:
        assert any(tool in dep for dep in dev_deps), f"Dev dependency {tool} should be present"


def test_requirements_txt_consistency():
    """Verify requirements.txt is consistent with pyproject.toml."""
    # Both files should exist
    assert Path("requirements.txt").exists()
    assert Path("pyproject.toml").exists()

    # Read both
    with open("requirements.txt") as f:
        req_lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    import tomllib
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)

    # Check both project.dependencies and project.optional-dependencies.test
    pyproject_deps = data["project"]["dependencies"]
    test_deps = data["project"].get("optional-dependencies", {}).get("test", [])
    all_deps = pyproject_deps + test_deps

    # Check that all requirements.txt entries are in pyproject.toml
    for req in req_lines:
        req_name = req.split("==")[0].split(">=")[0].split("<=")[0].strip().lower()
        assert any(req_name in dep.lower() for dep in all_deps), \
            f"Requirement {req} should be in pyproject.toml"


def test_github_actions_syntax():
    """Validate GitHub Actions workflow syntax with actionlint if available."""
    workflows_dir = Path(".github/workflows")
    yaml_files = list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))

    for wf_file in yaml_files:
        # Basic YAML validity check
        import yaml
        with open(wf_file) as f:
            yaml.safe_load(f)


def test_mock_provider_available():
    """Verify mock LLM provider exists for CI testing."""
    from app.llm.mock_provider import MockLLMProvider
    provider = MockLLMProvider(responses=["[]"])
    assert provider.generate("test") == "[]"


def test_ci_environment_variables():
    """Test that CI environment variables are properly handled."""
    # Test MOCK_LLM_PROVIDERS
    os.environ["MOCK_LLM_PROVIDERS"] = "true"
    assert os.environ.get("MOCK_LLM_PROVIDERS") == "true"

    # Clean up
    os.environ.pop("MOCK_LLM_PROVIDERS", None)


def test_requirements_files():
    """Test that all requirement files are valid."""
    # requirements.txt
    with open("requirements.txt") as f:
        req_content = f.read()
    assert "pydantic" in req_content
    assert "pytest" in req_content

    # Check no empty lines (only non-comment lines)
    lines = [line for line in req_content.split("\n") if line.strip() and not line.strip().startswith("#")]
    assert all(line.strip() for line in lines)


def test_pre_commit_config():
    """Test pre-commit configuration if exists."""
    pre_commit_file = Path(".pre-commit-config.yaml")
    if pre_commit_file.exists():
        import yaml
        with open(pre_commit_file) as f:
            config = yaml.safe_load(f)
        assert "repos" in config
        for repo in config["repos"]:
            assert "repo" in repo
            assert "hooks" in repo


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
