#!/usr/bin/env python3
"""Simple cancellation test for TaskExecutor."""

import sys
import os
import tempfile

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.core.state.task import Task, TaskStatus
from app.core.task_executor import TaskExecutor
from app.tools.registry import ToolRegistry
from app.tools.executor import ToolExecutor
from app.tools.adapters import FSReadTool, FSWriteTool
from app.core.permissions import PermissionManager, ApprovalMode
from app.memory.enhanced import EnhancedMemory
from app.core.planner import Planner, Plan
from app.core.evaluator import Evaluator
from app.core.state.task import PlanVersion


class SimplePlanner(Planner):
    """Simple planner that just writes a file."""
    
    def __init__(self):
        self.call_count = 0
        
    def plan(self, message, available_tools, observations=None, context=None):
        self.call_count += 1
        print(f'Planner call #{self.call_count}')
        
        if self.call_count == 1:
            return Plan(
                action='use_tool',
                tool_name='fs.write',
                arguments={'path': 'test.txt', 'content': 'hello'},
                reason='Write test file'
            )
        elif self.call_count == 2:
            return Plan(
                action='use_tool',
                tool_name='fs.read',
                arguments={'path': 'test.txt'},
                reason='Read test file'
            )
        else:
            return Plan(
                action='respond',
                response='Task completed',
                reason='All done'
            )


def test_simple_cancellation():
    """Test simple cancellation scenario."""
    print("=== Testing Simple Cancellation ===")
    
    workspace = tempfile.mkdtemp(prefix='simple_cancel_')
    os.environ['HERMES_WORKSPACE'] = workspace
    
    registry = ToolRegistry()
    registry.register(FSWriteTool())
    registry.register(FSReadTool())
    
    perm_manager = PermissionManager(workspace_root=workspace, approval_mode=ApprovalMode.FULL_AUTO)
    tool_executor = ToolExecutor(registry)
    planner = SimplePlanner()
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
    print(f"Task created: {task.task_id}, initial status: {task.status.value}")
    
    def responder(plans):
        print(f'Responder called with {len(plans)} plans')
        # Cancel immediately on first call
        print("Cancelling task...")
        cancelled = task_executor.cancel_task(task.task_id)
        print(f"Cancel returned: {cancelled}")
        return 'cancel'
    
    try:
        result_task = task_executor.execute_task(task=task, available_tools=available_tools, responder=responder)
        print(f"Execution completed. Final task status: {task.status.value}")
        print(f"Task is terminal: {task.is_terminal()}")
        print(f"Completed steps: {len(task.completed_step_ids)}")
        print(f"Failed steps: {len(task.failed_step_ids)}")
        
        success = task.status == TaskStatus.CANCELLED and task.is_terminal()
        print(f"Simple cancellation test: {'PASS' if success else 'FAIL'}")
        return success
    except Exception as e:
        print(f"Exception during execution: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if test_simple_cancellation():
        print("\n✅ Simple cancellation test PASSED")
    else:
        print("\n❌ Simple cancellation test FAILED")
        sys.exit(1)