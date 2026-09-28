import sys
sys.path.insert(0, '.')

from app.core.evaluator import Evaluator

evaluator = Evaluator()

# Simulate the actual scenario
user_request = "Fetch https://httpbin.org/get"
plan = {"action": "respond", "tool_name": None, "arguments": {}, "reason": "A tool result is available for the final response."}
observations = [{
    "tool_name": "http.fetch",
    "result": "Fetched: https://httpbin.org/get\nStatus: 200\nContent-Type: application/json\nSize: 276 chars\n\n{\n  \"args\": {}, \n  \"headers\": {\n    \"Accept-Encoding\": \"identity\", \n    \"Host\": \"httpbin.org\", \n    \"User-Agent\": \"Python-urllib/3.11\", \n    \"X-Amzn-Trace-Id\": \"Root=1-6ab05da6-3d8cfccf0f9720e568caf26b\"\n  }, \n  \"origin\": \"47.247.118.30\", \n  \"url\": \"https://httpbin.org/get\"\n}"
}]
response = """Fetched: https://httpbin.org/get
Status: 200
Content-Type: application/json
Size: 276 chars

{
  "args": {}, 
  "headers": {
    "Accept-Encoding": "identity", 
    "Host": "httpbin.org", 
    "User-Agent": "Python-urllib/3.11", 
    "X-Amzn-Trace-Id": "Root=1-6ab05da6-3d8cfccf0f9720e568caf26b"
  }, 
  "origin": "47.247.118.30", 
  "url": "https://httpbin.org/get"
}"""

eval_result = evaluator.evaluate(user_request, plan, observations, response)
print(f"Score: {eval_result.score:.2f}")
print(f"Criteria met: {eval_result.criteria_met}")
print(f"Criteria not met: {eval_result.criteria_not_met}")
print(f"Feedback: {eval_result.feedback}")
print(f"Relevance score: {eval_result.details.get('relevance_score')}")
print(f"Hallucination score: {eval_result.details.get('hallucination_score')}")
print(f"Completeness score: {eval_result.details.get('completeness_score')}")
print(f"Actionability score: {eval_result.details.get('actionability_score')}")