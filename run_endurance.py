#!/usr/bin/env python3
"""
Phase 13 Endurance Test Runner
Runs sequential tasks and captures resource metrics at checkpoints.
"""

import os
import sys
import json
import time
import tempfile
import subprocess
import threading
import glob
from pathlib import Path

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

# Global metrics storage
metrics_history = []

def measure_resources():
    """Capture current resource metrics."""
    import psutil
    proc = psutil.Process()
    
    metrics = {}
    mem = proc.memory_info()
    metrics['python_memory_mb'] = mem.rss / (1024 * 1024)
    metrics['child_process_count'] = len(proc.children(recursive=True))
    try:
        metrics['open_handles'] = proc.num_handles()
    except AttributeError:
        metrics['open_handles'] = proc.num_fds()
    
    browser_procs = [p for p in psutil.process_iter(['name']) 
                     if 'chrome' in p.info['name'].lower() or 'chromium' in p.info['name'].lower()]
    metrics['browser_processes'] = len(browser_procs)
    
    temp_dir = tempfile.gettempdir()
    phase13_temps = glob.glob(os.path.join(temp_dir, 'phase13*'))
    metrics['phase13_temp_dirs'] = len([d for d in phase13_temps if os.path.isdir(d)])
    metrics['phase13_temp_files'] = len([f for f in phase13_temps if os.path.isfile(f)])
    
    metrics['thread_count'] = threading.active_count()
    
    monitoring_db = os.path.join(temp_dir, 'hermes_monitoring.db')
    if os.path.exists(monitoring_db):
        metrics['monitoring_db_mb'] = os.path.getsize(monitoring_db) / (1024 * 1024)
    else:
        metrics['monitoring_db_mb'] = 0
    
    checkpoint_dir = os.path.join(temp_dir, 'hermes_checkpoints')
    if os.path.exists(checkpoint_dir):
        ckpt_files = glob.glob(os.path.join(checkpoint_dir, '*'))
        metrics['checkpoint_count'] = len(ckpt_files)
    else:
        metrics['checkpoint_count'] = 0
    
    return metrics


def run_workflow(workflow_type, task_id, workspace):
    """Run a single workflow of the specified type - direct execution without planner."""
    os.environ["HERMES_WORKSPACE"] = workspace
    
    if workflow_type == 'filesystem':
        # Direct execution: write -> read -> verify
        fs_write = FSWriteTool()
        fs_read = FSReadTool()
        
        try:
            # Write
            fs_write.execute(path="output/result.txt", content="Phase 13 filesystem test")
            
            # Read
            content = fs_read.execute(path="output/result.txt")
            
            # Verify
            if "Phase 13 filesystem test" not in content:
                return {"success": False, "status": "verify_failed", "error": f"Content mismatch: {content}"}
            
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'terminal':
        # Direct execution: run python command
        terminal = TerminalRunTool()
        
        try:
            result = terminal.execute(cmd=["python", "-c", "print(2+2)"])
            stdout = result.get("stdout", "")
            if "4" not in stdout:
                return {"success": False, "status": "verify_failed", "error": f"Expected 4 in output, got: {stdout}"}
            
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'calculator':
        # Direct execution: calculate -> write
        calc = CalculatorTool()
        fs_write = FSWriteTool()
        
        try:
            result = calc.execute(expression="125 * 4")
            # Calculator returns int directly, not a dict
            calc_result = str(result)
            
            fs_write.execute(path="output/calc_result.txt", content=calc_result)
            
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    elif workflow_type == 'multi-tool':
        # Direct execution: calculate -> write -> read -> verify
        calc = CalculatorTool()
        fs_write = FSWriteTool()
        fs_read = FSReadTool()
        
        try:
            result = calc.execute(expression="25 * 4")
            # Calculator returns int directly, not a dict
            calc_result = str(result)
            
            fs_write.execute(path="output/multi.txt", content=calc_result)
            
            content = fs_read.execute(path="output/multi.txt")
            if "100" not in content:
                return {"success": False, "status": "verify_failed", "error": f"Expected 100, got: {content}"}
            
            return {"success": True, "workflow": workflow_type, "task_id": task_id, "status": "COMPLETED"}
        except Exception as e:
            return {"success": False, "status": "workflow_failed", "error": str(e)}
    
    else:
        return {"success": False, "status": "unknown_workflow", "error": f"Unknown workflow type: {workflow_type}"}


def run_endurance_test(num_tasks=100, checkpoint_interval=25):
    """Run endurance test with periodic resource measurement."""
    workflows = [
        'filesystem',
        'terminal', 
        'calculator',
        'multi-tool',
    ]
    
    for i in range(num_tasks):
        workflow_type = workflows[i % len(workflows)]
        task_id = f"endurance_{i:04d}"
        
        # Create isolated workspace
        workspace = os.path.join(tempfile.gettempdir(), f"phase13_{task_id}")
        os.makedirs(workspace, exist_ok=True)
        
        start_time = time.time()
        result = run_workflow(workflow_type, task_id, workspace)
        duration = time.time() - start_time
        
        print(f"Task {i+1}/{num_tasks} ({workflow_type}): {result.get('status', 'unknown')} ({duration:.2f}s)")
        
        # Capture metrics at checkpoint intervals
        if (i + 1) % checkpoint_interval == 0:
            metrics = measure_resources()
            metrics['task_number'] = i + 1
            metrics['workflow'] = workflow_type
            metrics['duration'] = duration
            metrics_history.append(metrics)
            
            print(f"\n=== CHECKPOINT {i+1} ===")
            for k, v in metrics.items():
                print(f"  {k}: {v}")
    
    return metrics_history


if __name__ == "__main__":
    print("Starting Phase 13 Long-Run Endurance Test (100 tasks)")
    history = run_endurance_test(100, 25)
    
    # Save results
    with open(os.path.join(tempfile.gettempdir(), 'phase13_endurance_history.json'), 'w') as f:
        json.dump(history, f, indent=2)
    
    print("\nEndurance test complete. Results saved.")