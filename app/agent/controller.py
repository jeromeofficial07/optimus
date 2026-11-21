"""
ExecutionController - runs actions and plans.

For every step:  execute (validate + permission + run + log)  ->  verify the effect
                 -> retry once if the effect was not confirmed (safe tools only)
                 -> apply the step's failure policy ("stop" or "continue")
At the end it returns an ExecutionReport that summarises everything.
"""
import json
from dataclasses import replace

from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.plan import ExecutionReport, Plan, PlanError, Step, StepResult, StepStatus
from app.agent.registry import Risk, ToolError, ToolResult
from app.agent.validator import validate_arguments
from app.agent.verifier import ResultVerifier, Verification
from app.config import MAX_STEP_ATTEMPTS


def _as_dict(raw) -> dict:
    """Tool arguments may arrive as a dict, a JSON string or nothing."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            return {}
    try:
        return dict(raw or {})
    except (TypeError, ValueError):
        return {}


def _annotate(result: ToolResult, verification: Verification):
    """Add the verification outcome to the result text (and flip it to failed if not confirmed)."""
    first, *rest = result.message.splitlines() or [""]
    if verification.ok is True:
        suffix = f" (verified: {verification.note})" if verification.note else " (verified)"
        result.message = "\n".join([first + suffix, *rest])
    elif verification.ok is False:
        result.ok = False
        result.message = f"{first} However, I could not confirm it worked: {verification.note}."


class ExecutionController:
    def __init__(self, executor: ToolExecutor, verifier: ResultVerifier, planner):
        self.executor = executor
        self.verifier = verifier
        self.planner = planner

    @property
    def registry(self):
        return self.executor.registry

    # ------------------------------------------------------------ single tool call
    def run_tool(self, name, raw_args, callbacks: ToolCallbacks) -> ToolResult:
        """A tool the AI chose during normal tool calling (Phase 5 path), now with verification."""
        if name == "run_workflow":
            return self._run_workflow_tool(raw_args, callbacks)
        result, _ = self._execute_verified(name, raw_args, callbacks)
        return result

    def _run_workflow_tool(self, raw_args, callbacks: ToolCallbacks) -> ToolResult:
        """The AI picked an approved workflow by name."""
        tool = self.registry.get("run_workflow")
        try:
            args = validate_arguments(tool, raw_args, self.executor.context.guard)
            plan = self.planner.from_workflow(args["name"])
            self.planner.validate(plan)
        except (ToolError, PlanError) as exc:
            result = ToolResult("run_workflow", False, f"Request rejected: {exc}")
            if callbacks.on_result:
                callbacks.on_result(result)
            return result
        report = self.run_plan(plan, callbacks)
        return ToolResult("run_workflow", report.succeeded, report.summary())

    # ------------------------------------------------------------ plans
    def run_plan(self, plan: Plan, callbacks: ToolCallbacks) -> ExecutionReport:
        """Run the steps strictly one after another."""
        total = len(plan.steps)
        results: list[StepResult] = []
        stopped = False
        for index, step in enumerate(plan.steps, start=1):
            if stopped:
                results.append(StepResult(step, StepStatus.SKIPPED,
                                          "Skipped because an earlier step did not succeed."))
                continue
            outcome = self._run_step(step, index, total, callbacks)
            results.append(outcome)
            if outcome.status is not StepStatus.OK and step.on_fail == "stop":
                stopped = True
        return ExecutionReport(plan, results)

    def _run_step(self, step: Step, index: int, total: int, callbacks: ToolCallbacks) -> StepResult:
        tool = self.registry.get(step.tool)
        # Only safe tools are retried: a sensitive step must never ask permission twice
        can_retry = tool is not None and tool.risk is Risk.SAFE
        attempts = 0
        while True:
            attempts += 1
            result, verification = self._execute_verified(
                step.tool, step.args, callbacks, prefix=f"Step {index}/{total}: ")
            if result.declined:
                return StepResult(step, StepStatus.DECLINED, result.message, attempts=attempts)
            if result.ok:
                return StepResult(step, StepStatus.OK, result.message,
                                  verified=verification.ok, attempts=attempts)
            if verification.ok is False and can_retry and attempts < MAX_STEP_ATTEMPTS:
                continue  # It ran but the effect was not confirmed: try once more
            return StepResult(step, StepStatus.FAILED, result.message, verified=verification.ok,
                              attempts=attempts)

    # ------------------------------------------------------------ shared
    def _execute_verified(self, name, raw_args, callbacks: ToolCallbacks, prefix: str = ""):
        """Execute, verify, annotate, and only then tell the GUI the final outcome."""
        on_start = callbacks.on_start
        quiet = replace(
            callbacks,
            on_result=None,  # We report after verification instead
            on_start=(lambda text: on_start(prefix + text)) if on_start else None,
        )
        result = self.executor.execute(name, raw_args, quiet)
        verification = Verification(None)
        if result.ok:
            verification = self.verifier.verify(name, _as_dict(raw_args), result)
            _annotate(result, verification)
        if callbacks.on_result:
            try:
                callbacks.on_result(result)
            except Exception:
                pass
        return result, verification