"""
ToolExecutor - runs ONE tool safely:

    registry check -> validate arguments -> permission -> run -> audit log

The AI never calls tool functions directly. It can only hand a name and
arguments to execute(), which applies every safety check.
"""
import logging

# ConfirmationRequest and ToolCallbacks live in events.py; importing them here keeps
# older code such as "from app.agent.executor import ToolCallbacks" working.
from app.agent.events import ConfirmationRequest, SafeDict, ToolCallbacks  # noqa: F401
from app.agent.permissions import PermissionManager
from app.agent.registry import Tool, ToolContext, ToolError, ToolRegistry, ToolResult
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


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, context: ToolContext,
                 permissions: PermissionManager | None = None):
        self.registry = registry
        self.context = context
        self.permissions = permissions or PermissionManager()

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
        if not self.permissions.authorize(tool, args, callbacks):
            return self._finish(
                ToolResult(tool.name, False,
                           "The user declined this action, so nothing was done.", declined=True),
                args, callbacks)

        # 4) Run the predefined function
        if callbacks.on_start:
            try:
                text = tool.status_text.format_map(SafeDict(args)) if tool.status_text \
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