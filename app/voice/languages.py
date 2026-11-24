"""
Language helpers: which languages are configured, which have a voice installed,
script-based detection for typed text, and the saved language preference.
"""
from app.config import LANGUAGES, PIPER_DIR, PIPER_MODEL_PATH
from app.features.state import load_state, save_state

_NAME_TO_CODE = {info["name"].lower(): code for code, info in LANGUAGES.items()}

# (language code, first and last Unicode code point of its writing system)
_SCRIPTS = [("hi", 0x0900, 0x097F), ("bn", 0x0980, 0x09FF), ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F),
            ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F), ("ar", 0x0600, 0x06FF), ("ru", 0x0400, 0x04FF),
            ("zh", 0x4E00, 0x9FFF), ("ja", 0x3040, 0x30FF), ("ko", 0xAC00, 0xD7AF)]


def resolve_language(text: str) -> str | None:
    """'Spanish' -> 'es', 'auto' -> 'auto', unknown -> None."""
    word = text.strip().lower()
    if word in ("auto", "automatic", "detect", "any"):
        return "auto"
    return word if word in LANGUAGES else _NAME_TO_CODE.get(word)


def language_name(code: str) -> str:
    return LANGUAGES.get(code, {}).get("name", code)


def voice_path(code: str):
    if code == "en":
        return PIPER_MODEL_PATH
    voice = LANGUAGES.get(code, {}).get("voice")
    return PIPER_DIR / f"{voice}.onnx" if voice else None


def voice_installed(code: str) -> bool:
    path = voice_path(code)
    return bool(path and path.exists())


def detect_script_language(text: str) -> str | None:
    """Typed text in a non-Latin script identifies its language. Latin text is not guessed (None)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return None
    for code, low, high in _SCRIPTS:
        if code in LANGUAGES and sum(low <= ord(c) <= high for c in letters) / len(letters) >= 0.3:
            return code
    return None


def reply_instruction(code: str) -> str:
    """Extra system-prompt text telling the AI which language to answer in."""
    if code == "en" or code not in LANGUAGES:
        return ""
    name = language_name(code)
    return f"\nThe user is speaking {name}. Reply in {name}, using short sentences."


class LanguageState:
    """The language preference: 'auto' (detect it) or a fixed language code. Saved between sessions."""

    def __init__(self, persist: bool = True):
        self._persist = persist
        stored = load_state().get("language", "auto") if persist else "auto"
        self._value = stored if stored == "auto" or stored in LANGUAGES else "auto"

    @property
    def preference(self) -> str:
        return self._value

    def set(self, value: str):
        self._value = value
        if self._persist:
            state = load_state()
            state["language"] = value
            save_state(state)


LANG = LanguageState()