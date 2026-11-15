"""
Application tools. Only programs listed in APPS (config.py) can be opened or closed.
The launch target is a fixed string from that list, never text from the AI.
"""
import difflib
import os
import sys

import psutil

from app.agent.registry import ToolContext, ToolError
from app.config import APP_ALIASES, APPS

_LABELS = {"vs code": "VS Code"}


def _label(key: str) -> str:
    return _LABELS.get(key, key.title())


def _resolve_app(name: str) -> str:
    """Map what the user said ('the calc app') to an approved application key."""
    key = name.lower().strip()
    for prefix in ("the ", "my "):
        key = key.removeprefix(prefix)
    for suffix in (" app", " application", " program"):
        key = key.removesuffix(suffix)
    key = APP_ALIASES.get(key.strip(), key.strip())
    if key in APPS:
        return key
    # Forgive small spelling mistakes ("notpad")
    match = difflib.get_close_matches(key, list(APPS) + list(APP_ALIASES), n=1, cutoff=0.75)
    if match:
        found = APP_ALIASES.get(match[0], match[0])
        if found in APPS:
            return found
    raise ToolError(
        f"'{name}' is not on the approved application list. "
        f"Approved applications: {', '.join(_label(k) for k in sorted(APPS))}."
    )


def open_application(ctx: ToolContext, name: str) -> str:
    if sys.platform != "win32":
        raise ToolError("Opening applications is only supported on Windows.")
    key = _resolve_app(name)
    target = os.path.expandvars(APPS[key]["target"])
    try:
        os.startfile(target)  # Windows 'open' on a fixed, approved target. No shell involved.
    except OSError as exc:
        raise ToolError(f"Could not open {_label(key)}. It may not be installed ({exc}).") from exc
    return f"Opened {_label(key)}."


def close_application(ctx: ToolContext, name: str) -> str:
    key = _resolve_app(name)
    processes = APPS[key].get("process")
    if not processes:
        raise ToolError(f"For safety, OPTIMUS does not close {_label(key)}.")
    wanted = {p.lower() for p in processes}
    closed = 0
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() in wanted:
                proc.terminate()
                closed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if closed == 0:
        return f"{_label(key)} is not running."
    return f"Closed {_label(key)}."


def list_supported_apps(ctx: ToolContext) -> str:
    return "Approved applications: " + ", ".join(_label(k) for k in sorted(APPS)) + "."