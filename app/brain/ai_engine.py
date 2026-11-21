"""
AIEngine - the bridge between OPTIMUS and the local Ollama server.

Responsibilities:
  * keep the conversation history (context) and trim it
  * recognise the intent of each message and route it:
        CHAT       -> stream a normal answer
        ACTION     -> the model may call tools (each one verified)
        WORKFLOW   -> run an approved multi-step workflow
        MULTI_STEP -> the model drafts a plan, code validates it, you approve it, it runs
  * translate low-level network errors into friendly messages
"""
import json
from collections.abc import Iterator

import httpx
import ollama
from ollama import ResponseError

from app.agent.agent import Agent
from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.intent import Intent, IntentKind, recognize_intent
from app.agent.plan import PlanError
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
        self._tools_supported = True         # Becomes False if the model rejects tools
        self._follow_up = False              # True if the previous turn used a tool
        self._client = ollama.Client(host=host, timeout=OLLAMA_TIMEOUT)
        self._history: list[dict[str, str]] = []  # Only user and final assistant messages
        # The agent (planner, controller, verifier, permissions). None = plain chatbot.
        self._agent: Agent | None = Agent(executor, llm=self) if executor is not None else None

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

    # ------------------------------------------------------------ routing
    def _route(self, user_text: str) -> Intent:
        if self._agent is None:
            return Intent(IntentKind.CHAT)
        intent = recognize_intent(user_text, self._follow_up)
        if intent.kind is IntentKind.CHAT and not TOOL_INTENT_GATE:
            return Intent(IntentKind.ACTION)
        if intent.kind is IntentKind.ACTION and not self._tools_supported:
            return Intent(IntentKind.CHAT)
        return intent

    # ------------------------------------------------------------ chatting
    def stream_reply(self, user_text: str, callbacks: ToolCallbacks | None = None) -> Iterator[str]:
        """
        Send a message and yield the answer in small pieces.

        The 'finally' block saves only the user message and the final answer to the
        history, or forgets the question if nothing came back.
        """
        callbacks = callbacks or ToolCallbacks()
        self._history.append({"role": "user", "content": user_text})
        parts: list[str] = []
        used_tools = False
        try:
            messages = self._build_messages()
            intent = self._route(user_text)
            if intent.kind is IntentKind.WORKFLOW:
                used_tools = yield from self._workflow_turn(intent.workflow, parts, callbacks)
            elif intent.kind is IntentKind.MULTI_STEP:
                used_tools = yield from self._plan_turn(user_text, messages, parts, callbacks)
            elif intent.kind is IntentKind.ACTION:
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

    def _stream_chat(self, messages: list, parts: list[str]) -> Iterator[str]:
        """Ask the model WITHOUT tools and stream the text."""
        stream = self._client.chat(model=self.model, messages=messages, stream=True,
                                   options=self._options(), keep_alive=OLLAMA_KEEP_ALIVE)
        for chunk in stream:
            piece = chunk["message"]["content"]
            if piece:
                parts.append(piece)
                yield piece

    # ------------------------------------------------------------ workflows and plans
    def _workflow_turn(self, name: str, parts: list[str], callbacks) -> Iterator[str]:
        """Run an approved workflow. The summary comes from the report, not from the model."""
        agent = self._agent
        try:
            plan = agent.planner.from_workflow(name)
            agent.planner.validate(plan)
        except PlanError as exc:
            text = f"I can't run that workflow: {exc}"
            parts.append(text)
            yield text
            return False
        report = agent.controller.run_plan(plan, callbacks)
        text = report.summary()
        parts.append(text)
        yield text
        return True

    def _plan_turn(self, user_text: str, messages: list, parts: list[str], callbacks) -> Iterator[str]:
        """Let the model draft a plan, validate it, get approval, then run it."""
        agent = self._agent
        try:
            plan = agent.planner.from_llm(user_text)
        except PlanError:
            # No usable plan: fall back to one-tool-at-a-time behaviour
            return (yield from self._tool_turn(messages, parts, callbacks))
        if not agent.permissions.authorize_plan(plan, callbacks):
            text = "Okay, I cancelled that plan. Nothing was done."
            parts.append(text)
            yield text
            return False
        report = agent.controller.run_plan(plan, callbacks)
        text = report.summary()
        parts.append(text)
        yield text
        return True

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        """Ask the model for JSON that must match a schema. Used by the task planner."""
        response = self._client.chat(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format=schema, stream=False,
            options={"temperature": 0.1, "num_ctx": LLM_CONTEXT_TOKENS},
            keep_alive=OLLAMA_KEEP_ALIVE,
        )
        return json.loads(_field(_field(response, "message"), "content") or "{}")

    # ------------------------------------------------------------ single tool calls
    def _tool_turn(self, messages: list, parts: list[str], callbacks) -> Iterator[str]:
        """
        Ask the model WITH tools available. Returns True if it requested any tool.
        Each requested tool goes through the controller (validate, permission, run, verify).
        """
        controller = self._agent.controller
        try:
            response = self._client.chat(
                model=self.model, messages=messages, tools=controller.registry.schemas(),
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
            result = controller.run_tool(name, _field(function, "arguments"), callbacks)
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
        """Is Ollama running and is the model installed? Returns (kind, message)."""
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