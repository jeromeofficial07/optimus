"""
Language commands:
    "switch language to Spanish"   "reply in French"   "speak in auto"   "list languages"
"""
from app.agent.registry import Param, Tool, ToolContext, ToolError
from app.config import LANGUAGES, MULTILINGUAL_ENABLED
from app.features.base import Feature, rule
from app.voice.languages import LANG, language_name, resolve_language, voice_installed


def set_language(ctx: ToolContext, language: str) -> str:
    if not MULTILINGUAL_ENABLED:
        raise ToolError("Multilingual mode is off. Set MULTILINGUAL_ENABLED = True in config.py "
                        "and follow the Phase 8B setup steps.")
    code = resolve_language(language)
    if code is None:
        names = ", ".join(info["name"] for info in LANGUAGES.values())
        raise ToolError(f"I don't know the language '{language}'. Available: {names}, or 'auto'.")
    LANG.set(code)
    if code == "auto":
        return "Language set to automatic detection. I will answer in the language you speak."
    note = ("I can speak it aloud." if voice_installed(code)
            else "I have no voice installed for it, so I will show text only.")
    return f"Language set to {language_name(code)}. {note}"


def list_languages(ctx: ToolContext) -> str:
    lines = [f"Languages (current setting: {LANG.preference}):"]
    for code, info in LANGUAGES.items():
        voice = "voice installed" if voice_installed(code) else "no voice installed (text only)"
        lines.append(f"- {info['name']}: {voice}")
    lines.append("Multilingual mode is " + ("on." if MULTILINGUAL_ENABLED else "off (see config.py)."))
    return "\n".join(lines)


class LanguageFeature(Feature):
    name = "multilingual voice"

    def register_tools(self):
        self.add_tool(Tool("set_language", "Set the language OPTIMUS listens for and answers in.", set_language,
                           (Param("language", "string", "A language name or 'auto'", max_length=30),),
                           status_text="Changing the language..."))
        self.add_tool(Tool("list_languages", "List the available languages.", list_languages,
                           status_text="Checking languages..."))

    def rules(self):
        return [
            rule(r"^(?:please\s+)?(?:switch|change|set)\s+(?:the\s+)?(?:voice\s+|speech\s+)?language\s+(?:to\s+)?"
                 r"(?P<lang>[a-z]+)$", self._set),
            rule(r"^(?:please\s+)?(?:speak|talk|reply|answer|respond)\s+(?:to\s+me\s+)?in\s+(?P<lang>[a-z]+)$", self._set),
            rule(r"^(?:(?:what|which)\s+languages\s+(?:do\s+you|can\s+you)\s+(?:speak|support|understand)|"
                 r"(?:list|show)\s+(?:the\s+)?languages)$", self._list),
        ]

    def _set(self, match, cb):
        result = self.call("set_language", {"language": match["lang"]}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"

    def _list(self, match, cb):
        return self.call("list_languages", {}, cb).message