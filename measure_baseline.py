#!/usr/bin/env python3
"""
Baseline resource measurement script for Phase 13 endurance testing.
Captures all metrics before and after representative tasks.
"""

import os
import sys
import psutil
import tempfile
import glob
import threading
import time

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

def measure_baseline():
    """Capture all baseline metrics."""
    proc = psutil.Process()
    
    metrics = {}
    
    # Python process memory
    mem = proc.memory_info()
    metrics['python_memory_mb'] = mem.rss / (1024 * 1024)
    metrics['python_memory_vms_mb'] = mem.vms / (1024 * 1024)
    
    # Child process count
    children = proc.children(recursive=True)
    metrics['child_process_count'] = len(children)
    
    # Open handles (Windows)
    try:
        metrics['open_handles'] = proc.num_handles()
    except AttributeError:
        metrics['open_handles'] = proc.num_fds()
    
    # Browser processes
    browser_procs = [p for p in psutil.process_iter(['name']) 
                     if 'chrome' in p.info['name'].lower() or 'chromium' in p.info['name'].lower()]
    metrics['browser_processes'] = len(browser_procs)
    
    # Temporary directories/files
    temp_dir = tempfile.gettempdir()
    phase13_temps = glob.glob(os.path.join(temp_dir, 'phase13*'))
    metrics['phase13_temp_dirs'] = len([d for d in phase13_temps if os.path.isdir(d)])
    metrics['phase13_temp_files'] = len([f for f in phase13_temps if os.path.isfile(f)])
    
    # Thread count
    metrics['thread_count'] = threading.active_count()
    
    # Try to get task/state counts from agent internals
    try:
        from app.core.task_executor import TaskExecutor
        metrics['task_executor_exists'] = True
    except ImportError:
        metrics['task_executor_exists'] = False
    
    # Monitoring DB size (if exists)
    monitoring_db = os.path.join(tempfile.gettempdir(), 'hermes_monitoring.db')
    if os.path.exists(monitoring_db):
        metrics['monitoring_db_mb'] = os.path.getsize(monitoring_db) / (1024 * 1024)
    else:
        metrics['monitoring_db_mb'] = 0
    
    # Checkpoint directory
    checkpoint_dir = os.path.join(tempfile.gettempdir(), 'hermes_checkpoints')
    if os.path.exists(checkpoint_dir):
        ckpt_files = glob.glob(os.path.join(checkpoint_dir, '*'))
        metrics['checkpoint_count'] = len(ckpt_files)
    else:
        metrics['checkpoint_count'] = 0
    
    return metrics


def print_metrics(label, metrics):
    """Print metrics in a readable format."""
    print(f"\n=== {label} ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return metrics


if __name__ == "__main__":
    baseline = measure_baseline()
    print_metrics("BASELINE RESOURCE PROFILE", baseline)
    
    # Save to file for comparison
    import json
    with open(os.path.join(tempfile.gettempdir(), 'phase13_baseline.json'), 'w') as f:
        json.dump(baseline, f, indent=2)
    
    print(f"\nBaseline saved to {tempfile.gettempdir()}/phase13_baseline.json")