"""
Data types for plans and execution reports.

Step            - one tool call with its arguments
Plan            - an ordered list of steps
StepResult      - what happened to one step
ExecutionReport - all results, with a readable summary
"""
from dataclasses import dataclass, field
from enum import Enum


class PlanError(Exception):
    """A plan could not be created or failed validation."""


@dataclass
class Step:
    tool: str
    args: dict = field(default_factory=dict)
    description: str = ""
    on_fail: str = "stop"        # "stop" = skip the remaining steps, "continue" = carry on


@dataclass
class Plan:
    title: str
    steps: list[Step]
    source: str = "workflow"     # "workflow" (trusted, predefined) or "llm" (drafted by the AI)


class StepStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    DECLINED = "declined"        # The user said no to a permission prompt
    SKIPPED = "skipped"          # An earlier step failed


@dataclass
class StepResult:
    step: Step
    status: StepStatus
    message: str
    verified: bool | None = None  # True / False / None (cannot be checked)
    attempts: int = 1


@dataclass
class ExecutionReport:
    plan: Plan
    results: list[StepResult]

    @property
    def succeeded(self) -> bool:
        return all(r.status is StepStatus.OK for r in self.results)

    def summary(self) -> str:
        """A readable Markdown summary: headline, one line per step, details underneath."""
        total = len(self.results)
        count = lambda status: sum(r.status is status for r in self.results)
        done = count(StepStatus.OK)

        if done == total:
            headline = f"**{self.plan.title}:** all {total} step{'s' if total != 1 else ''} completed."
        else:
            parts = [f"{done} of {total} steps completed"]
            for status, word in ((StepStatus.FAILED, "failed"), (StepStatus.DECLINED, "declined"),
                                 (StepStatus.SKIPPED, "skipped")):
                if count(status):
                    parts.append(f"{count(status)} {word}")
            headline = f"**{self.plan.title}:** " + ", ".join(parts) + "."

        lines = [headline, ""]
        for index, result in enumerate(self.results, start=1):
            first, *details = result.message.splitlines() or [""]
            what = result.step.description or result.step.tool
            if result.status is StepStatus.OK:
                extra = f" (worked on attempt {result.attempts})" if result.attempts > 1 else ""
                lines.append(f"{index}. **Done:** {first}{extra}")
            elif result.status is StepStatus.FAILED:
                lines.append(f"{index}. **Failed:** {what}. {first}")
            elif result.status is StepStatus.DECLINED:
                lines.append(f"{index}. **Declined:** {what}. You chose not to allow it.")
            else:
                lines.append(f"{index}. **Skipped:** {what}.")
            if result.status in (StepStatus.OK, StepStatus.FAILED):
                for detail in details[:6]:
                    if detail.strip():
                        lines.append(f"   - {detail.strip()}")
        return "\n".join(lines)