#!/usr/bin/env python3
"""Comprehensive cancellation validation tests for Phase 13."""

import sys
import os
import tempfile
import time
import threading

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.core.state.task import Task, TaskStatus
from app.core.task_executor import TaskExecutor
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.adapters import FSReadTool, FSWriteTool, TerminalRunTool
from app.core.permissions import PermissionManager, ApprovalMode
from app.memory.enhanced import EnhancedMemory
from app.core.planner import Planner, Plan
from app.core.evaluator import Evaluator
from app.core.state.task import PlanVersion


class TestPlanner(Planner):
    """Test planner that allows controlled cancellation points."""
    
    def __init__(self, test_type='filesystem', cancel_at_step=None):
        self.test_type = test_type
        self.cancel_at_step = cancel_at_step
        self.step_count = 0
        
    def plan(self, message, available_tools, observations=None, context=None):
        self.step_count += 1
        print(f'Planner step {self.step_count}')
        
        # Check if we should cancel at this step
        if self.cancel_at_step and self.step_count >= self.cancel_at_step:
            # Return a respond plan to allow cancellation check
            return Plan(
                action='respond',
                response=f'Step {self.step_count} completed',
                reason='Allowing cancellation check'
            )
        
        if self.test_type == 'filesystem':
            if self.step_count == 1:
                return Plan(
                    action='use_tool',
                    tool_name='fs.write',
                    arguments={'path': 'test.txt', 'content': 'test data'},
                    reason='Write test file'
                )
            elif self.step_count == 2:
                return Plan(
                    action='use_tool',
                    tool_name='fs.read',
                    arguments={'path': 'test.txt'},
                    reason='Read test file'
                )
            else:
                return Plan(
                    action='respond',
                    response='File operations completed',
                    reason='All steps done'
                )
        elif self.test_type == 'terminal':
            if self.step_count == 1:
                return Plan(
                    action='use_tool',
                    tool_name='terminal.run',
                    arguments={'cmd': ['python', '-c', 'import time; time.sleep(5); print("done")'], 'timeout': 10},
                    reason='Run sleep command'
                )
            else:
                return Plan(
                    action='respond',
                    response='Terminal command completed',
                    reason='Done'
                )
        else:
            return Plan(
                action='respond',
                response='Task completed',
                reason='Default'
            )


