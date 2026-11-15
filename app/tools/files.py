"""
File tools: search the configured folders and open files or folders.

Opening is restricted by FILE TYPE as well as location: documents, images and media
open normally, plain-text and code files open in Notepad, and anything that could
execute (exe, bat, ps1, scripts, shortcuts, macro documents...) is refused.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from app.agent.registry import ToolContext, ToolError
from app.config import MAX_SEARCH_RESULTS, SEARCH_SKIP_DIRS, SEARCH_TIME_LIMIT

OPEN_WITH_DEFAULT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".rtf", ".odt",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
    ".mp3", ".wav", ".mp4", ".mkv", ".avi", ".mov", ".zip", ".html", ".htm",
}
OPEN_WITH_NOTEPAD = {
    ".txt", ".md", ".log", ".ini", ".cfg", ".toml", ".yaml", ".yml", ".xml", ".json",
    ".py", ".js", ".ts", ".css", ".sql",
}


def _score(name: str, tokens: list[str]) -> int:
    """Lower is better: exact name, then starts-with, then contains."""
    stem = name.rsplit(".", 1)[0]
    if stem == " ".join(tokens):
        return 0
    return 1 if name.startswith(tokens[0]) else 2


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def search_files(ctx: ToolContext, query: str, kind: str = "any") -> str:
    tokens = [t for t in re.split(r"\W+", query.lower()) if t]
    if not tokens:
        raise ToolError("Please tell me what to search for.")
    if not ctx.guard.roots:
        raise ToolError("No search folders are configured. See SEARCH_DIRECTORIES in config.py.")

    deadline = time.monotonic() + SEARCH_TIME_LIMIT
    matches: list[tuple[int, float, Path]] = []
    timed_out = False

    for root in ctx.guard.roots:
        for current, dirs, files in os.walk(root):
            # Prune folders we never want to search (modifying 'dirs' in place skips them)
            dirs[:] = [d for d in dirs if d.lower() not in SEARCH_SKIP_DIRS and not d.startswith(".")]
            names = []
            if kind in ("any", "folder"):
                names += dirs
            if kind in ("any", "file"):
                names += [f for f in files if not f.startswith((".", "~$"))]
            for name in names:
                lowered = name.lower()
                if all(token in lowered for token in tokens):
                    path = Path(current) / name
                    matches.append((_score(lowered, tokens), -_mtime(path), path))
            if time.monotonic() > deadline or len(matches) > 500:
                timed_out = time.monotonic() > deadline
                break
        else:
            continue
        break

    matches.sort(key=lambda item: (item[0], item[1]))
    top = [path for _, _, path in matches[:MAX_SEARCH_RESULTS]]
    if not top:
        return f"No matches for '{query}' in the configured folders."

    ctx.last_search_results = top  # So "open the second one" works next
    lines = [f"Found {len(top)} match{'es' if len(top) != 1 else ''} for '{query}':"]
    lines += [f"{i}. {p.name}   ({p.parent})" for i, p in enumerate(top, 1)]
    if timed_out:
        lines.append(f"(The search stopped after {SEARCH_TIME_LIMIT} seconds, so it may be incomplete.)")
    lines.append("To open one, use open_search_result with its number.")
    return "\n".join(lines)


def _open_item(path: Path) -> str:
    if sys.platform != "win32":
        raise ToolError("Opening files is only supported on Windows.")
    if not path.exists():
        raise ToolError(f"'{path.name}' does not exist.")
    if path.is_dir():
        os.startfile(str(path))  # Opens the folder in File Explorer
        return f"Opened the folder {path.name}."
    ext = path.suffix.lower()
    if ext in OPEN_WITH_NOTEPAD:
        subprocess.Popen(["notepad.exe", str(path)])  # List arguments, no shell
        return f"Opened {path.name} in Notepad."
    if ext in OPEN_WITH_DEFAULT:
        os.startfile(str(path))
        return f"Opened {path.name}."
    raise ToolError(
        f"For safety, OPTIMUS does not open '{ext or 'this type of'}' files. "
        "It only opens documents, images, media and plain-text files."
    )


def open_path(ctx: ToolContext, path: Path) -> str:
    return _open_item(path)  # 'path' was already validated by PathGuard


def open_search_result(ctx: ToolContext, number: int) -> str:
    if not ctx.last_search_results:
        raise ToolError("There are no search results yet. Search for something first.")
    if not 1 <= number <= len(ctx.last_search_results):
        raise ToolError(f"Please choose a number between 1 and {len(ctx.last_search_results)}.")
    chosen = ctx.last_search_results[number - 1]
    return _open_item(ctx.guard.resolve(str(chosen)))  # Re-check the path, to be safe