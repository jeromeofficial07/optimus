"""
Workflow automation: your own multi-step routines, defined in data/workflows.json.

Every step must be a registered tool, and every workflow is validated with the SAME rules as
built-in plans (unknown tools, bad arguments and unsafe paths are rejected). Permission prompts
still apply, so a workflow can never do anything you could not do by hand.
Say "list my workflows" or "reload workflows" after editing the file.
"""
import copy
import json
import re

from app.agent.plan import Plan, PlanError, Step
from app.agent.registry import Tool, ToolContext
from app.agent.workflows import WORKFLOWS, Workflow
from app.config import DATA_DIR, MAX_PLAN_STEPS
from app.features.base import Feature, rule

WORKFLOWS_FILE = DATA_DIR / "workflows.json"

DEFAULT_FILE = {
    "workflows": [
        {"name": "start_my_day", "title": "Start my day",
         "description": "Show the daily briefing and open VS Code",
         "triggers": ["start my day", "morning routine"],
         "steps": [{"tool": "daily_briefing", "description": "Show the daily briefing"},
                   {"tool": "open_application", "args": {"name": "vs code"},
                    "description": "Open Visual Studio Code", "on_fail": "continue"}]},
        {"name": "end_of_day", "title": "End of day",
         "description": "Review open tasks and check the computer",
         "triggers": ["end my day", "wrap up the day"],
         "steps": [{"tool": "list_tasks", "description": "Review open tasks"},
                   {"tool": "get_system_usage", "description": "Check the computer", "on_fail": "continue"}]},
    ]
}


def _build(entry: dict, planner) -> tuple[Workflow, list[str]]:
    """Turn one JSON entry into a Workflow, or raise an error that says what is wrong."""
    name = str(entry["name"]).strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,40}", name):
        raise ValueError("the name must be 3 to 40 letters, digits or underscores")
    description = str(entry.get("description") or name)
    title = str(entry.get("title") or name.replace("_", " ").title())
    phrases = [str(p).strip().lower() for p in entry.get("triggers", []) if str(p).strip()]
    if not phrases or any(len(p) < 4 for p in phrases):
        raise ValueError("it needs at least one trigger phrase of 4 or more characters")
    raw_steps = entry.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("it needs a list of steps")
    steps = [{"tool": str(s["tool"]), "args": dict(s.get("args") or {}),
              "description": str(s.get("description") or s["tool"]),
              "on_fail": str(s.get("on_fail", "stop")).lower()} for s in raw_steps]
    if any(s["on_fail"] not in ("stop", "continue") for s in steps):
        raise ValueError("on_fail must be 'stop' or 'continue'")
    if len(steps) > MAX_PLAN_STEPS:
        raise ValueError(f"a workflow can have at most {MAX_PLAN_STEPS} steps")

    def builder() -> Plan:   # A fresh Plan each time, so runs never share state
        return Plan(title, [Step(s["tool"], copy.deepcopy(s["args"]), s["description"], s["on_fail"])
                            for s in steps])

    planner.validate(builder())   # Same checks as every other plan
    return Workflow(name, description, tuple(r"\b" + re.escape(p) + r"\b" for p in phrases), builder), phrases


class WorkflowFeature(Feature):
    name = "workflow automation"

    def __init__(self, services):
        super().__init__(services)
        self.loaded: list[str] = []
        self.phrases: dict[str, list[str]] = {}
        self.problems: list[str] = []

    def register_tools(self):
        self.add_tool(Tool("list_workflows", "List the available workflows.", lambda ctx: self._describe(),
                           status_text="Listing workflows..."))
        self.add_tool(Tool("reload_workflows", "Reload data/workflows.json.", lambda ctx: self.load(),
                           status_text="Reloading workflows..."))
        self.load()   # Registered last, so every tool a workflow may use already exists

    def _read(self) -> dict:
        if not WORKFLOWS_FILE.exists():
            WORKFLOWS_FILE.write_text(json.dumps(DEFAULT_FILE, indent=2), encoding="utf-8")
            return copy.deepcopy(DEFAULT_FILE)
        try:
            data = json.loads(WORKFLOWS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            self.problems.append(f"workflows.json could not be read: {exc}")
            return {}

    def load(self) -> str:
        for name in self.loaded:                 # Forget the previous custom workflows
            WORKFLOWS.pop(name, None)
        self.loaded, self.phrases, self.problems = [], {}, []
        planner = self.s.controller.planner
        for entry in self._read().get("workflows", []):
            label = entry.get("name", "?") if isinstance(entry, dict) else "?"
            try:
                workflow, phrases = _build(entry, planner)
                if workflow.name in WORKFLOWS:
                    raise ValueError("a workflow with this name already exists")
            except (KeyError, TypeError, ValueError, PlanError, AttributeError) as exc:
                self.problems.append(f"{label}: {exc}")
                continue
            WORKFLOWS[workflow.name] = workflow
            self.loaded.append(workflow.name)
            self.phrases[workflow.name] = phrases
        text = f"Loaded {len(self.loaded)} custom workflow{'s' if len(self.loaded) != 1 else ''}."
        return text + ("" if not self.problems else " Problems: " + " | ".join(self.problems))

    def _describe(self) -> str:
        lines = ["Workflows you can run by saying their phrase:"]
        for name, workflow in WORKFLOWS.items():
            if name in self.phrases:
                phrases = "; ".join(f"'{p}'" for p in self.phrases[name])
                lines.append(f"- {name} (custom): {workflow.description}. Say: {phrases}")
            else:
                lines.append(f"- {name} (built-in): {workflow.description}")
        lines += [f"Problem: {p}" for p in self.problems]
        lines.append(f"Edit {WORKFLOWS_FILE} and say 'reload workflows' to change them.")
        return "\n".join(lines)

    def rules(self):
        return [rule(r"^(?:please\s+)?(?:list|show)\s+(?:my\s+)?(?:custom\s+)?workflows$", self._list),
                rule(r"^(?:please\s+)?reload\s+(?:my\s+)?workflows$", self._reload)]

    def _list(self, match, cb):
        return self.call("list_workflows", {}, cb).message

    def _reload(self, match, cb):
        return self.call("reload_workflows", {}, cb).message