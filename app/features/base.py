"""
Feature framework.

A Feature is an independent module that adds:
  * tools   (registered in the shared registry, so they get validation, permissions and the audit log)
  * rules   (plain-language patterns that trigger it, answered without involving the AI's judgement)

Features run their tools THROUGH the agent controller via self.call().
"""
import re
from dataclasses import dataclass, replace
from typing import Any, Callable

from app.agent.events import ToolCallbacks
from app.agent.registry import HIDDEN_FROM_MODEL, Tool, ToolContext, ToolRegistry, ToolResult


@dataclass
class Services:
    """Everything a feature may use."""
    storage: Any                       # Storage, or None if the database is unavailable
    registry: ToolRegistry
    controller: Any                    # ExecutionController
    context: ToolContext
    llm: Any = None                    # Engine with stream_with_system(system, user)
    ui: Callable[[str], None] = lambda action: None   # Ask the GUI to do something (used in part 8B)


@dataclass
class Rule:
    pattern: re.Pattern
    handler: Callable                  # handler(match, callbacks) -> str | iterator of str
    guard: Callable[[str], bool] | None = None   # Extra check on the whole message
    statement_only: bool = False       # Ignore if the message is a question


def rule(pattern: str, handler, guard=None, statement_only: bool = False) -> Rule:
    return Rule(re.compile(pattern, re.IGNORECASE), handler, guard, statement_only)


class Feature:
    name = "feature"

    def __init__(self, services: Services):
        self.s = services

    def register_tools(self):
        """Add this feature's tools to the registry."""

    def rules(self) -> list[Rule]:
        return []

    def add_tool(self, tool: Tool):
        self.s.registry.register(tool)
        HIDDEN_FROM_MODEL.add(tool.name)   # Run by rules, not offered to the small model

    def call(self, tool: str, args: dict, callbacks: ToolCallbacks) -> ToolResult:
        """Run a tool through the agent controller (validate, permission, run, verify, audit)."""
        quiet = replace(callbacks, on_result=None)  # The reply itself is the feedback
        return self.s.controller.run_tool(tool, args, quiet)