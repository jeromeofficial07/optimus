"""
Tool registry: the ONLY actions OPTIMUS is able to perform.

A Tool is a predefined Python function plus a description of its arguments.
The AI model can only ask for tools registered here. It can never run
arbitrary code or shell commands.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.path_guard import PathGuard


class ToolError(Exception):
    """A tool could not do what was asked. The message is shown to the user and the AI."""


class ValidationError(ToolError):
    """The request was rejected before anything ran (bad name, bad argument, bad path)."""


class Risk(str, Enum):
    SAFE = "safe"                # Runs immediately
    SENSITIVE = "sensitive"      # Needs the user's permission (for example locking the PC)
    DESTRUCTIVE = "destructive"  # Needs permission and warns about data loss


@dataclass(frozen=True)
class Param:
    """Describes one argument of a tool. The validator enforces every field."""
    name: str
    type: str                          # "string" or "integer"
    description: str
    required: bool = True
    enum: tuple[str, ...] | None = None  # If set, only these values are accepted
    path: bool = False                 # True = must be a safe path inside the allowed folders
    max_length: int = 200
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str                   # Shown to the AI so it can pick the right tool
    func: Callable                     # func(context, **validated_arguments) -> message
    params: tuple[Param, ...] = ()
    risk: Risk = Risk.SAFE
    status_text: str = ""              # Shown while running, for example "Opening {name}..."
    confirm_text: str = ""             # Shown in the permission card

    def schema(self) -> dict:
        """The description of this tool in the format Ollama expects."""
        properties = {}
        for p in self.params:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = list(p.enum)
            properties[p.name] = prop
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": [p.name for p in self.params if p.required],
                },
            },
        }


@dataclass
class ToolResult:
    tool: str
    ok: bool
    message: str                       # Plain English, sent back to the AI
    declined: bool = False             # True if the user said no to the permission prompt


@dataclass
class ToolContext:
    """Shared state that tools may use."""
    guard: PathGuard
    last_search_results: list[Path] = field(default_factory=list)
    set_window_hidden: Callable[[bool], None] | None = None  # Lets a tool hide the OPTIMUS window


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]