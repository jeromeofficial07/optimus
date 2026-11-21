"""
PermissionManager - the one place that decides what needs the user's approval.

  * SAFE tools run immediately.
  * SENSITIVE and DESTRUCTIVE tools always ask first, every time.
  * A plan drafted by the AI (not a trusted workflow) with 2+ steps is shown to the
    user for approval before anything runs.
"""
from app.agent.events import ConfirmationRequest, SafeDict, ToolCallbacks
from app.agent.plan import Plan
from app.agent.registry import Risk, Tool
from app.config import REQUIRE_PLAN_APPROVAL


class PermissionManager:
    def needs_confirmation(self, tool: Tool) -> bool:
        return tool.risk is not Risk.SAFE

    def authorize(self, tool: Tool, args: dict, callbacks: ToolCallbacks | None) -> bool:
        """True if the tool may run now (asking the user if it is sensitive)."""
        if not self.needs_confirmation(tool):
            return True
        request = ConfirmationRequest(
            tool=tool.name,
            title="Permission needed" if tool.risk is Risk.SENSITIVE else "Warning: permission needed",
            description=tool.confirm_text.format_map(SafeDict(args)) or tool.description,
            risk=tool.risk,
        )
        return self._ask(request, callbacks)

    def authorize_plan(self, plan: Plan, callbacks: ToolCallbacks | None) -> bool:
        """Ask the user to approve a plan that the AI drafted."""
        if plan.source != "llm" or len(plan.steps) < 2 or not REQUIRE_PLAN_APPROVAL:
            return True
        steps = "\n".join(f"{i}. {s.description or s.tool}" for i, s in enumerate(plan.steps, 1))
        request = ConfirmationRequest(
            tool="plan",
            title="Approve this plan?",
            description=f"I plan to do the following:\n{steps}\n\nRun it?",
            risk=Risk.SENSITIVE,
        )
        return self._ask(request, callbacks)

    @staticmethod
    def _ask(request: ConfirmationRequest, callbacks: ToolCallbacks | None) -> bool:
        if callbacks is None or callbacks.confirm is None:
            return False  # Nobody to ask means no permission
        try:
            return bool(callbacks.confirm(request))
        except Exception:
            return False