"""
AIEngine - the bridge between OPTIMUS and the local Ollama server.

Responsibilities:
  * keep the conversation history (context) and trim it
  * stream normal answers back piece by piece
  * Phase 5: let the model REQUEST actions (tool calls), hand them to the
    ToolExecutor for validation, and turn the results into a spoken-style answer
  * translate low-level network errors into friendly messages
"""
from collections.abc import Iterator

import httpx
import ollama
from ollama import ResponseError

from app.agent.executor import ToolCallbacks, ToolExecutor
from app.agent.intent import looks_like_action
from app.config import (LLM_CONTEXT_TOKENS, LLM_TEMPERATURE, MAX_HISTORY_MESSAGES,
                        MAX_TOOL_CALLS_PER_TURN, OLLAMA_HOST, OLLAMA_KEEP_ALIVE, OLLAMA_MODEL,
                        OLLAMA_TIMEOUT, SYSTEM_PROMPT, TOOL_INTENT_GATE)


class AIEngineError(Exception):
    """
    Any problem talking to Ollama.
    kind    - short code the UI can react to: offline, no_model, timeout, server, unknown
    message - a friendly sentence that can be shown directly to the user
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def _field(obj, name, default=None):
    """Read a field from an Ollama response object (new library) or a dict (old library)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class AIEngine:
    def __init__(self, model: str = OLLAMA_MODEL, host: str = OLLAMA_HOST,
                 system_prompt: str = SYSTEM_PROMPT, max_history: int = MAX_HISTORY_MESSAGES,
                 executor: ToolExecutor | None = None):
        self.model = model
        self.system_prompt = system_prompt
        self.max_history = max_history
        self._executor = executor            # None = plain chatbot without actions
        self._tools_supported = True         # Becomes False if the model rejects tools
        self._follow_up = False              # True if the previous turn used a tool
        self._client = ollama.Client(host=host, timeout=OLLAMA_TIMEOUT)
        self._history: list[dict[str, str]] = []  # Only user and final assistant messages

    # ------------------------------------------------------------ context
    def reset(self):
        """Forget the conversation (used by 'New conversation')."""
        self._history.clear()
        self._follow_up = False

    def _build_messages(self) -> list:
        """The system prompt always goes first, followed by the recent history."""
        return [{"role": "system", "content": self.system_prompt}, *self._history]

    def _trim_history(self):
        """Keep only the newest messages so requests stay fast and inside the context window."""
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]
        while self._history and self._history[0]["role"] != "user":
            self._history.pop(0)

    def _options(self) -> dict:
        return {"temperature": LLM_TEMPERATURE, "num_ctx": LLM_CONTEXT_TOKENS}

    # ------------------------------------------------------------ chatting
    def stream_reply(self, user_text: str, callbacks: ToolCallbacks | None = None) -> Iterator[str]:
        """
        Send a message and yield the answer in small pieces.

        If the message looks like a computer action, the model is given the tool list.
        When it asks for a tool, the executor validates and (if needed) asks the user's
        permission, then the model writes the final answer from the tool's result.

        The 'finally' block saves only the user message and the final answer to the history,
        or forgets the question if nothing came back.
        """
        self._history.append({"role": "user", "content": user_text})
        parts: list[str] = []
        used_tools = False
        try:
            messages = self._build_messages()
            if self._should_use_tools(user_text):
                used_tools = yield from self._tool_turn(messages, parts, callbacks)
            else:
                yield from self._stream_chat(messages, parts)
        except Exception as exc:  # GeneratorExit is not an Exception, so closing is safe
            raise self._translate_error(exc) from exc
        finally:
            reply = "".join(parts)
            if reply:
                self._history.append({"role": "assistant", "content": reply})
            else:
                self._history.pop()
            self._follow_up = used_tools
            self._trim_history()

    def _should_use_tools(self, user_text: str) -> bool:
        if self._executor is None or not self._tools_supported:
            return False
        if not TOOL_INTENT_GATE:
            return True
        # Follow-ups such as "open the second one" carry no keyword, so the tools stay
        # available for one more turn after a tool was used.
        return self._follow_up or looks_like_action(user_text)

    def _stream_chat(self, messages: list, parts: list[str]) -> Iterator[str]:
        """Ask the model WITHOUT tools and stream the text."""
        stream = self._client.chat(model=self.model, messages=messages, stream=True,
                                   options=self._options(), keep_alive=OLLAMA_KEEP_ALIVE)
        for chunk in stream:
            piece = chunk["message"]["content"]
            if piece:
                parts.append(piece)
                yield piece

    def _tool_turn(self, messages: list, parts: list[str], callbacks) -> Iterator[str]:
        """
        Ask the model WITH tools available. Returns True if it requested any tool.
        Step 1: one non-streamed call to see whether the model wants a tool.
        Step 2: run each requested tool through the executor.
        Step 3: stream the model's final answer, which now knows the results.
        """
        try:
            response = self._client.chat(
                model=self.model, messages=messages, tools=self._executor.registry.schemas(),
                stream=False, options=self._options(), keep_alive=OLLAMA_KEEP_ALIVE)
        except ResponseError as exc:
            if "tool" in str(exc.error).lower():
                self._tools_supported = False
                note = ("The current model does not support computer actions, so I can only chat. "
                        "Try the model qwen2.5:3b.")
                parts.append(note)
                yield note
                return False
            raise

        message = _field(response, "message")
        calls = _field(message, "tool_calls") or []
        if not calls:                                   # Just a normal answer
            text = _field(message, "content") or ""
            if text:
                parts.append(text)
                yield text
            return False

        messages.append(message)                        # The assistant message holding the tool calls
        summaries = []
        for call in list(calls)[:MAX_TOOL_CALLS_PER_TURN]:
            function = _field(call, "function")
            name = _field(function, "name")
            result = self._executor.execute(name, _field(function, "arguments"), callbacks)
            summaries.append(result.message.splitlines()[0] if result.message else "")
            messages.append({"role": "tool", "tool_name": name, "content": result.message})

        before = len(parts)
        yield from self._stream_chat(messages, parts)   # Final answer, streamed
        if len(parts) == before:                        # The model said nothing: fall back to the results
            fallback = " ".join(summaries)
            parts.append(fallback)
            yield fallback
        return True

    # ------------------------------------------------------------ health
    def check_connection(self) -> tuple[str, str]:
        """
        Is Ollama running and is the model installed?
        Returns (kind, message). kind == "ok" means everything is fine.
        """
        try:
            self._client.list()
        except Exception as exc:
            err = self._translate_error(exc)
            return err.kind, err.message
        try:
            self._client.show(self.model)
        except Exception as exc:
            err = self._translate_error(exc)
            return err.kind, err.message
        return "ok", f"Connected to Ollama. Model: {self.model}"

    def warm_up(self):
        """Load the model into RAM ahead of time. Failures are ignored."""
        try:
            self._client.chat(model=self.model, messages=[], keep_alive=OLLAMA_KEEP_ALIVE)
        except Exception:
            pass

    # ------------------------------------------------------------ errors
    def _translate_error(self, exc: Exception) -> AIEngineError:
        """Convert library/network exceptions into an AIEngineError with a friendly message."""
        if isinstance(exc, AIEngineError):
            return exc
        if isinstance(exc, ResponseError):
            if exc.status_code == 404:
                return AIEngineError(
                    "no_model",
                    f"The model '{self.model}' is not installed yet. "
                    f"Open a terminal and run:  ollama pull {self.model}",
                )
            return AIEngineError("server", f"Ollama reported an error: {exc.error}")
        if isinstance(exc, httpx.TimeoutException):   # Must be checked before TransportError
            return AIEngineError(
                "timeout",
                "The model took too long to respond. It may still be loading. "
                "Wait a moment and try again.",
            )
        if isinstance(exc, (ConnectionError, httpx.TransportError)):
            return AIEngineError(
                "offline",
                "I can't reach Ollama. Make sure it is running (look for the llama icon "
                "in the system tray, or start it from the Start menu), then send your "
                "message again.",
            )
        return AIEngineError("unknown", f"Unexpected error: {exc}")