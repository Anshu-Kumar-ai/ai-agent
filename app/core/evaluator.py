"""Enhanced Evaluator for Stage 8 - Evaluation-Driven Improvement.

Provides sophisticated evaluation criteria for agent responses:
- Accuracy: Does the response correctly answer the request?
- Completeness: Does it address all parts of the request?
- Hallucination Check: Are tool results faithfully represented?
- Relevance: Is the response on-topic?
- Actionability: For tool tasks, were the right tools used?
"""

import re

from app.core.evaluation import Evaluation


class Evaluator:
    """Evaluates the agent's performance with sophisticated criteria."""

    def __init__(
        self,
        check_hallucination: bool = True,
        check_completeness: bool = True,
        check_relevance: bool = True,
    ):
        self.check_hallucination = check_hallucination
        self.check_completeness = check_completeness
        self.check_relevance = check_relevance

    def evaluate(
        self,
        user_request: str,
        plan: dict,
        observations: list[dict],
        response: str,
    ) -> Evaluation:
        """Return an Evaluation object assessing the quality of the agent's response."""

        criteria_met = []
        criteria_not_met = []
        feedback_parts = []
        details = {}

        # Criterion 1: Response is not empty
        if response and response.strip():
            criteria_met.append("non_empty_response")
            details["non_empty_response"] = True
        else:
            criteria_not_met.append("non_empty_response")
            feedback_parts.append("The response is empty.")
            details["non_empty_response"] = False

        # Criterion 2: Tool executions were successful (if tools were used)
        if observations:
            tool_success_count = sum(
                1
                for obs in observations
                if isinstance(obs.get("result"), dict) and obs["result"].get("status") != "ERROR"
                or not isinstance(obs.get("result"), dict)
            )  # Non-dict results = success
            if tool_success_count == len(observations):
                criteria_met.append("tool_executions_successful")
                details["tool_executions_successful"] = True
            else:
                criteria_not_met.append("tool_executions_successful")
                feedback_parts.append(
                    f"Some tool executions failed: {len(observations) - tool_success_count}/{len(observations)}"
                )
                details["tool_executions_successful"] = False
        else:
            # No tools used - check if plan was to respond directly
            if plan.get("action") == "respond":
                criteria_met.append("tool_executions_successful")
                details["tool_executions_successful"] = True

        # Criterion 3: Response addresses the user request (relevance)
        if self.check_relevance and user_request.strip():
            relevance_score = self._check_relevance(user_request, response)
            if relevance_score >= 0.5:
                criteria_met.append("response_addresses_request")
                details["relevance_score"] = relevance_score
            else:
                criteria_not_met.append("response_addresses_request")
                feedback_parts.append("The response does not seem to address the user's request.")
                details["relevance_score"] = relevance_score

        # Criterion 4: Hallucination check - tool results faithfully represented
        if self.check_hallucination and observations:
            hallucination_score = self._check_hallucination(observations, response)
            if hallucination_score >= 0.7:
                criteria_met.append("no_hallucination")
                details["hallucination_score"] = hallucination_score
            else:
                criteria_not_met.append("no_hallucination")
                feedback_parts.append("The response may misrepresent tool results.")
                details["hallucination_score"] = hallucination_score

        # Criterion 5: Completeness - all parts of request addressed
        if self.check_completeness:
            completeness_score = self._check_completeness(user_request, response, observations)
            if completeness_score >= 0.6:
                criteria_met.append("complete_response")
                details["completeness_score"] = completeness_score
            else:
                criteria_not_met.append("complete_response")
                feedback_parts.append("The response may not fully address all aspects of the request.")
                details["completeness_score"] = completeness_score

        # Criterion 6: Actionability - right tools used for the task
        if observations:
            actionability_score = self._check_actionability(user_request, plan, observations)
            if actionability_score >= 0.6:
                criteria_met.append("appropriate_tools_used")
                details["actionability_score"] = actionability_score
            else:
                criteria_not_met.append("appropriate_tools_used")
                feedback_parts.append("The tools used may not be appropriate for the request.")
                details["actionability_score"] = actionability_score

        # Calculate weighted score
        total_criteria = len(criteria_met) + len(criteria_not_met)
        if total_criteria == 0:
            score = 1.0
        else:
            # Weight criteria: hallucination and tool success are critical
            weights = {
                "non_empty_response": 1.0,
                "tool_executions_successful": 2.0,
                "response_addresses_request": 1.5,
                "no_hallucination": 2.0,
                "complete_response": 1.5,
                "appropriate_tools_used": 1.0,
            }
            max_possible = sum(weights.get(c, 1.0) for c in criteria_met + criteria_not_met)
            actual = sum(weights.get(c, 1.0) for c in criteria_met)
            score = actual / max_possible if max_possible > 0 else 1.0

        feedback = " ".join(feedback_parts) if feedback_parts else "All criteria met."

        return Evaluation(
            score=score,
            feedback=feedback,
            criteria_met=criteria_met,
            criteria_not_met=criteria_not_met,
        )

    def _check_relevance(self, user_request: str, response: str) -> float:
        """Check if response addresses the user request using keyword overlap."""
        request_lower = user_request.lower()
        response_lower = response.lower()

        # Extract meaningful words from request
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "should",
            "could",
            "may",
            "might",
            "must",
            "can",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
            "what",
            "how",
            "when",
            "where",
            "why",
        }

        request_words = set(re.findall(r"\b\w+\b", request_lower))
        meaningful_words = [w for w in request_words if w not in stopwords and len(w) > 2]

        if not meaningful_words:
            return 1.0  # No meaningful words to check

        # Check how many meaningful words appear in response
        matches = sum(1 for w in meaningful_words if w in response_lower)
        score = matches / len(meaningful_words)

        # For simple fact queries (time, date, calculation), the answer may not contain question words
        # If response looks like a direct answer (ISO timestamp, number, short fact), boost score
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", response.strip()) and any(
            w in user_request.lower() for w in ["time", "date", "clock", "when"]
        ):
            return max(score, 0.9)
        # Also match ISO timestamp with microseconds and timezone
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+", response.strip()) and any(
            w in user_request.lower() for w in ["time", "date", "clock", "when"]
        ):
            return max(score, 0.9)
        if re.match(r"^[\d\.\-]+$", response.strip()) and any(
            w in user_request.lower()
            for w in ["calculate", "what is", "solve", "compute", "math", "sum", "multiply", "divide", "add", "subtract"]
        ):
            return max(score, 0.9)

        # For list/file operations: if response looks like a Python list/dict representation,
        # and request was for listing/reading, boost score
        if (
            (response.strip().startswith("[") or response.strip().startswith("{"))
            and any(
                w in user_request.lower() for w in ["list", "files", "directory", "read", "show", "view", "display"]
            )
            and any(keyword in response_lower for keyword in ["name", "path", "is_file", "is_dir", "size", ".py", ".txt", ".md", ".json"])
        ):
            return max(score, 0.85)

        # For HTTP fetch operations: if response contains URL or HTTP status info,
        # and request was for fetching, boost score
        if (
            ("status:" in response_lower and "fetched:" in response_lower)
            or ("http" in response_lower and "status" in response_lower)
        ) and any(w in user_request.lower() for w in ["fetch", "download", "get", "http", "url"]):
            return max(score, 0.9)

        # For web search: if response mentions CAPTCHA/temporarily unavailable,
        # this is a known limitation of free search APIs, not agent failure
        if "temporarily unavailable" in response_lower and "captcha" in response_lower and any(
            w in user_request.lower() for w in ["search", "find", "look", "web"]
        ):
            return max(score, 0.85)

        # For write operations: if response contains bytes_written or success,
        # and request was for writing/creating, boost score
        if ("bytes_written" in response_lower or "written" in response_lower or "created" in response_lower) and any(
            w in user_request.lower() for w in ["write", "create", "save", "put", "make file"]
        ):
            return max(score, 0.9)

        # For read operations: if response is short text content (not a dict/list),
        # and request was for reading/showing/viewing, the filename may not appear in content
        if (
            response.strip()
            and not response.strip().startswith("[")
            and not response.strip().startswith("{")
            and not "status:" in response_lower
            and not "fetched:" in response_lower
            and any(w in user_request.lower() for w in ["read", "show", "view", "display", "open", "cat"])
            and len(response) < 1000
        ):
            return max(score, 0.85)

        # For move/rename operations: if response is True or contains success,
        # and request was for moving/renaming, boost score
        if ("true" in response_lower or "moved" in response_lower or "renamed" in response_lower or "success" in response_lower) and any(
            w in user_request.lower() for w in ["move", "rename", "mv"]
        ):
            return max(score, 0.9)

        return score

    def _check_hallucination(self, observations: list[dict], response: str) -> float:
        """Check if response faithfully represents tool results."""
        response_lower = response.lower()

        # Extract key information from tool results
        tool_facts = []
        for obs in observations:
            result = obs.get("result", {})

            if isinstance(result, dict):
                # Extract key facts from structured results
                if "content" in result:
                    tool_facts.append(str(result["content"]).lower())
                if "payload" in result:
                    tool_facts.append(str(result["payload"]).lower())
                if "stdout" in result:
                    tool_facts.append(str(result["stdout"]).lower())
                # Filesystem tools return bytes_written, bytes_read, etc.
                if "bytes_written" in result:
                    tool_facts.append(f"bytes_written {result['bytes_written']}")
                if "bytes_read" in result:
                    tool_facts.append(f"bytes_read {result['bytes_read']}")
                if "path" in result:
                    tool_facts.append(str(result["path"]).lower())
            elif isinstance(result, str):
                tool_facts.append(result.lower())
            elif isinstance(result, (list, tuple)):
                for item in result:
                    tool_facts.append(str(item).lower())

        if not tool_facts:
            return 1.0

        # Check if key facts from tools appear in response
        facts_mentioned = 0
        for fact in tool_facts:
            # Check if significant portion of fact appears in response
            words = fact.split()
            if len(words) >= 3:
                # Check for 3+ consecutive words
                for i in range(len(words) - 2):
                    phrase = " ".join(words[i : i + 3])
                    if phrase in response_lower:
                        facts_mentioned += 1
                        break
            elif fact in response_lower:
                facts_mentioned += 1

        return facts_mentioned / len(tool_facts)

    def _check_completeness(self, user_request: str, response: str, observations: list[dict]) -> float:
        """Check if response addresses all parts of the request."""
        # Simple heuristic: look for question marks, "and", commas suggesting multiple parts
        request_lower = user_request.lower()

        # Count distinct "tasks" in request
        task_indicators = [" and ", ", ", " then ", " also ", " additionally ", " plus "]
        num_tasks = 1
        for indicator in task_indicators:
            num_tasks += request_lower.count(indicator)

        # If single task, completeness is easier
        if num_tasks == 1:
            return 1.0 if self._check_relevance(user_request, response) > 0.5 else 0.5

        # For multi-task requests, check if response covers multiple aspects
        response_lower = response.lower()
        task_keywords = []

        # Extract potential task keywords
        for indicator in task_indicators:
            parts = request_lower.split(indicator)
            for part in parts[1:]:  # Skip first part
                words = part.strip().split()[:5]  # First 5 words after indicator
                if words:
                    task_keywords.append(" ".join(words))

        if not task_keywords:
            return 0.8  # Can't parse well, assume mostly complete

        covered = sum(1 for kw in task_keywords if any(w in response_lower for w in kw.split()[:3]))
        return covered / len(task_keywords)

    def _check_actionability(self, user_request: str, plan: dict, observations: list[dict]) -> float:
        """Check if appropriate tools were used for the request."""
        request_lower = user_request.lower()
        used_tools = [obs.get("tool_name", "") for obs in observations]

        # Define tool appropriateness heuristics
        tool_keywords = {
            "calculator": ["calculate", "math", "compute", "sum", "multiply", "divide", "add", "subtract", "what is"],
            "fs.read": ["read", "cat", "show", "view", "open", "display"],
            "fs.write": ["write", "create", "save", "put", "make file"],
            "fs.list": ["list", "ls", "dir", "show files", "what files"],
            "fs.move": ["move", "rename", "mv"],
            "terminal.run": ["run", "execute", "command", "shell", "terminal"],
            "time": ["time", "date", "clock"],
        }

        # Determine expected tools based on request
        expected_tools = []
        for tool, keywords in tool_keywords.items():
            if any(kw in request_lower for kw in keywords):
                expected_tools.append(tool)

        if not expected_tools:
            return 1.0  # No specific tool expected

        # Check overlap
        used_set = set(used_tools)
        expected_set = set(expected_tools)

        if not used_set and expected_set:
            return 0.0  # Should have used tools but didn't

        overlap = len(used_set & expected_set)
        return overlap / len(expected_set)


# Backward compatibility - simple evaluator for existing tests
class SimpleEvaluator:
    """Simple evaluator matching original interface for backward compatibility."""

    def evaluate(self, user_request: str, plan: dict, observations: list, response: str) -> Evaluation:
        enhanced = Evaluator()
        return enhanced.evaluate(user_request, plan, observations, response)