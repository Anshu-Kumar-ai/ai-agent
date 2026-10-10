#!/usr/bin/env python3
"""
Phase 13 Concurrent Task Load Test
Runs multiple tasks concurrently and verifies isolation.
"""

import os
import sys
import json
import time
import tempfile
import threading
import concurrent.futures
import glob
import psutil

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.tools.adapters import FSReadTool, FSWriteTool, TerminalRunTool
from app.tools.calculator import CalculatorTool

def run_workflow(workflow_type, task_id, workspace):
    """Run a single workflow of the specified type - direct execution without planner."""
    
    if workflow_type == 'filesystem':
        fs_write = FSWriteTool()
        fs_read = FSReadTool()
        
        try:
            fs_write.execute(path="output/result.txt", content=f"Phase 13 concurrent test {task_id}", workspace=workspace)
            content = fs_read.execute(path="output/result.txt", workspace=workspace)
            if f"Phase 13 concurrent test {task_id}" not in content:
                return {"success": False, "status": "verify_failed", "error": f"Content mismatch: {content}"}
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'terminal':
        terminal = TerminalRunTool()
        try:
            result = terminal.execute(cmd=["python", "-c", "print(2+2)"], workspace=workspace)
            stdout = result.get("stdout", "")
            if "4" not in stdout:
                return {"success": False, "status": "verify_failed", "error": f"Expected 4 in output, got: {stdout}"}
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'calculator':
        calc = CalculatorTool()
        fs_write = FSWriteTool()
        try:
            result = calc.execute(expression="125 * 4")
            calc_result = str(result)
            fs_write.execute(path="output/calc_result.txt", content=calc_result, workspace=workspace)
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'multi-tool':
        calc = CalculatorTool()
        fs_write = FSWriteTool()
        fs_read = FSReadTool()
        try:
            result = calc.execute(expression="25 * 4")
            calc_result = str(result)
            fs_write.execute(path="output/multi.txt", content=calc_result, workspace=workspace)
            content = fs_read.execute(path="output/multi.txt", workspace=workspace)
            if "100" not in content:
                return {"success": False, "status": "verify_failed", "error": f"Expected 100, got: {content}"}
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    else:
        return {"success": False, "status": "unknown_workflow", "error": f"Unknown workflow type: {workflow_type}"}


def run_concurrent_test(num_concurrent, workflows_per_type=1):
    """Run concurrent tasks."""
    workflows = ['filesystem', 'terminal', 'calculator', 'multi-tool']
    tasks = []
    
    for _ in range(workflows_per_type):
        for w in workflows:
            tasks.append(w)
    
    # Limit to num_concurrent
    tasks = tasks[:num_concurrent]
    
    print(f"Starting {num_concurrent} concurrent tasks...")
    
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        for i, workflow_type in enumerate(tasks):
            task_id = f"concurrent_{i:03d}"
            workspace = os.path.join(tempfile.gettempdir(), f"phase13_concurrent_{task_id}")
            os.makedirs(workspace, exist_ok=True)
            
            future = executor.submit(run_workflow, workflow_type, task_id, workspace)
            futures.append((task_id, workflow_type, future))
        
        results = []
        for task_id, workflow_type, future in futures:
            result = future.result()
            result['task_id'] = task_id
            result['workflow'] = workflow_type
            results.append(result)
            status = result.get('status', 'unknown')
            print(f"  {task_id} ({workflow_type}): {status}")
    
    return results


def verify_isolation(results):
    """Verify no cross-task contamination."""
    # Check that all tasks succeeded
    failed = [r for r in results if not r.get('success', False)]
    if failed:
        print(f"FAILED: {len(failed)} tasks failed")
        for f in failed:
            print(f"  {f.get('task_id')} ({f.get('workflow')}): {f.get('status')} - {f.get('error')}")
        return False
    
    print(f"All {len(results)} concurrent tasks COMPLETED successfully")
    return True


if __name__ == "__main__":
    print("=== Phase 13 Concurrent Task Load Test ===\n")
    
    for num in [10, 25, 50]:
        print(f"\n--- Testing {num} concurrent tasks ---")
        start = time.time()
        results = run_concurrent_test(num, workflows_per_type=num//4 + 1)
        elapsed = time.time() - start
        
        success = verify_isolation(results)
        print(f"Concurrency {num}: {'PASS' if success else 'FAIL'} ({elapsed:.2f}s)")
        
        if not success:
            break
    
    print("\nConcurrent task load test complete.")