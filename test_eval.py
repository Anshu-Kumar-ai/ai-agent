import sys
sys.path.insert(0, '.')

from app.core.evaluator import Evaluator

evaluator = Evaluator()

# Test the list case
user_request = "List files in current directory"
response = """[{'name': '.env', 'path': 'C:\\\\Users\\\\anshu\\\\Agent\\\\AI-Agent\\\\.env', 'is_file': True, 'is_dir': False, 'size': 267}, {'name': '.gitignore', 'path': 'C:\\\\Users\\\\anshu\\\\Agent\\\\AI-Agent\\\\.gitignore', 'is_file': True, 'is_dir': False, 'size': 33}, {'name': '.pytest_cache', 'path': 'C:\\\\Users\\\\anshu\\\\Agent\\\\AI-Agent\\\\.pytest_cache', 'is_file': False, 'is_dir': True, 'size': 0}]"""
observations = [{
    "tool_name": "fs.list",
    "result": [{"name": ".env", "path": "C:\\Users\\anshu\\Agent\\AI-Agent\\.env", "is_file": True, "is_dir": False, "size": 267}]
}]
plan = {"action": "respond", "tool_name": None, "arguments": {}, "reason": "A tool result is available for the final response."}

eval_result = evaluator.evaluate(user_request, plan, observations, response)
print(f"Score: {eval_result.score:.2f}")
print(f"Criteria met: {eval_result.criteria_met}")
print(f"Criteria not met: {eval_result.criteria_not_met}")
print(f"Feedback: {eval_result.feedback}")

# Test time case
user_request2 = "What time is it?"
response2 = "2026-09-21T02:38:37.172935+05:30"
observations2 = [{"tool_name": "time", "result": "2026-09-21T02:38:37.172935+05:30"}]
plan2 = {"action": "respond", "tool_name": None, "arguments": {}, "reason": "A tool result is available for the final response."}

eval_result2 = evaluator.evaluate(user_request2, plan2, observations2, response2)
print(f"\nTime Score: {eval_result2.score:.2f}")
print(f"Criteria met: {eval_result2.criteria_met}")
print(f"Criteria not met: {eval_result2.criteria_not_met}")
print(f"Feedback: {eval_result2.feedback}")