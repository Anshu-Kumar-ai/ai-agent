#!/usr/bin/env python3
"""
Phase 13 Timeout Validation Test
Tests short/normal/repeated/multi-tool timeouts.
"""

import os
import sys
import tempfile

sys.path.insert(0, "C:/Users/anshu/Agent/AI-Agent")

from app.tools.adapters import TerminalRunTool

def test_timeout(workspace, timeout_seconds, cmd, description):
    """Test a command with a specific timeout."""
    terminal = TerminalRunTool()
    
    try:
        result = terminal.execute(cmd=cmd, workspace=workspace, timeout=timeout_seconds)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)
        
        return {
            "success": True,
            "status": "completed",
            "exit_code": exit_code,
            "stdout": stdout[:100],
            "stderr": stderr[:100],
            "timed_out": False
        }
    except TimeoutError as e:
        return {
            "success": True,
            "status": "timeout",
            "timed_out": True,
            "error": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "error": str(e)
        }


def run_timeout_tests():
    """Run timeout validation tests."""
    
    workspace = tempfile.mkdtemp(prefix="phase13_timeout_")
    os.environ["HERMES_WORKSPACE"] = workspace
    
    print("=== Phase 13 Timeout Validation Test ===\n")
    
    tests = [
        # (timeout, cmd, description, expected)
        (1, ["python", "-c", "import time; time.sleep(5); print('done')"], "Short timeout (1s) on long sleep (5s)", "timeout"),
        (10, ["python", "-c", "import time; time.sleep(2); print('done')"], "Normal timeout (10s) on short sleep (2s)", "completed"),
        (2, ["python", "-c", "import time; time.sleep(5); print('done')"], "Repeated timeout test 1", "timeout"),
        (2, ["python", "-c", "import time; time.sleep(5); print('done')"], "Repeated timeout test 2", "timeout"),
        (5, ["python", "-c", "import time; time.sleep(1); print('step1'); time.sleep(1); print('step2')"], "Multi-step with timeout", "completed"),
    ]
    
    results = []
    
    for timeout, cmd, description, expected in tests:
        print(f"Testing: {description}")
        print(f"  Timeout: {timeout}s, Command: {' '.join(cmd)}")
        
        result = test_timeout(workspace, timeout, cmd, description)
        results.append(result)
        
        status = result.get('status', 'unknown')
        timed_out = result.get('timed_out', False)
        
        if expected == "timeout" and timed_out:
            print(f"  ✓ CORRECTLY TIMED OUT")
        elif expected == "completed" and status == "completed" and not timed_out:
            print(f"  ✓ COMPLETED NORMALLY")
        else:
            print(f"  ✗ UNEXPECTED: status={status}, timed_out={timed_out}, expected={expected}")
        
        if 'error' in result:
            print(f"    Error: {result['error'][:100]}")
        
        print()
    
    # Summary
    correct = sum(1 for r, (_, _, _, expected) in zip(results, tests) 
                  if (expected == "timeout" and r.get('timed_out', False)) or 
                     (expected == "completed" and r.get('status') == "completed" and not r.get('timed_out', False)))
    
    print(f"=== Summary ===")
    print(f"Correct: {correct}/{len(tests)}")
    print(f"Overall: {'PASS' if correct == len(tests) else 'FAIL'}")
    
    return correct == len(tests)


if __name__ == "__main__":
    success = run_timeout_tests()
    sys.exit(0 if success else 1)