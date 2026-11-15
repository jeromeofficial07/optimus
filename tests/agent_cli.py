"""
Console chat WITH tools enabled. Permission prompts are asked in the console.
Run from the project root:   python -m tests.agent_cli
"""
from app.agent.executor import ToolCallbacks, ToolExecutor
from app.agent.path_guard import PathGuard
from app.agent.registry import ToolContext
from app.brain.ai_engine import AIEngine, AIEngineError
from app.config import SEARCH_DIRECTORIES
from app.tools.builtin import build_default_registry


def ask_permission(request) -> bool:
    answer = input(f"\n  [PERMISSION] {request.description}  Allow? (y/n): ").strip().lower()
    return answer in ("y", "yes")


def main():
    context = ToolContext(guard=PathGuard(SEARCH_DIRECTORIES))
    engine = AIEngine(executor=ToolExecutor(build_default_registry(), context))
    callbacks = ToolCallbacks(
        confirm=ask_permission,
        on_start=lambda text: print(f"\n  [running] {text}"),
        on_result=lambda r: print(f"  [{'ok' if r.ok else 'failed'}] "
                                  f"{r.message.splitlines()[0] if r.message else ''}"),
    )
    kind, message = engine.check_connection()
    print(f"[{kind}] {message}")
    if kind != "ok":
        return
    print("Try: 'open notepad', 'how is my cpu', 'lock my computer'. Type 'exit' to quit.\n")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("exit", "quit"):
            break
        if not text:
            continue
        print("OPTIMUS: ", end="", flush=True)
        try:
            for piece in engine.stream_reply(text, callbacks):
                print(piece, end="", flush=True)
        except AIEngineError as err:
            print(f"\n[{err.kind}] {err.message}")
        print("\n")


if __name__ == "__main__":
    main()