"""
Safety and tool tests WITHOUT the AI model.
Run from the project root:   python -m tests.tools_cli
"""
from app.agent.executor import ToolCallbacks, ToolExecutor
from app.agent.path_guard import PathGuard
from app.agent.registry import ToolContext
from app.config import DATA_DIR, SEARCH_DIRECTORIES
from app.tools.builtin import build_default_registry

passed = failed = 0


def check(label: str, result, expect_ok: bool, show_all: bool = False):
    global passed, failed
    good = result.ok == expect_ok
    passed += good
    failed += not good
    first = result.message.splitlines()[0] if result.message else ""
    print(f"[{'PASS' if good else 'FAIL'}] {label}\n         -> {first}")
    if show_all and result.message.count("\n"):
        print("\n".join("            " + line for line in result.message.splitlines()[1:]))


def main():
    context = ToolContext(guard=PathGuard(SEARCH_DIRECTORIES))
    run = ToolExecutor(build_default_registry(), context).execute
    deny = ToolCallbacks(confirm=lambda request: False)
    print("Allowed folders:", [str(r) for r in context.guard.roots], "\n")

    print("--- things that MUST be refused ---")
    check("unknown tool 'format_disk'", run("format_disk", {}), False)
    check("shell injection in an app name", run("open_application", {"name": "notepad && del *.*"}), False)
    check("path outside allowed folders", run("open_path", {"path": r"C:\Windows\System32\cmd.exe"}), False)
    check("path traversal with ..", run("open_path", {"path": str(DATA_DIR / ".." / ".." / ".." / "Windows" / "notepad.exe")}), False)
    check("network path", run("open_path", {"path": r"\\server\share\file.txt"}), False)

    bat = DATA_DIR / "blocked_test.bat"
    bat.write_text("echo test")
    check("executable file type (.bat)", run("open_path", {"path": str(bat)}), False)
    bat.unlink()

    check("lock computer, user says NO", run("lock_computer", {}, deny), False)
    check("close Notepad, user says NO", run("close_application", {"name": "notepad"}, deny), False)

    print("\n--- things that should work ---")
    check("system usage", run("get_system_usage", {}), True)
    check("battery", run("get_battery_status", {}), True)
    check("list apps", run("list_supported_apps", {}), True)
    check("search 'optimus'", run("search_files", {"query": "optimus"}), True, show_all=True)
    check("take screenshot", run("take_screenshot", {}), True)
    check("open Notepad (a window should appear)", run("open_application", {"name": "notepad"}), True)

    print(f"\n{passed} passed, {failed} failed.  Audit log: logs\\actions.log")


if __name__ == "__main__":
    main()