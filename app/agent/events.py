"""
Small shared types for the agent: permission requests and the callbacks the
GUI uses to follow what the agent is doing.
"""
from collections.abc import Callable
from dataclasses import dataclass

from app.agent.registry import Risk, ToolResult


@dataclass
class ConfirmationRequest:
    tool: str
    title: str
    description: str
    risk: Risk


@dataclass
class ToolCallbacks:
    """Hooks the GUI uses. All are optional."""
    confirm: Callable[[ConfirmationRequest], bool] | None = None  # Ask the user; True = allowed
    on_start: Callable[[str], None] | None = None                 # "Step 2/4: Opening VS Code..."
    on_result: Callable[[ToolResult], None] | None = None


class SafeDict(dict):
    """For str.format_map: unknown {placeholders} stay as they are instead of raising an error."""

    def __missing__(self, key):
        return "{" + key + "}"