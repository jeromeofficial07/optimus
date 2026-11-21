"""
CommandRouter - understands memory, task and reminder requests with plain rules.

  "remember that my favorite color is blue"   "add task buy milk tomorrow at 9am"
  "my name is Jerome"                         "show my tasks"      "complete task 2"
  "forget about favorite color"               "remind me in 10 minutes to stretch"
  "what do you remember about me"             "show my reminders"  "cancel reminder 1"

handle() returns the reply text, or None if the message is not one of these commands
(so it continues to the AI). Every action still goes through ToolExecutor.
"""
import re
from dataclasses import replace

from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.timeparse import extract_time
from app.storage.database import DatabaseError
from app.storage.repositories import Storage

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10}
_FILLERS = {"to", "that", "about", "for", "at", "on", "in", "by", "due", "the", "a"}


def _to_number(text: str) -> int | None:
    text = text.strip().lower()
    return int(text) if text.isdigit() else _WORD_NUMBERS.get(text)


def _tidy(text: str) -> str:
    """Remove leftover connecting words such as 'to' or 'by' from the ends of a phrase."""
    words = text.strip(" ,.;:-").split()
    while words and words[0].lower() in _FILLERS:
        words.pop(0)
    while words and words[-1].lower() in _FILLERS:
        words.pop()
    return " ".join(words)


# (pattern, handler name, only for statements, not questions)
_RULES = [
    (r"^(?:please\s+)?remember(?:\s+that)?\s+(?!when\b|how\b|what\b|if\b|why\b)(?P<fact>.+)$", "_remember", True),
    (r"^(?:(?:hi|hello|hey)[,!.\s]+)?(?:my name is|call me)\s+(?P<name>[A-Za-z][A-Za-z'-]*)$", "_name", True),
    (r"^(?:please\s+)?forget(?:\s+(?:that|about))?\s+(?P<what>.+)$", "_forget", True),
    (r"^(?:what\s+(?:do|did)\s+you\s+(?:remember|know)(?:\s+about\s+me)?|(?:show|list)\s+(?:me\s+)?(?:my\s+)?memor(?:y|ies))$", "_list_memories", False),
    (r"^(?:please\s+)?(?:add|create|new)\s+(?:a\s+)?(?:new\s+)?(?:task|to-?do)\s*(?:to|:|called|named|for)?\s*(?P<title>.+)$", "_add_task", True),
    (r"^(?:please\s+)?(?:add|put)\s+(?P<title>.+?)\s+(?:to|on)\s+my\s+(?:task|to-?do|todo)(?:\s+list)?$", "_add_task", True),
    (r"^(?:please\s+)?(?:show|list|display|what(?:'s| is| are))\s+(?:me\s+)?(?:all\s+)?(?:my\s+)?(?:open\s+)?(?:tasks|to-?dos|todos|to-?do\s+list|todo\s+list)$", "_list_tasks", False),
    (r"^(?:please\s+)?(?:complete|finish|mark)\s+task\s+(?:number\s+|#)?(?P<n>\w+)(?:\s+as\s+(?:done|complete|completed))?$", "_complete_task", True),
    (r"^(?:please\s+)?mark\s+(?:task\s+)?(?:number\s+|#)?(?P<n>\w+)\s+(?:as\s+)?(?:done|complete|completed)$", "_complete_task", True),
    (r"^(?:please\s+)?(?:delete|remove)\s+task\s+(?:number\s+|#)?(?P<n>\w+)$", "_delete_task", True),
    (r"^(?:please\s+)?(?:remind me|set\s+(?:a\s+|an\s+)?reminder)\b(?P<rest>.*)$", "_add_reminder", True),
    (r"^(?:please\s+)?(?:show|list|display|what(?:'s| are))\s+(?:me\s+)?(?:my\s+)?(?:upcoming\s+)?reminders$", "_list_reminders", False),
    (r"^(?:please\s+)?(?:cancel|delete|remove)\s+reminder\s+(?:number\s+|#)?(?P<n>\w+)$", "_cancel_reminder", True),
]


