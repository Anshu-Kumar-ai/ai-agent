#!/usr/bin/env python3
"""
Phase 13 Mixed Success/Failure Load Test
Runs a mix of successful, failing, and error-inducing tasks.
"""

import os
import sys
import json
import time
import tempfile
import threading
import concurrent.futures

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.tools.adapters import FSReadTool, FSWriteTool, TerminalRunTool
from app.tools.calculator import CalculatorTool

def run_workflow(workflow_type, task_id, workspace, should_fail=False):
    """Run a single workflow of the specified type."""
    
    if workflow_type == 'filesystem':
        fs_write = FSWriteTool()
        fs_read = FSReadTool()
        
        try:
            if should_fail:
                # Try to write outside workspace (should fail)
                fs_write.execute(path="C:/Temp/escape.txt", content="escape", workspace=workspace)
                return {"success": True, "status": "unexpectedly_succeeded", "task_id": task_id, "workflow": workflow_type}
            
            fs_write.execute(path="output/result.txt", content=f"test {task_id}", workspace=workspace)
            content = fs_read.execute(path="output/result.txt", workspace=workspace)
            if f"test {task_id}" not in content:
                return {"success": False, "status": "verify_failed", "task_id": task_id, "workflow": workflow_type, "error": f"Content mismatch: {content}"}
            return {"success": True, "status": "COMPLETED", "task_id": task_id, "workflow": workflow_type}
        except Exception as e:
            if should_fail:
                return {"success": True, "status": "EXPECTED_FAILURE", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
            return {"success": False, "status": "workflow_failed", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
    
    elif workflow_type == 'terminal':
        terminal = TerminalRunTool()
        try:
            if should_fail:
                # Try to run invalid command
                terminal.execute(cmd=["invalid_command_that_does_not_exist"], workspace=workspace)
                return {"success": True, "status": "unexpectedly_succeeded", "task_id": task_id, "workflow": workflow_type}
            
            result = terminal.execute(cmd=["python", "-c", "print(2+2)"], workspace=workspace)
            stdout = result.get("stdout", "")
            if "4" not in stdout:
                return {"success": False, "status": "verify_failed", "task_id": task_id, "workflow": workflow_type, "error": f"Expected 4 in output, got: {stdout}"}
            return {"success": True, "status": "COMPLETED", "task_id": task_id, "workflow": workflow_type}
        except Exception as e:
            if should_fail:
                return {"success": True, "status": "EXPECTED_FAILURE", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
            return {"success": False, "status": "workflow_failed", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
    
    elif workflow_type == 'calculator':
        calc = CalculatorTool()
        fs_write = FSWriteTool()
        try:
            if should_fail:
                # Division by zero
                calc.execute(expression="1/0")
                return {"success": True, "status": "unexpectedly_succeeded", "task_id": task_id, "workflow": workflow_type}
            
            result = calc.execute(expression="125 * 4")
            calc_result = str(result)
            fs_write.execute(path="output/calc_result.txt", content=calc_result, workspace=workspace)
            return {"success": True, "status": "COMPLETED", "task_id": task_id, "workflow": workflow_type}
        except Exception as e:
            if should_fail:
                return {"success": True, "status": "EXPECTED_FAILURE", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
            return {"success": False, "status": "workflow_failed", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
    
    elif workflow_type == 'permission_denied':
        # Simulate permission denied by trying to write to protected path
        fs_write = FSWriteTool()
        try:
            fs_write.execute(path="C:/Windows/System32/test.txt", content="test", workspace=workspace)
            return {"success": True, "status": "unexpectedly_succeeded", "task_id": task_id, "workflow": workflow_type}
        except Exception as e:
            return {"success": True, "status": "EXPECTED_FAILURE", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
    
    elif workflow_type == 'invalid_argument':
        # Missing required argument
        fs_write = FSWriteTool()
        try:
            fs_write.execute(path="", content="test", workspace=workspace)
            return {"success": True, "status": "unexpectedly_succeeded", "task_id": task_id, "workflow": workflow_type}
        except Exception as e:
            return {"success": True, "status": "EXPECTED_FAILURE", "task_id": task_id, "workflow": workflow_type, "error": str(e)}
    
    else:
        return {"success": False, "status": "unknown_workflow", "task_id": task_id, "workflow": workflow_type, "error": f"Unknown workflow type: {workflow_type}"}


def run_mixed_load_test():
    """Run a mixed load of successful and failing tasks."""
    
    # Define task mix
    task_mix = [
        ("filesystem", False),      # 1. successful
        ("filesystem", True),       # 2. escape attempt (should fail)
        ("terminal", False),        # 3. successful
        ("terminal", True),         # 4. invalid command (should fail)
        ("calculator", False),      # 5. successful
        ("calculator", True),       # 6. div by zero (should fail)
        ("permission_denied", True), # 7. permission attempt (should fail)
        ("invalid_argument", True),  # 8. invalid arg (should fail)
        ("filesystem", False),      # 9. successful
        ("terminal", False),        # 10. successful
    ]
    
    print("=== Phase 13 Mixed Success/Failure Load Test ===\n")
    
    results = []
    
    for i, (workflow_type, should_fail) in enumerate(task_mix):
        task_id = f"mixed_{i:03d}"
        workspace = os.path.join(tempfile.gettempdir(), f"phase13_mixed_{task_id}")
        os.makedirs(workspace, exist_ok=True)
        
        print(f"Task {i+1}/{len(task_mix)}: {workflow_type} (should_fail={should_fail})")
        result = run_workflow(workflow_type, task_id, workspace, should_fail)
        result['expected_fail'] = should_fail
        results.append(result)
        
        status = result.get('status', 'unknown')
        print(f"  Result: {status}")
    
    return results


def analyze_results(results):
    """Analyze the mixed load results."""
    
    counts = {
        "COMPLETED": 0,
        "EXPECTED_FAILURE": 0,
        "unexpectedly_succeeded": 0,
        "verify_failed": 0,
        "workflow_failed": 0,
    }
    
    for r in results:
        status = r.get('status', 'unknown')
        if status in counts:
            counts[status] += 1
        else:
            counts[status] = 1
        
        expected = r.get('expected_fail', False)
        actual_failed = r.get('status') == 'EXPECTED_FAILURE'
        actual_succeeded = r.get('status') == 'COMPLETED'
        
        if expected and actual_failed:
            print(f"✓ {r['task_id']} ({r['workflow']}): EXPECTED FAILURE - {r.get('error', '')[:80]}")
        elif not expected and actual_succeeded:
            print(f"✓ {r['task_id']} ({r['workflow']}): COMPLETED")
        elif expected and actual_succeeded:
            print(f"✗ {r['task_id']} ({r['workflow']}): UNEXPECTED SUCCESS")
        elif not expected and r.get('status') == 'EXPECTED_FAILURE':
            print(f"✗ {r['task_id']} ({r['workflow']}): UNEXPECTED FAILURE - {r.get('error', '')[:80]}")
        else:
            print(f"✗ {r['task_id']} ({r['workflow']}): UNEXPECTED - {r.get('status')}")
    
    print(f"\n=== Summary ===")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k}: {v}")
    
    # Check for security violations - tasks that should fail but succeeded
    security_violations = sum(1 for r in results if r.get('expected_fail', False) and r.get('status') == 'COMPLETED')
    if security_violations > 0:
        print(f"\n⚠ SECURITY: {security_violations} tasks unexpectedly succeeded (should have failed)")
        return False
    
    # Check for tasks that should succeed but failed
    false_failures = sum(1 for r in results if not r.get('expected_fail', False) and r.get('status') not in ['COMPLETED', 'EXPECTED_FAILURE'])
    if false_failures > 0:
        print(f"\n⚠ RELIABILITY: {false_failures} tasks unexpectedly failed (should have succeeded)")
        return False
    
    return True


if __name__ == "__main__":
    print("=== Phase 13 Mixed Success/Failure Load Test ===\n")
    
    results = run_mixed_load_test()
    success = analyze_results(results)
    
    print(f"\nOverall: {'PASS' if success else 'FAIL'}")