def test_cancellation_at_planning():
    """Test cancellation during planning phase."""
    print("\n=== Testing cancellation at planning phase ===")
    
    workspace = tempfile.mkdtemp(prefix='phase13_cancel_plan_')
    os.environ['HERMES_WORKSPACE'] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = TestPlanner(test_type='filesystem', cancel_at_step=1)  # Cancel at first step
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
    
    goal = "Write and read a test file"
    available_tools = [
        {'name': 'fs.write', 'description': 'Write file', 'selection_phrases': ['write file'], 
         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['path', 'content']}},
        {'name': 'fs.read', 'description': 'Read file', 'selection_phrases': ['read file'], 
         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    def responder(plans):
        print(f'Responder called with {len(plans)} plans')
        # Cancel on first responder call
        cancelled = task_executor.cancel_task(task.task_id)
        print(f'Cancellation requested: {cancelled}')
        return 'cancel'
    
    try:
        result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    except Exception as e:
        print(f'Exception: {e}')
        import traceback
        traceback.print_exc()
    
    print(f'Final task status: {task.status.value}')
    print(f'Task is terminal: {task.is_terminal()}')
    print(f'Completed steps: {len(task.completed_step_ids)}')
    print(f'Failed steps: {len(task.failed_step_ids)}')
    
    success = task.status == TaskStatus.CANCELLED and task.is_terminal()
    print(f'Cancellation at planning: {"PASS" if success else "FAIL"}')
    return success


def test_cancellation_before_first_tool():
    """Test cancellation before first tool execution."""
    print("\n=== Testing cancellation before first tool ===")
    
    workspace = tempfile.mkdtemp(prefix='phase13_cancel_before_tool_')
    os.environ['HERMES_WORKSPACE'] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = TestPlanner(test_type='filesystem', cancel_at_step=2)  # Cancel after first plan
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
    
    goal = "Write and read a test file"
    available_tools = [
        {'name': 'fs.write', 'description': 'Write file', 'selection_phrases': ['write file'], 
         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['path', 'content']}},
        {'name': 'fs.read', 'description': 'Read file', 'selection_phrases': ['read file'], 
         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    call_count = 0
    def responder(plans):
        nonlocal call_count
        call_count += 1
        print(f'Responder call #{call_count}')
        # Cancel on second responder call (after first tool would execute)
        if call_count >= 2:
            cancelled = task_executor.cancel_task(task.task_id)
            print(f'Cancellation requested: {cancelled}')
            return 'cancel'
        return 'continue'
    
    try:
        result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    except Exception as e:
        print(f'Exception: {e}')
        import traceback
        traceback.print_exc()
    
    print(f'Final task status: {task.status.value}')
    print(f'Task is terminal: {task.is_terminal()}')
    print(f'Completed steps: {len(task.completed_step_ids)}')
    print(f'Failed steps: {len(task.failed_step_ids)}')
    
    success = task.status == TaskStatus.CANCELLED and task.is_terminal()
    print(f'Cancellation before first tool: {"PASS" if success else "FAIL"}')
    return success


def test_cancellation_during_tool_execution():
    """Test cancellation during tool execution (simulated)."""
    print("\n=== Testing cancellation during tool execution ===")
    
    workspace = tempfile.mkdtemp(prefix='phase13_cancel_during_tool_')
    os.environ['HERMES_WORKSPACE'] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    registry.register(TerminalRunTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    # Use a planner that takes time to simulate long tool execution
    planner = TestPlanner(test_type='terminal', cancel_at_step=2)  # Cancel during terminal sleep
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
    
    goal = "Run a command and read result"
    available_tools = [
        {'name': 'terminal.run', 'description': 'Run terminal command', 'selection_phrases': ['run command'], 
         'parameters': {'type': 'object', 'properties': {'cmd': {'type': 'array'}, 'timeout': {'type': 'integer'}}, 'required': ['cmd']}},
        {'name': 'fs.write', 'description': 'Write file', 'selection_phrases': ['write file'], 
         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['path', 'content']}},
    ]
    
    task = task_executor.create_task(user_goal=goal, available_tools=available_tools)
    
    def responder(plans):
        print(f'Responder called with {len(plans)} plans')
        # Cancel during the terminal execution (second planner call)
        cancelled = task_executor.cancel_task(task.task_id)
        print(f'Cancellation requested: {cancelled}')
        return 'cancel'
    
    try:
        result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
    except Exception as e:
        print(f'Exception: {e}')
        import traceback
        traceback.print_exc()
    
    print(f'Final task status: {task.status.value}')
    print(f'Task is terminal: {task.is_terminal()}')
    print(f'Completed steps: {len(task.completed_step_ids)}')
    print(f'Failed steps: {len(task.failed_step_ids)}')
    
    success = task.status == TaskStatus.CANCELLED and task.is_terminal()
    print(f'Cancellation during tool execution: {"PASS" if success else "FAIL"}')
    return success


def test_cancellation_terminal_state():
    """Test that cancelled tasks are terminal and don't continue."""
    print("\n=== Testing cancelled task terminal state ===")
    
    task = Task(
        task_id="test_terminal_check",
        user_goal="Test terminal state",
        max_steps=10,
        max_retries_per_step=2,
        max_replans=2,
    )
    
    print(f"Initial status: {task.status.value}")
    print(f"Is terminal: {task.is_terminal()}")
    
    # Cancel the task
    task.cancel()
    
    print(f"After cancel status: {task.status.value}")
    print(f"Is terminal: {task.is_terminal()}")
    
    # Verify it's terminal
    is_terminal = task.is_terminal()
    status_is_cancelled = task.status == TaskStatus.CANCELLED
    
    print(f"Task is terminal: {is_terminal}")
    print(f"Task status is CANCELLED: {status_is_cancelled}")
    
    success = is_terminal and status_is_cancelled
    print(f'Cancelled task terminal state: {"PASS" if success else "FAIL"}')
    return success


def main():
    """Run all cancellation validation tests."""
    print("Starting Phase 13 Cancellation Validation Tests")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(test_cancellation_at_planning())
    results.append(test_cancellation_before_first_tool())
    results.append(test_cancellation_during_tool_execution())
    results.append(test_cancellation_terminal_state())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("\n" + "=" * 50)
    print(f"Cancellation Validation Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✅ All cancellation validation tests PASSED")
        return 0
    else:
        print("❌ Some cancellation validation tests FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())