class CommandRouter:
    def __init__(self, executor: ToolExecutor, storage: Storage):
        self.executor = executor
        self.storage = storage
        self._rules = [(re.compile(p, re.IGNORECASE), getattr(self, name), statement_only)
                       for p, name, statement_only in _RULES]

    def handle(self, text: str, callbacks: ToolCallbacks) -> str | None:
        original = text.strip()
        plain = original.rstrip(".!?, ").strip()
        is_question = original.endswith("?")
        for pattern, method, statement_only in self._rules:
            if statement_only and is_question:
                continue  # "Remember when we...?" is a question, not a command
            match = pattern.match(plain)
            if match:
                try:
                    return method(match, callbacks)
                except DatabaseError as exc:
                    return f"I couldn't reach my memory just now. {exc}"
        return None

    # ------------------------------------------------------------ helper
    def _call(self, tool: str, args: dict, callbacks: ToolCallbacks) -> str:
        """Run a tool through the executor and turn its result into a reply."""
        quiet = replace(callbacks, on_start=None, on_result=None)  # The reply itself is the feedback
        result = self.executor.execute(tool, args, quiet)
        if result.ok:
            return result.message
        if result.declined:
            return "Okay, I won't do that."
        return f"Sorry, that didn't work: {result.message}"

    # ------------------------------------------------------------ memory
    def _remember(self, match, cb):
        fact = match.group("fact").strip().rstrip(".")
        possessive = re.match(r"^my\s+(?P<k>.+?)\s+(?:is|are|was)\s+(?P<v>.+)$", fact, re.IGNORECASE)
        if possessive:
            key, value = possessive["k"], possessive["v"]
        else:
            key, value = " ".join(fact.split()[:6]), fact
        reply = self._call("remember_fact", {"key": key, "value": value}, cb)
        return f"Okay, I'll remember that {fact}." if reply.startswith("Remembered") else reply

    def _name(self, match, cb):
        name = match.group("name")
        name = name[:1].upper() + name[1:]
        reply = self._call("remember_fact", {"key": "name", "value": name, "category": "profile"}, cb)
        return f"Nice to meet you, {name}! I'll remember your name." if reply.startswith("Remembered") else reply

    def _forget(self, match, cb):
        matches = self.storage.memory.find(match.group("what"))
        if not matches:
            return "I don't have anything stored about that."
        return self._call("forget_fact", {"key": matches[0]["key"]}, cb)

    def _list_memories(self, match, cb):
        return self._call("list_memories", {}, cb)

    # ------------------------------------------------------------ tasks
    def _add_task(self, match, cb):
        title = match.group("title").strip()
        when, remainder = extract_time(title)
        cleaned = _tidy(remainder if when else title)
        if not cleaned:
            return "What should the task be?"
        args = {"title": cleaned}
        if when:
            args["due"] = when.strftime("%Y-%m-%d %H:%M")
        return self._call("add_task", args, cb)

    def _list_tasks(self, match, cb):
        return self._call("list_tasks", {}, cb)

    def _task_number(self, match, tool, cb):
        number = _to_number(match.group("n"))
        if number is None:
            return "Which number? For example: complete task 2."
        return self._call(tool, {"number": number}, cb)

    def _complete_task(self, match, cb):
        return self._task_number(match, "complete_task", cb)

    def _delete_task(self, match, cb):
        return self._task_number(match, "delete_task", cb)

    # ------------------------------------------------------------ reminders
    def _add_reminder(self, match, cb):
        when, remainder = extract_time((match.group("rest") or "").strip())
        if when is None:
            return "When should I remind you? For example: remind me in 10 minutes to stretch."
        message = _tidy(remainder) or "your reminder"
        return self._call("add_reminder",
                          {"text": message, "when": when.strftime("%Y-%m-%d %H:%M:%S")}, cb)

    def _list_reminders(self, match, cb):
        return self._call("list_reminders", {}, cb)

    def _cancel_reminder(self, match, cb):
        return self._task_number(match, "cancel_reminder", cb)