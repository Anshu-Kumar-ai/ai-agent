#!/usr/bin/env python3
"""
Phase 13 Cancellation Validation Test
Tests cancellation at various points in the task lifecycle.
"""

import os
import sys
import tempfile
import time
import threading
import concurrent.futures

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.core.task_executor import TaskExecutor
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.adapters import FSReadTool, FSWriteTool, TerminalRunTool
from app.tools.calculator import CalculatorTool
from app.core.permissions import PermissionManager, ApprovalMode
from app.memory.enhanced import EnhancedMemory
from app.core.planner import Planner
from app.core.evaluator import Evaluator
from app.core.state.task import Task, TaskStatus, PlanVersion


def test_cancellation_before_execution():
    """Test cancellation before any tool execution."""
    workspace = tempfile.mkdtemp(prefix="phase13_cancel_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    registry.register(CalculatorTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = Planner()
    memory = EnhancedMemory()
    evaluator = Evaluator()
    
    task_executor = TaskExecutor(
        planner=planner,
        tool_executor=tool_executor,
        permission_manager=perm_manager,
        memory=memory,
        evaluator=evaluator,
        max_steps=5,
        max_retries_per_step=2,
        max_replans=2
    )
    
    goal = "Write a file test.txt with content 'test', read it back, and verify."
    available_tools = [
        {"name": "fs.write", "description": "Write content to a file", "selection_phrases": ["write file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "fs.read", "description": "Read file contents", "selection_phrases": ["read file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    def responder(plans):
        # Cancel immediately when first plan is generated
        task_executor.cancel_task(task.task_id)
        return "continue"
    
    result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    
    return {
        "status": result_task.status.value,
        "cancelled": result_task.status == TaskStatus.CANCELLED,
        "completed_steps": len(result_task.completed_step_ids),
        "failed_steps": len(result_task.failed_step_ids)
    }


def test_cancellation_during_execution():
    """Test cancellation during tool execution."""
    workspace = tempfile.mkdtemp(prefix="phase13_cancel_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    registry.register(CalculatorTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = Planner()
    memory = EnhancedMemory()
    evaluator = Evaluator()
    
    task_executor = TaskExecutor(
        planner=planner,
        tool_executor=tool_executor,
        permission_manager=perm_manager,
        memory=memory,
        evaluator=evaluator,
        max_steps=10,
        max_retries_per_step=2,
        max_replans=2
    )
    
    goal = "Run a long sleep command: python -c 'import time; time.sleep(10); print(\"done\")' then write result to file."
    available_tools = [
        {"name": "terminal.run", "description": "Execute shell commands", "selection_phrases": ["run command"], "parameters": {"type": "object", "properties": {"cmd": {"type": "array", "items": {"type": "string"}}, "timeout": {"type": "number"}}, "required": ["cmd"]}},
        {"name": "fs.write", "description": "Write content to a file", "selection_phrases": ["write file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    cancel_triggered = [False]
    
    def responder(plans):
        # Cancel after first step starts
        if not cancel_triggered[0]:
            cancel_triggered[0] = True
            # Give a moment for step to start
            time.sleep(0.1)
            task_executor.cancel_task(task.task_id)
        return "continue"
    
    result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    
    return {
        "status": result_task.status.value,
        "cancelled": result_task.status == TaskStatus.CANCELLED,
        "completed_steps": len(result_task.completed_step_ids),
        "failed_steps": len(result_task.failed_step_ids)
    }


def test_cancellation_during_retry():
    """Test cancellation during retry handling."""
    workspace = tempfile.mkdtemp(prefix="phase13_cancel_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = Planner()
    memory = EnhancedMemory()
    evaluator = Evaluator()
    
    task_executor = TaskExecutor(
        planner=planner,
        tool_executor=tool_executor,
        permission_manager=perm_manager,
        memory=memory,
        evaluator=evaluator,
        max_steps=5,
        max_retries_per_step=2,
        max_replans=2
    )
    
    goal = "Write a file test.txt with content 'test', read it back, and verify."
    available_tools = [
        {"name": "fs.write", "description": "Write content to a file", "selection_phrases": ["write file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "fs.read", "description": "Read file contents", "selection_phrases": ["read file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    cancel_triggered = [False]
    
    def responder(plans):
        if not cancel_triggered[0]:
            cancel_triggered[0] = True
            time.sleep(0.05)
            task_executor.cancel_task(task.task_id)
        return "continue"
    
    result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    
    return {
        "status": result_task.status.value,
        "cancelled": result_task.status == TaskStatus.CANCELLED,
        "completed_steps": len(result_task.completed_step_ids),
        "failed_steps": len(result_task.failed_step_ids)
    }


def test_multiple_cancellations():
    """Test multiple cancellation requests."""
    workspace = tempfile.mkdtemp(prefix="phase13_cancel_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    registry.register(CalculatorTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = Planner()
    memory = EnhancedMemory()
    evaluator = Evaluator()
    
    task_executor = TaskExecutor(
        planner=planner,
        tool_executor=tool_executor,
        permission_manager=perm_manager,
        memory=memory,
        evaluator=evaluator,
        max_steps=10,
        max_retries_per_step=2,
        max_replans=2
    )
    
    goal = "Write a file test.txt with content 'test', read it back, and verify."
    available_tools = [
        {"name": "fs.write", "description": "Write content to a file", "selection_phrases": ["write file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "fs.read", "description": "Read file contents", "selection_phrases": ["read file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    # Test multiple cancel calls
    task.cancel()
    result1 = task_executor.cancel_task(task.task_id)
    result2 = task_executor.cancel_task(task.task_id)
    result3 = task_executor.cancel_task(task.task_id)
    
    return {
        "status": task.status.value,
        "cancelled": task.status == TaskStatus.CANCELLED,
        "multiple_cancels_idempotent": result1 and not result2 and not result3,
        "terminal_state": task.is_terminal()
    }


def test_cancellation_after_completion():
    """Test that cancelling a completed task is handled gracefully."""
    workspace = tempfile.mkdtemp(prefix="phase13_cancel_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = Planner()
    memory = EnhancedMemory()
    evaluator = Evaluator()
    
    task_executor = TaskExecutor(
        planner=planner,
        tool_executor=tool_executor,
        permission_manager=perm_manager,
        memory=memory,
        evaluator=evaluator,
        max_steps=5,
        max_retries_per_step=2,
        max_replans=2
    )
    
    goal = "Write a file test.txt with content 'test', read it back, and verify."
    available_tools = [
        {"name": "fs.write", "description": "Write content to a file", "selection_phrases": ["write file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "fs.read", "description": "Read file contents", "selection_phrases": ["read file"], "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    def responder(plans):
        return "continue"
    
    # Execute to completion
    result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    
    # Now try to cancel completed task
    result = task_executor.cancel_task(task.task_id)
    
    return {
        "completed_status": result_task.status.value,
        "cancel_result": result,
        "completed_cancel_noop": not result  # Should return False for already terminal task
    }


def run_cancellation_tests():
    """Run all cancellation tests."""
    print("=== Phase 13 Cancellation Validation ===\n")
    
    results = []
    
    # Test 1: Cancellation before execution
    print("Test 1: Cancellation before execution")
    result = test_cancellation_before_execution()
    print(f"  Status: {result['status']}")
    print(f"  Cancelled: {result['cancelled']}")
    print(f"  Completed steps: {result['completed_steps']}")
    print(f"  Failed steps: {result['failed_steps']}")
    results.append(("Before execution", result['cancelled'] and result['completed_steps'] == 0))
    
    # Test 2: Cancellation during execution
    print("\nTest 2: Cancellation during execution")
    result = test_cancellation_during_execution()
    print(f"  Status: {result['status']}")
    print(f"  Cancelled: {result['cancelled']}")
    print(f"  Completed steps: {result['completed_steps']}")
    print(f"  Failed steps: {result['failed_steps']}")
    results.append(("During execution", result['cancelled']))
    
    # Test 3: Cancellation during retry
    print("\nTest 3: Cancellation during retry")
    result = test_cancellation_during_retry()
    print(f"  Status: {result['status']}")
    print(f"  Cancelled: {result['cancelled']}")
    results.append(("During retry", result['cancelled']))
    
    # Test 4: Multiple cancellations
    print("\nTest 4: Multiple cancellation requests")
    result = test_multiple_cancellations()
    print(f"  Status: {result['status']}")
    print(f"  Cancelled: {result['cancelled']}")
    print(f"  Multiple cancels idempotent: {result['multiple_cancels_idempotent']}")
    print(f"  Terminal state: {result['terminal_state']}")
    results.append(("Multiple cancels", result['cancelled'] and result['multiple_cancels_idempotent'] and result['terminal_state']))
    
    # Test 5: Cancellation after completion
    print("\nTest 5: Cancellation after completion")
    result = test_cancellation_after_completion()
    print(f"  Completed status: {result['completed_status']}")
    print(f"  Cancel result: {result['cancel_result']}")
    print(f"  Completed cancel no-op: {result['completed_cancel_noop']}")
    results.append(("After completion", result['completed_cancel_noop']))
    
    print("\n=== Summary ===")
    for name, passed in results:
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    
    all_passed = all(passed for _, passed in results)
    print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


if __name__ == "__main__":
    import os
    import sys
    import time
    
    sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")
    success = run_cancellation_tests()
    sys.exit(0 if success else 1)