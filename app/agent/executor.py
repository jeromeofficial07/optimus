"""
ToolExecutor - the single gateway through which every action passes.

    validate -> (ask permission if needed) -> run -> log

The AI never calls tool functions directly. It can only hand a name and
arguments to execute(), which applies every safety check.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.agent.registry import (Risk, Tool, ToolContext, ToolError, ToolRegistry,
                                ToolResult)
from app.agent.validator import validate_arguments
from app.config import ACTION_LOG_PATH

# ---- audit log: one line per request, whether it was allowed or not
_log = logging.getLogger("optimus.actions")
if not _log.handlers:
    _handler = logging.FileHandler(ACTION_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False


@dataclass
class ConfirmationRequest:
    tool: str
    title: str
    description: str
    risk: Risk


@dataclass
class ToolCallbacks:
    """Hooks the GUI uses to follow what the executor is doing. All are optional."""
    confirm: Callable[[ConfirmationRequest], bool] | None = None  # Ask the user; True = allowed
    on_start: Callable[[str], None] | None = None                 # "Opening Notepad..."
    on_result: Callable[[ToolResult], None] | None = None


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, context: ToolContext):
        self.registry = registry
        self.context = context

    def execute(self, name, raw_args, callbacks: ToolCallbacks | None = None) -> ToolResult:
        callbacks = callbacks or ToolCallbacks()

        # 1) The tool must exist in the registry
        tool: Tool | None = self.registry.get(str(name))
        if tool is None:
            return self._finish(
                ToolResult(str(name), False, f"'{name}' is not an available action."),
                raw_args, callbacks)

        # 2) The arguments must be valid and any path must be safe
        try:
            args = validate_arguments(tool, raw_args, self.context.guard)
        except ToolError as exc:
            return self._finish(
                ToolResult(tool.name, False, f"Request rejected: {exc}"), raw_args, callbacks)

        # 3) Sensitive and destructive actions need the user's permission
        if tool.risk is not Risk.SAFE:
            request = ConfirmationRequest(
                tool=tool.name,
                title="Permission needed" if tool.risk is Risk.SENSITIVE else "Warning: permission needed",
                description=tool.confirm_text.format_map(_SafeDict(args)) or tool.description,
                risk=tool.risk,
            )
            allowed = False
            if callbacks.confirm is not None:
                try:
                    allowed = bool(callbacks.confirm(request))
                except Exception:
                    allowed = False
            if not allowed:
                return self._finish(
                    ToolResult(tool.name, False,
                               "The user declined this action, so nothing was done.", declined=True),
                    args, callbacks)

        # 4) Run the predefined function
        if callbacks.on_start:
            try:
                text = tool.status_text.format_map(_SafeDict(args)) if tool.status_text \
                    else f"Running {tool.name}..."
                callbacks.on_start(text)
            except Exception:
                pass
        try:
            result = ToolResult(tool.name, True, str(tool.func(self.context, **args)))
        except ToolError as exc:
            result = ToolResult(tool.name, False, str(exc))
        except Exception as exc:  # A bug in a tool must never crash the application
            _log.exception("Unexpected error in %s", tool.name)
            result = ToolResult(tool.name, False, f"The action failed unexpectedly: {exc}")
        return self._finish(result, args, callbacks)

    def _finish(self, result: ToolResult, args, callbacks: ToolCallbacks) -> ToolResult:
        """Write the audit log line and notify the GUI."""
        status = "DECLINED" if result.declined else ("OK" if result.ok else "FAILED")
        first_line = result.message.splitlines()[0] if result.message else ""
        _log.info("%s | %s | args=%s | %s", status, result.tool, args, first_line)
        if callbacks.on_result:
            try:
                callbacks.on_result(result)
            except Exception:
                pass
        return result