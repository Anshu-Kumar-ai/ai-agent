import sys

import pytest

from app.core.permissions import PermissionManager, RiskLevel


def test_scoped_session_allows_sibling_writes():
    pm = PermissionManager(workspace_root="/project")
    # Grant session permission for writing a file in /project/src/foo.py
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Should allow writing to another file in same workspace
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project/src/bar.py", "data": "world"}
    )
    assert allowed is True
    assert "Scoped permission granted" in reason


def test_scoped_session_does_not_allow_outside_workspace():
    pm = PermissionManager(workspace_root="/project")
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Try to write to /project2/foo.py
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project2/foo.py", "data": "hello"}
    )
    assert allowed is False
    assert "requires approval" in reason


def test_scoped_write_does_not_allow_delete():
    pm = PermissionManager(workspace_root="/project")
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Try to delete a file
    allowed, reason = pm.check_permission(
        "delete_file", {"path": "/project/src/foo.py"}
    )
    assert allowed is False
    assert "requires approval" in reason


def test_scoped_write_does_not_allow_shell():
    pm = PermissionManager(workspace_root="/project")
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Try to execute a shell command
    allowed, reason = pm.check_permission(
        "run_command", {"cmd": "echo hello"}
    )
    assert allowed is False
    assert "requires approval" in reason


def test_high_operation_blocked_even_with_scoped_permission():
    pm = PermissionManager(workspace_root="/project")
    # Grant a scoped permission for write (medium) but we will try a high-risk delete
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Even though we have a scoped write permission, delete is high and should be blocked
    allowed, reason = pm.check_permission(
        "delete_file", {"path": "/project/src/foo.py"}
    )
    assert allowed is False
    assert "HIGH-risk action requires approval" in reason


def test_critical_operation_always_blocked():
    pm = PermissionManager(workspace_root="/project")
    # We need to classify something as critical; we can mock classify_risk or rely on existing classification.
    # For simplicity, we'll monkey-patch classify_risk to return CRITICAL for a specific tool.
    original_classify = pm.classify_risk
    pm.classify_risk = lambda tool_name, args: RiskLevel.CRITICAL if tool_name == "dangerous_tool" else original_classify(tool_name, args)
    try:
        # Grant a scoped permission for write (should not matter)
        pm.grant_permission(
            tool_name="write_file",
            arguments={"path": "/project/src/foo.py", "data": "hello"},
            scope="/project/src/foo.py",
            duration="session",
        )
        # Try the dangerous tool
        allowed, reason = pm.check_permission(
            "dangerous_tool", {"some": "arg"}
        )
        assert allowed is False
        assert "CRITICAL-risk action requires approval" in reason
    finally:
        pm.classify_risk = original_classify


def test_one_time_scoped_permission_consumed():
    pm = PermissionManager(workspace_root="/project")
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "first"},
        scope="/project/src/foo.py",
        duration="one_time",
    )
    # First use should succeed
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project/src/foo.py", "data": "second"}
    )
    assert allowed is True
    assert "Scoped permission granted" in reason
    # Second use should fail because one-time consumed
    allowed2, reason2 = pm.check_permission(
        "write_file", {"path": "/project/src/foo.py", "data": "third"}
    )
    assert allowed2 is False
    assert "requires approval" in reason2


def test_session_scoped_permission_persists():
    pm = PermissionManager(workspace_root="/project")
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/foo.py", "data": "hello"},
        scope="/project/src/foo.py",
        duration="session",
    )
    # Multiple checks should all succeed
    for i in range(3):
        allowed, reason = pm.check_permission(
            "write_file", {"path": f"/project/src/file{i}.txt", "data": f"data{i}"}
        )
        assert allowed is True
        assert "Scoped permission granted" in reason


@pytest.mark.skipif(not sys.platform.startswith('win'), reason="Windows-specific test")
def test_windows_style_paths():
    # Test that backslash is recognized as a path separator and permission works within workspace.
    pm = PermissionManager(workspace_root="C:\\project")
    # Use a path with backslashes that lies inside the workspace.
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "C:\\project\\src\\foo.txt", "data": "hello"},
        scope="C:\\project\\src\\foo.txt",
        duration="session",
    )
    # Allow another file with backslashes
    allowed, reason = pm.check_permission(
        "write_file", {"path": "C:\\project\\src\\bar.txt", "data": "world"}
    )
    assert allowed is True
    # Also test forward slashes (should still work)
    allowed2, reason2 = pm.check_permission(
        "write_file", {"path": "C:/project/src/baz.txt", "data": "baz"}
    )
    assert allowed2 is True


