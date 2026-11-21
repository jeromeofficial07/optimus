"""
MemoryAIEngine - the AI engine plus memory.

  * commands such as "remember...", "add task...", "remind me..." are answered
    instantly by the CommandRouter, before the AI is involved
  * every other message gets today's date and the relevant remembered facts added
    to the system prompt, so the AI can use what you told it in earlier sessions
  * set_history() restores the AI's context when an old conversation is reopened
"""
from collections.abc import Iterator
from datetime import datetime

from app.agent.commands import CommandRouter
from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.brain.ai_engine import AIEngine
from app.storage.database import DatabaseError
from app.storage.repositories import Storage

MEMORY_PROMPT_LIMIT = 8  # At most this many remembered facts go into each prompt


class MemoryAIEngine(AIEngine):
    def __init__(self, executor: ToolExecutor, storage: Storage):
        super().__init__(executor=executor)
        self._storage = storage
        self._commands = CommandRouter(executor, storage)

    def stream_reply(self, user_text: str, callbacks: ToolCallbacks | None = None) -> Iterator[str]:
        callbacks = callbacks or ToolCallbacks()
        reply = self._commands.handle(user_text, callbacks)
        if reply is not None:  # It was a command: answered without the AI
            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": reply})
            self._trim_history()
            self._follow_up = False
            yield reply
            return
        yield from super().stream_reply(user_text, callbacks)

    def _build_messages(self) -> list:
        """The normal system prompt plus today's date and the relevant remembered facts."""
        messages = super()._build_messages()
        extra = self._memory_block()
        messages[0] = {"role": "system", "content": messages[0]["content"] + "\n\n" + extra}
        return messages

    def _memory_block(self) -> str:
        lines = [f"Today is {datetime.now():%A, %d %B %Y}."]
        last_user_text = next((m["content"] for m in reversed(self._history) if m["role"] == "user"), "")
        try:
            facts = self._storage.memory.relevant(last_user_text, MEMORY_PROMPT_LIMIT)
        except DatabaseError:
            facts = []  # A database problem must never stop the AI from answering
        if facts:
            lines.append("Things the user asked you to remember (use them naturally, only when relevant):")
            lines += [f"- {m['key']}: {m['value']}" for m in facts]
        return "\n".join(lines)

    def set_history(self, messages: list[dict]):
        """Restore the context of a conversation loaded from the database."""
        self._history = [{"role": m["role"], "content": m["content"]}
                         for m in messages if m["role"] in ("user", "assistant")]
        self._trim_history()
        self._follow_up = False