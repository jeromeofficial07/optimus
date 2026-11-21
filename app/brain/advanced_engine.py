"""
AdvancedAIEngine = MemoryAIEngine + features.

Order for every message:
   1. Phase 7 commands  (remember, tasks, reminders)
   2. FeatureRouter     (file search, briefing, history, coding, web)
   3. the normal AI path (Phase 6 intent routing, tools, chat)
It also adds snippets from old conversations to the prompt when you refer to the past.
"""
from collections.abc import Iterator

from app.agent.events import ToolCallbacks
from app.brain.memory_engine import MemoryAIEngine


class AdvancedAIEngine(MemoryAIEngine):
    def __init__(self, executor, storage):
        super().__init__(executor, storage)
        self._router = None
        self._history_index = None
        self._conversation_id = lambda: None

    def attach(self, router, history_index=None, conversation_id=None):
        self._router = router
        self._history_index = history_index
        if conversation_id is not None:
            self._conversation_id = conversation_id

    # ------------------------------------------------------------ used by features
    def stream_with_system(self, system: str, user: str) -> Iterator[str]:
        """One-off question with its own system prompt, no tools and no chat history."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            yield from self._stream_chat(messages, [])
        except Exception as exc:
            raise self._translate_error(exc) from exc

    # ------------------------------------------------------------ routing
    def stream_reply(self, user_text: str, callbacks: ToolCallbacks | None = None) -> Iterator[str]:
        callbacks = callbacks or ToolCallbacks()
        reply = self._commands.handle(user_text, callbacks)           # 1. Phase 7 commands
        if reply is None and self._router is not None:
            reply = self._router.handle(user_text, callbacks)         # 2. Phase 8 features
        if reply is None:
            # 3. The normal AI path (skips MemoryAIEngine, whose command step already ran above)
            yield from super(MemoryAIEngine, self).stream_reply(user_text, callbacks)
            return

        self._history.append({"role": "user", "content": user_text})
        parts: list[str] = []
        try:
            for piece in ([reply] if isinstance(reply, str) else reply):
                parts.append(piece)
                yield piece
        finally:
            text = "".join(parts)
            if text:
                self._history.append({"role": "assistant", "content": text})
            else:
                self._history.pop()
            self._trim_history()
            self._follow_up = False

    def _memory_block(self) -> str:
        block = super()._memory_block()
        if self._history_index is not None:
            last = next((m["content"] for m in reversed(self._history) if m["role"] == "user"), "")
            snippets = self._history_index.context_for(last, exclude_id=self._conversation_id())
            if snippets:
                block += ("\n\nRelevant messages from earlier conversations "
                          "(use them only if they help answer):\n" + "\n".join(snippets))
        return block