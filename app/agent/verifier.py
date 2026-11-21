"""
ResultVerifier - checks that an action really had the effect it claimed.

A tool saying "opened Notepad" is not proof. For tools where the effect can be
observed (a process is running, a file exists) we look for ourselves.
Verification returns True (confirmed), False (not confirmed) or None (cannot be checked).
"""
import re
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.agent.registry import ToolContext, ToolResult
from app.config import APPS, VERIFY_TIMEOUT
from app.tools.apps import _resolve_app as resolve_app


@dataclass
class Verification:
    ok: bool | None
    note: str = ""


def _running_process_names() -> set[str]:
    names = set()
    for proc in psutil.process_iter(["name"]):
        try:
            names.add((proc.info["name"] or "").lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return names


def _wait_for(process_names, present: bool, timeout: float) -> bool:
    """Wait until one of the processes is running (present=True) or all are gone (False)."""
    wanted = {n.lower() for n in process_names}
    deadline = time.monotonic() + timeout
    while True:
        if bool(wanted & _running_process_names()) == present:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.4)


def _verify_app_running(ctx: ToolContext, args: dict, result: ToolResult) -> Verification:
    key = resolve_app(str(args.get("name", "")))
    processes = APPS[key].get("process")
    if not processes:
        return Verification(None)
    if _wait_for(processes, True, VERIFY_TIMEOUT):
        return Verification(True, "it is running")
    return Verification(False, f"{key} did not appear to start")


def _verify_vscode_running(ctx: ToolContext, args: dict, result: ToolResult) -> Verification:
    if _wait_for(APPS["vs code"]["process"], True, VERIFY_TIMEOUT):
        return Verification(True, "VS Code is running")
    return Verification(False, "VS Code did not appear to start")


def _verify_app_closed(ctx: ToolContext, args: dict, result: ToolResult) -> Verification:
    if "not running" in result.message.lower():
        return Verification(True, "it was not running")
    key = resolve_app(str(args.get("name", "")))
    processes = APPS[key].get("process") or []
    if processes and _wait_for(processes, False, 4):
        return Verification(True, "it has closed")
    return Verification(False, f"{key} is still running")


def _verify_screenshot(ctx: ToolContext, args: dict, result: ToolResult) -> Verification:
    match = re.search(r"saved to (.+)$", result.message.strip(), re.MULTILINE)
    if not match:
        return Verification(None)
    path = Path(match.group(1).strip())
    if path.is_file() and path.stat().st_size > 0:
        return Verification(True, "image file saved")
    return Verification(False, "the image file was not created")


_VERIFIERS = {
    "open_application": _verify_app_running,
    "open_in_vscode": _verify_vscode_running,
    "close_application": _verify_app_closed,
    "take_screenshot": _verify_screenshot,
}


class ResultVerifier:
    def __init__(self, context: ToolContext):
        self.context = context

    def verify(self, tool_name: str, args: dict, result: ToolResult) -> Verification:
        check = _VERIFIERS.get(tool_name)
        if check is None:
            return Verification(None)
        try:
            return check(self.context, args, result)
        except Exception as exc:  # A broken check must never break the action itself
            return Verification(None, f"verification skipped ({exc})")