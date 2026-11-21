"""A tiny JSON file for small bits of state (for example, the date of the last daily briefing)."""
import json

from app.config import DATA_DIR

_PATH = DATA_DIR / "state.json"


def load_state() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict):
    try:
        temporary = _PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(_PATH)  # Atomic: a crash never leaves a half-written file
    except OSError:
        pass