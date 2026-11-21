"""
Workspace tools. They only LAUNCH VS Code with a validated folder and READ files
to inspect the environment. Nothing from your project is ever executed.
"""
import os
import re
import subprocess
from pathlib import Path

from app.agent.registry import ToolContext, ToolError
from app.config import APPS, WORKSPACES

VENV_NAMES = ("venv", ".venv", "env")


def get_workspace(ctx: ToolContext, kind: str) -> str:
    entry = WORKSPACES.get(kind)
    if not entry:
        raise ToolError(f"No '{kind}' workspace is configured. Add one to WORKSPACES in config.py.")
    path = ctx.guard.resolve(str(entry["path"]))  # Must be inside an allowed folder
    if not path.is_dir():
        raise ToolError(f"The configured workspace folder does not exist: {path}")
    return f"Workspace '{entry.get('name', path.name)}' is at {path}"


def open_in_vscode(ctx: ToolContext, path: Path) -> str:
    if not path.is_dir():
        raise ToolError("VS Code can only be opened on a project folder here.")
    exe = Path(os.path.expandvars(APPS["vs code"]["target"]))
    if not exe.is_file():
        raise ToolError("Visual Studio Code was not found. Update the 'vs code' entry in APPS in config.py.")
    subprocess.Popen([str(exe), str(path)])  # List arguments: no shell, no command text
    return f"Opened the project {path.name} in VS Code."


# ---------------------------------------------------------------- environment check
def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _venv_python_version(venv: Path) -> str | None:
    """Read the Python version from pyvenv.cfg (a plain text file)."""
    try:
        for line in (venv / "pyvenv.cfg").read_text(encoding="utf-8", errors="ignore").splitlines():
            key, _, value = line.partition("=")
            if key.strip() in ("version", "version_info"):
                return value.strip()
    except OSError:
        pass
    return None


def _site_packages(venv: Path) -> Path | None:
    windows = venv / "Lib" / "site-packages"
    if windows.is_dir():
        return windows
    return next(iter(venv.glob("lib/python*/site-packages")), None)


def _installed_packages(site: Path) -> set[str]:
    """Package names from the *.dist-info folders (no code is imported or run)."""
    names = set()
    for entry in site.iterdir():
        if entry.name.endswith((".dist-info", ".egg-info")):
            names.add(_normalize(entry.name.rsplit("-", 1)[0]))
    return names


def _parse_requirements(path: Path) -> dict[str, str]:
    """requirements.txt -> {normalised name: display name}. Options and comments are ignored."""
    wanted = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name = re.split(r"[\s=<>!~;\[@]", line, maxsplit=1)[0]
        if name:
            wanted[_normalize(name)] = name
    return wanted


def check_python_environment(ctx: ToolContext, path: Path) -> str:
    if not path.is_dir():
        raise ToolError("The project folder does not exist.")
    problems: list[str] = []
    details: list[str] = []

    venv = next((path / n for n in VENV_NAMES if (path / n / "pyvenv.cfg").is_file()), None)
    version = None
    installed: set[str] = set()
    if venv is None:
        problems.append("no virtual environment found")
        details.append("No virtual environment found (looked for venv, .venv and env).")
    else:
        version = _venv_python_version(venv)
        details.append(f"Virtual environment: {venv.name}" + (f" (Python {version})" if version else ""))
        site = _site_packages(venv)
        installed = _installed_packages(site) if site else set()

    requirements = path / "requirements.txt"
    if requirements.is_file():
        wanted = _parse_requirements(requirements)
        if venv is not None:
            missing = sorted(name for key, name in wanted.items() if key not in installed)
            if missing:
                problems.append(f"{len(missing)} of {len(wanted)} required packages are not installed")
                details.append("Missing packages: " + ", ".join(missing[:10])
                               + (" and more" if len(missing) > 10 else ""))
            else:
                details.append(f"All {len(wanted)} packages in requirements.txt are installed.")
    else:
        details.append("No requirements.txt found.")
    details.append("Git repository: " + ("yes" if (path / ".git").exists() else "no"))

    if problems:
        head = "Environment check found issues: " + "; ".join(problems) + "."
    else:
        head = "Environment looks healthy" + (f" (Python {version})." if version else ".")
    return "\n".join([head, *details])