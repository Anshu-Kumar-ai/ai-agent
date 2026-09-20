from datetime import datetime

from app.tools.base import BaseTool


class TimeTool(BaseTool):
    """Return the current local date and time with its UTC offset."""

    name = "time"
    description = "Get the current local date and time as an ISO 8601 timestamp."
    selection_phrases = (
        "what time is it",
        "what's the time",
        "current time",
        "tell me the time",
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def execute(self) -> str:
        return datetime.now().astimezone().isoformat()