def test_no_bypass_via_executor():
    from app.tools.base import BaseTool
    from app.tools.calculator import CalculatorTool
    from app.tools.executor import ToolExecutor
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    executor = ToolExecutor(registry)
    pm = PermissionManager(workspace_root="/tmp")
    # Try to execute a medium-risk tool without permission -> should raise PermissionError via safe_execute
    from app.core.permissions import safe_execute
    # Create a dummy tool that inherits from BaseTool
    class DummyWriteTool(BaseTool):
        name = "write_file"
        def execute(self, path, data):
            return f"wrote {len(data)} bytes to {path}"
    # Register it
    registry.register(DummyWriteTool())
    # Now try to execute without permission
    try:
        safe_execute(executor, pm, "write_file", path="/tmp/foo.txt", data="test")
        assert False, "Expected PermissionError"
    except PermissionError:
        pass  # expected
    # After granting scoped permission, safe_execute should succeed
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/tmp/foo.txt", "data": "test"},
        scope="/tmp/foo.txt",
        duration="session",
    )
    result = safe_execute(executor, pm, "write_file", path="/tmp/foo.txt", data="test")
    assert "wrote" in result


def test_integration_repeated_approval_scenario():
    """
    Simulate the actual problem:
    1. Hermes requests a normal file operation inside the workspace.
    2. User grants the appropriate session-scoped permission.
    3. Hermes performs another operation on a different file inside the same workspace.
    4. Hermes performs another operation in a different subdirectory.
    5. No additional approval is requested for those matching operations.
    Then verify:
    6. An operation outside the workspace requires approval.
    7. Delete does not inherit write permission.
    8. Shell execution does not inherit filesystem permission.
    9. HIGH/CRITICAL operations still require approval.
    """
    pm = PermissionManager(workspace_root="/project")
    # Initially, no permissions
    # 1. Request write to /project/src/alpha.txt
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project/src/alpha.txt", "data": "test"}
    )
    assert allowed is False
    assert "requires approval" in reason  # needs approval
    # 2. User grants session-scoped permission for write on that path (as if they approved)
    pm.grant_permission(
        tool_name="write_file",
        arguments={"path": "/project/src/alpha.txt", "data": "test"},
        scope="/project/src/alpha.txt",
        duration="session",
    )
    # 3. Another operation on a different file inside same workspace
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project/src/beta.txt", "data": "test2"}
    )
    assert allowed is True
    assert "Scoped permission granted" in reason
    # 4. Operation in a different subdirectory
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/project/tests/test_something.py", "data": "test3"}
    )
    assert allowed is True
    assert "Scoped permission granted" in reason
    # 5. No additional approval requested (implicitly true because we didn't call grant again)
    # 6. Operation outside the workspace requires approval
    allowed, reason = pm.check_permission(
        "write_file", {"path": "/other/project/gamma.txt", "data": "test"}
    )
    assert allowed is False
    assert "requires approval" in reason
    # 7. Delete does not inherit write permission
    allowed, reason = pm.check_permission(
        "delete_file", {"path": "/project/src/alpha.txt"}
    )
    assert allowed is False
    assert "requires approval" in reason
    # 8. Shell execution does not inherit filesystem permission
    allowed, reason = pm.check_permission(
        "run_command", {"cmd": "ls -la"}
    )
    assert allowed is False
    assert "requires approval" in reason
    # 9. HIGH/CRITICAL operations still require approval
    # We'll test HIGH via delete (already high) and CRITICAL via mock
    # DELETE is HIGH
    allowed, reason = pm.check_permission(
        "delete_file", {"path": "/project/src/alpha.txt"}
    )
    assert allowed is False
    assert "HIGH-risk action requires approval" in reason
    # CRITICAL: mock classify_risk
    original = pm.classify_risk
    pm.classify_risk = lambda t, a: RiskLevel.CRITICAL if t == "danger_tool" else original(t, a)
    try:
        allowed, reason = pm.check_permission("danger_tool", {"foo": "bar"})
        assert allowed is False
        assert "CRITICAL-risk action requires approval" in reason
    finally:
        pm.classify_risk = original