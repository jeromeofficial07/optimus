"""
TaskPlanner - creates plans.

  from_workflow(name)  -> a trusted, predefined plan
  from_llm(text)       -> the AI drafts a plan under a strict JSON schema
  validate(plan)       -> EVERY plan is checked against the registry before it can run

The AI can only choose among registered tools; code, not the model, decides
whether a plan is acceptable.
"""
from app.agent.path_guard import PathGuard
from app.agent.plan import Plan, PlanError, Step
from app.agent.registry import ToolError, ToolRegistry
from app.agent.validator import validate_arguments
from app.agent.workflows import WORKFLOWS
from app.config import MAX_PLAN_STEPS

_META_TOOLS = {"run_workflow"}  # Handled by the controller; never part of a drafted plan


class TaskPlanner:
    def __init__(self, registry: ToolRegistry, guard: PathGuard, llm=None):
        self.registry = registry
        self.guard = guard
        self._llm = llm  # Needs a generate_json(system, user, schema) method

    # ------------------------------------------------------------ workflows
    def from_workflow(self, name: str) -> Plan:
        workflow = WORKFLOWS.get(name)
        if workflow is None:
            raise PlanError(f"There is no approved workflow called '{name}'.")
        return workflow.builder()

    # ------------------------------------------------------------ AI-drafted plans
    def _tool_catalog(self) -> tuple[str, list[str]]:
        lines, names = [], []
        for schema in self.registry.schemas():
            function = schema["function"]
            if function["name"] in _META_TOOLS:
                continue
            names.append(function["name"])
            props = function["parameters"]["properties"]
            args = ", ".join(f"{n}: {p['type']}" for n, p in props.items())
            lines.append(f"- {function['name']}({args}): {function['description']}")
        return "\n".join(lines), names

    def from_llm(self, user_text: str) -> Plan:
        if self._llm is None:
            raise PlanError("No language model is available for planning.")
        catalog, names = self._tool_catalog()
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "steps": {
                    "type": "array",
                    "maxItems": MAX_PLAN_STEPS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "enum": names},
                            "arguments": {"type": "object"},
                            "description": {"type": "string"},
                        },
                        "required": ["tool", "arguments", "description"],
                    },
                },
            },
            "required": ["title", "steps"],
        }
        system = (
            "You are the task planner of a Windows desktop assistant. Break the user's request "
            f"into the fewest possible steps (at most {MAX_PLAN_STEPS}), in the order they must "
            "run, using ONLY the tools listed below with their exact names and argument names. "
            "Give each step a short plain-English description. If the request cannot be done "
            "with these tools, return an empty steps list.\n\nTools:\n" + catalog
        )
        try:
            data = self._llm.generate_json(system, user_text, schema)
            steps = [
                Step(tool=str(s["tool"]), args=dict(s.get("arguments") or {}),
                     description=str(s.get("description") or s["tool"]).strip())
                for s in data.get("steps", [])
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise PlanError(f"The model did not return a usable plan ({exc}).") from exc

        plan = Plan(title=str(data.get("title") or "Your request").strip()[:60],
                    steps=steps, source="llm")
        self.validate(plan)
        return plan

    # ------------------------------------------------------------ validation
    def validate(self, plan: Plan) -> Plan:
        """Reject a plan unless every step is a registered tool with valid, safe arguments."""
        if not plan.steps:
            raise PlanError("The plan has no steps.")
        if len(plan.steps) > MAX_PLAN_STEPS:
            raise PlanError(f"The plan has more than {MAX_PLAN_STEPS} steps.")
        for step in plan.steps:
            tool = self.registry.get(step.tool)
            if tool is None or tool.name in _META_TOOLS:
                raise PlanError(f"'{step.tool}' is not an approved action.")
            try:
                validate_arguments(tool, step.args, self.guard)
            except ToolError as exc:
                raise PlanError(f"The step '{step.description or step.tool}' is invalid: {exc}") from exc
        return plan