"""
Phase 6 tests WITHOUT the AI model:
  1) intent recognition on sample sentences
  2) failure handling and permission handling inside plans
  3) the real 'prepare Python workspace' workflow (opens VS Code)
Run from the project root:   python -m tests.workflow_cli
"""
from app.agent.agent import Agent
from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.intent import IntentKind, recognize_intent
from app.agent.path_guard import PathGuard
from app.agent.plan import Plan, Step
from app.agent.registry import ToolContext
from app.config import SEARCH_DIRECTORIES
from app.tools.builtin import build_default_registry

SAMPLES = [
    ("Prepare my Python development workspace.", IntentKind.WORKFLOW),
    ("set up my dev environment", IntentKind.WORKFLOW),
    ("start coding", IntentKind.WORKFLOW),
    ("give me a system health check", IntentKind.WORKFLOW),
    ("open notepad and then take a screenshot", IntentKind.MULTI_STEP),
    ("open notepad", IntentKind.ACTION),
    ("how much battery do I have", IntentKind.ACTION),
    ("tell me a joke", IntentKind.CHAT),
    ("hello, how are you?", IntentKind.CHAT),
]


def main():
    print("--- 1. intent recognition ---")
    for text, expected in SAMPLES:
        intent = recognize_intent(text)
        mark = "PASS" if intent.kind is expected else "FAIL"
        extra = f" ({intent.workflow})" if intent.workflow else ""
        print(f"[{mark}] {text!r} -> {intent.kind.value}{extra}")

    context = ToolContext(guard=PathGuard(SEARCH_DIRECTORIES))
    agent = Agent(ToolExecutor(build_default_registry(), context))
    callbacks = ToolCallbacks(
        confirm=lambda request: False,  # Deny every permission prompt in this test
        on_start=lambda text: print(f"   [running] {text}"),
        on_result=lambda r: print(f"   [{'ok' if r.ok else 'failed'}] {r.message.splitlines()[0]}"),
    )

    print("\n--- 2a. a failing step stops the plan, later steps are skipped ---")
    demo = Plan("Failure handling demo", [
        Step("get_system_usage", {}, "Check CPU and memory"),
        Step("open_application", {"name": "definitely not an app"}, "Open an application that does not exist"),
        Step("get_battery_status", {}, "Check the battery"),
    ])
    print(agent.controller.run_plan(demo, callbacks).summary())

    print("\n--- 2b. a sensitive step is declined (permission denied) ---")
    locked = Plan("Permission demo", [Step("lock_computer", {}, "Lock the computer")])
    print(agent.controller.run_plan(locked, callbacks).summary())

    print("\n--- 3. the real workspace workflow ---")
    if input("Run it now? This opens VS Code. (y/n): ").strip().lower() in ("y", "yes"):
        plan = agent.planner.from_workflow("prepare_python_workspace")
        agent.planner.validate(plan)
        print(agent.controller.run_plan(plan, callbacks).summary())


if __name__ == "__main__":
    main()