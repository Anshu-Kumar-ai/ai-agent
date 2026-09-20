import json
import logging
from typing import Optional, Tuple, Dict, Any
from uuid import uuid4
import time

from ..base import ReflectionEngine
from ....core.state.action import Action
from ....core.state.attempt import Attempt
from ....core.state.agent_state import TaskGoalState, ConversationState
from ....core.state.reflection import Reflection
from ....core.state.next_action import NextAction, NextActionType
from ....modules.llm.routing import LLMRouter
from ....modules.llm.provider import LLMProvider
from ..stub_reflector import StubReflector

logger = logging.getLogger(__name__)


class LLMStructuredReflector(ReflectionEngine):
    """
    Reflection engine that uses an LLM to generate structured reflection and next action.
    Falls back to StubReflector on failure.
    """

    def __init__(self, llm_router: LLMRouter, fallback: Optional[ReflectionEngine] = None, max_retries: int = 2):
        self.llm_router = llm_router
        self.fallback = fallback or StubReflector()
        self.max_retries = max_retries

    def _build_prompt(self, attempt: Attempt, task_state: TaskGoalState, conv_state: ConversationState) -> str:
        """Construct a prompt for the LLM to reflect on an attempt."""
        # We'll include the attempt details, goal, and recent conversation.
        goal_id = task_state.active_goal_id
        goal_desc = "unknown"
        if goal_id:
            goal_obj = task_state.goal_stack[-1] if task_state.goal_stack else None
            if goal_obj:
                goal_desc = str(goal_obj)

        # Recent conversation turns (last 3)
        recent_turns = conv_state.get_recent_turns(3)
        recent_conversation = "\n".join([f"{turn.role}: {turn.text}" for turn in recent_turns])

        prompt_parts = [
            "You are an AI agent reflecting on a recent action attempt.",
            f"Goal: {goal_desc}",
            "",
            "Attempt details:",
            f"  Action: {attempt.action.tool_name}",
            f"  Arguments: {attempt.action.arguments}",
            f"  Observation status: {attempt.observation.status}",
            f"  Observation payload: {attempt.observation.payload}",
            "",
            "Recent conversation:",
            recent_conversation if recent_conversation else "None",
            "",
            "Based on this, provide a reflection and suggest a next action.",
            "Return a JSON object with the following keys:",
            "  - reasoning: a string explaining your reflection",
            "  - next_action: an object with:",
            "      * action_type: one of \"RETRY\", \"PARAM_CHANGE\", \"ALTERNATIVE_TOOL\", \"DECOMPOSE_FURTHER\", \"WAIT_FOR_EXTERNAL\", \"NOOP\"",
            "      * payload: an object (optional) containing any additional parameters",
            "      * confidence: a float between 0 and 1 (optional, default 1.0)",
            "",
            "If you are unsure, set action_type to \"NOOP\" and provide reasoning.",
            "Do not include any extra text before or after the JSON object.",
        ]
        return "\n".join(prompt_parts)

    def _parse_llm_response(self, response: str) -> Tuple[str, Optional[NextAction]]:
        """Parse the LLM's JSON response into reasoning and next action."""
        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"LLM reflection response is not valid JSON: {response}")
            raise ValueError(f"Invalid JSON from LLM: {e}")

        if not isinstance(data, dict):
            logger.warning(f"LLM reflection response is not a dict: {data}")
            raise ValueError("Expected a JSON object")

        reasoning = data.get("reasoning")
        if not isinstance(reasoning, str):
            logger.warning(f"LLM reflection response missing or invalid 'reasoning'")
            raise ValueError("Missing or invalid 'reasoning'")

        next_action_data = data.get("next_action")
        next_action = None
        if next_action_data is not None:
            if not isinstance(next_action_data, dict):
                logger.warning(f"LLM reflection response 'next_action' is not an object: {next_action_data}")
                raise ValueError("'next_action' must be an object")

            action_type = next_action_data.get("action_type")
            if not isinstance(action_type, str):
                logger.warning(f"LLM reflection response missing or invalid 'action_type'")
                raise ValueError("Missing or invalid 'action_type'")

            payload = next_action_data.get("payload", {})
            if not isinstance(payload, dict):
                logger.warning(f"LLM reflection response 'payload' is not an object: {payload}")
                raise ValueError("'payload' must be an object")

            confidence = next_action_data.get("confidence", 1.0)
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                logger.warning(f"LLM reflection response invalid 'confidence': {confidence}")
                raise ValueError("'confidence' must be a float between 0 and 1")

            # Build NextAction based on action_type
            if action_type == NextActionType.RETRY:
                next_action = NextAction.retry(payload=payload, confidence=confidence)
            elif action_type == NextActionType.PARAM_CHANGE:
                next_action = NextAction.param_change(params=payload, confidence=confidence)
            elif action_type == NextActionType.ALTERNATIVE_TOOL:
                tool_name = payload.get("tool_name")
                if not isinstance(tool_name, str):
                    logger.warning(f"ALTERNATIVE_TOOL missing or invalid 'tool_name' in payload")
                    raise ValueError("ALTERNATIVE_TOOL requires 'tool_name' in payload")
                # Remove tool_name from payload for the alternative_tool factory
                alt_payload = {k: v for k, v in payload.items() if k != "tool_name"}
                next_action = NextAction.alternative_tool(tool_name=tool_name, payload=alt_payload, confidence=confidence)
            elif action_type == NextActionType.DECOMPOSE_FURTHER:
                next_action = NextAction.decompose_further(payload=payload, confidence=confidence)
            elif action_type == NextActionType.WAIT_FOR_EXTERNAL:
                next_action = NextAction.wait_for_external(payload=payload, confidence=confidence)
            elif action_type == NextActionType.NOOP:
                next_action = NextAction.noop(payload=payload, confidence=confidence)
            else:
                logger.warning(f"LLM reflection response unknown action_type: {action_type}")
                raise ValueError(f"Unknown action_type: {action_type}")

        return reasoning, next_action

    def reflect(
        self,
        attempt: Attempt,
        task_state: TaskGoalState,
        conv_state: ConversationState
    ) -> Tuple[Reflection, Optional[NextAction]]:
        if not self.llm_router.is_available():
            logger.warning("LLM router not available, using fallback reflector")
            return self.fallback.reflect(attempt, task_state, conv_state)

        prompt = self._build_prompt(attempt, task_state, conv_state)
        logger.debug(f"LLM reflector prompt:\n{prompt}")

        reasoning = ""
        next_action = None
        last_exception = None
        for retry in range(self.max_retries + 1):
            try:
                response = self.llm_router.generate(prompt)
                logger.debug(f"LLM reflector raw response: {response}")
                reasoning, next_action = self._parse_llm_response(response)
                logger.info(f"LLM reflector generated reasoning: {reasoning[:100]}...")
                break
            except Exception as e:
                last_exception = e
                logger.warning(f"LLM reflector attempt {retry + 1}/{self.max_retries + 1} failed: {e}")
                if retry < self.max_retries:
                    time.sleep(0.5 * (retry + 1))  # brief backoff
                else:
                    logger.warning(f"LLM reflector failed after {self.max_retries + 1} attempts: {last_exception}. Falling back to stub reflector.")
                    return self.fallback.reflect(attempt, task_state, conv_state)

        # Create the reflection record
        reflection = Reflection.create(
            attempt=attempt,
            goal_id=task_state.active_goal_id if task_state.active_goal_id else attempt.action.action_id,
            reasoning=reasoning,
            next_action=next_action
        )
        return reflection, next_action