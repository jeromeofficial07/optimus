"""
Approved workflows: predefined, trusted plans for common goals.
To add one: write a builder function that returns a Plan, then list it in WORKFLOWS
with the phrases that should trigger it. Every step must be a registered tool.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass

from app.agent.plan import Plan, PlanError, Step
from app.config import WORKSPACES


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    triggers: tuple[str, ...]        # Regular expressions that recognise a request for it
    builder: Callable[[], Plan]

    def matches(self, text: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.triggers)


def _python_workspace() -> Plan:
    entry = WORKSPACES.get("python")
    if not entry:
        raise PlanError("No Python workspace is configured. Add one to WORKSPACES in config.py.")
    path = str(entry["path"])
    name = entry.get("name", "the project")
    return Plan("Prepare Python workspace", [
        Step("get_workspace", {"kind": "python"}, "Identify the configured Python workspace"),
        Step("open_application", {"name": "vs code"}, "Open Visual Studio Code"),
        Step("open_in_vscode", {"path": path}, f"Open the project {name} in VS Code"),
        Step("check_python_environment", {"path": path}, "Check the project environment",
             on_fail="continue"),
    ])


def _system_check() -> Plan:
    return Plan("System health check", [
        Step("get_system_usage", {}, "Check CPU, memory and disk", on_fail="continue"),
        Step("get_battery_status", {}, "Check the battery", on_fail="continue"),
    ])


WORKFLOWS: dict[str, Workflow] = {
    "prepare_python_workspace": Workflow(
        name="prepare_python_workspace",
        description="Open VS Code with the configured Python project and check its environment.",
        triggers=(
            r"\b(prepare|set\s?up|setup|get)\b.{0,40}\b(python|coding|development|dev)\b.{0,30}\b(workspace|environment|setup)\b",
            r"\bstart\b.{0,20}\b(coding|development session|dev session)\b",
            r"\bopen\b.{0,20}\b(python|dev|development)\s+workspace\b",
        ),
        builder=_python_workspace,
    ),
    "system_check": Workflow(
        name="system_check",
        description="Report CPU, memory, disk and battery in one go.",
        triggers=(
            r"\b(system|computer|pc|laptop)\s+(health|check|status|report)\b",
            r"\bhow is my (computer|pc|laptop) doing\b",
        ),
        builder=_system_check,
    ),
}