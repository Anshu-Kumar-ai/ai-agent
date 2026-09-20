class ConversationMemory:
    """Stores recent conversation messages and builds model context."""

    def __init__(self, max_messages: int = 10):
        if max_messages <= 0:
            raise ValueError("max_messages must be greater than 0")

        self.max_messages = max_messages
        self.messages = []

    def add_user_message(self, message: str) -> None:
        """Store a user message."""
        self._add("user", message)

    def add_agent_message(self, message: str) -> None:
        """Store an agent response."""
        self._add("assistant", message)

    def _add(self, role: str, message: str) -> None:
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        message = message.strip()

        if not message:
            raise ValueError("message cannot be empty")

        self.messages.append({
            "role": role,
            "content": message,
        })

        self.messages = self.messages[-self.max_messages:]

    def get_messages(self) -> list[dict]:
        """Return a copy of the stored conversation."""
        return list(self.messages)

    def build_context(self, current_message: str) -> str:
        """Build a plain-text conversation context for the model."""
        if not isinstance(current_message, str):
            raise TypeError("current_message must be a string")

        current_message = current_message.strip()

        if not current_message:
            raise ValueError("current_message cannot be empty")

        lines = [
            "Previous conversation:",
        ]

        for message in self.messages:
            role = message["role"].capitalize()
            content = message["content"]
            lines.append(f"{role}: {content}")

        lines.extend([
            "",
            f"User: {current_message}",
            "",
            "Answer the user's latest message while considering the previous conversation.",
        ])

        return "\n".join(lines)

    def clear(self) -> None:
        """Delete all stored conversation messages."""
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)