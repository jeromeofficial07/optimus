"""
Natural language file search. Understands requests such as:
    "find the marketing pdf"                  "find spreadsheets modified yesterday"
    "files bigger than 50 mb in downloads"    "show me python files from last week"
No AI is involved: the request is parsed with rules, so it is fast and predictable.
"""
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.agent.registry import Param, Tool, ToolContext, ToolError
from app.config import MAX_SEARCH_RESULTS, SEARCH_SKIP_DIRS
from app.features.base import Feature, rule

_TYPES = {
    ("pdf", "pdfs"): {".pdf"},
    ("word", "docx", "doc"): {".doc", ".docx"},
    ("document", "documents"): {".doc", ".docx", ".pdf", ".txt", ".odt", ".rtf"},
    ("excel", "spreadsheet", "spreadsheets", "xlsx", "xls", "csv", "sheet", "sheets"): {".xls", ".xlsx", ".csv"},
    ("powerpoint", "presentation", "presentations", "slides", "pptx", "ppt", "deck"): {".ppt", ".pptx"},
    ("image", "images", "photo", "photos", "picture", "pictures", "png", "jpg", "jpeg",
     "screenshot", "screenshots"): {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"},
    ("python", "py"): {".py"},
    ("text", "txt", "note", "notes"): {".txt", ".md"},
    ("video", "videos", "mp4", "movie", "movies"): {".mp4", ".mkv", ".avi", ".mov"},
    ("music", "audio", "mp3", "song", "songs"): {".mp3", ".wav", ".flac", ".m4a"},
    ("zip", "archive", "archives"): {".zip", ".rar", ".7z"},
}
_WORD_TO_EXTS = {word: exts for words, exts in _TYPES.items() for word in words}

_STOP = {
    "the", "a", "an", "my", "me", "i", "of", "in", "on", "from", "to", "for", "with", "that", "this",
    "those", "these", "and", "or", "called", "named", "about", "please", "find", "search", "look",
    "looking", "locate", "show", "list", "get", "where", "is", "are", "file", "files", "folder",
    "folders", "all", "any", "some", "modified", "edited", "created", "changed", "saved", "downloaded",
    "updated", "opened", "last", "past", "than", "bigger", "larger", "greater", "over", "above", "more",
    "large", "big", "huge", "recent", "recently", "lately", "today", "yesterday", "week", "weeks",
    "month", "months", "day", "days", "new", "newest", "latest", "old", "one", "it", "did",
}
_UNITS = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}
_SIZE = re.compile(r"\b(?:bigger|larger|greater|more|over|above)\s+(?:than\s+)?(\d+(?:\.\d+)?)\s*(kb|mb|gb)\b")
_FILEISH = re.compile(
    r"\b(?:files?|folders?|documents?|pdfs?|docx?|spreadsheets?|excel|powerpoint|presentations?|slides|"
    r"images?|photos?|pictures?|screenshots?|videos?)\b|\.\w{2,4}\b|"
    r"\b(?:modified|edited|created|saved|downloaded|changed|updated)\b|\b(?:bigger|larger)\s+than\b",
    re.IGNORECASE)
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
             "eighth": 8, "ninth": 9, "tenth": 10}


@dataclass
class FileQuery:
    keywords: list = field(default_factory=list)
    exts: set = field(default_factory=set)
    after: datetime | None = None
    before: datetime | None = None
    min_size: int | None = None
    folders: set = field(default_factory=set)
    time_text: str = ""
    size_text: str = ""

    def describe(self) -> str:
        parts = []
        if self.exts:
            parts.append("types " + ", ".join(sorted(e.lstrip(".") for e in self.exts)))
        if self.time_text:
            parts.append(f"modified {self.time_text}")
        if self.size_text:
            parts.append(self.size_text)
        if self.keywords:
            parts.append("matching '" + " ".join(self.keywords) + "'")
        if self.folders:
            parts.append("in " + ", ".join(sorted(self.folders)))
        return "; ".join(parts)


def _time_range(t: str, now: datetime):
    """Returns (after, before, matched phrase). Dates are local time."""
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = day0 - timedelta(days=day0.weekday())
    first_of_month = day0.replace(day=1)
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month)s?\b", t)
    if m:
        days = int(m[1]) * {"day": 1, "week": 7, "month": 30}[m[2]]
        return now - timedelta(days=days), None, m.group(0)
    if "yesterday" in t:
        return day0 - timedelta(days=1), day0, "yesterday"
    if "today" in t:
        return day0, None, "today"
    if "last week" in t:
        return monday - timedelta(days=7), monday, "last week"
    if "this week" in t:
        return monday, None, "this week"
    if "last month" in t:
        return (first_of_month - timedelta(days=1)).replace(day=1), first_of_month, "last month"
    if "this month" in t:
        return first_of_month, None, "this month"
    m = re.search(r"\b(?:recent|recently|lately)\b", t)
    if m:
        return now - timedelta(days=7), None, m.group(0)
    return None, None, ""


def parse_query(text: str, roots=(), now: datetime | None = None) -> FileQuery:
    now = now or datetime.now()
    t = text.lower()
    q = FileQuery()

    m = _SIZE.search(t)
    if m:
        q.min_size = int(float(m[1]) * _UNITS[m[2]])
        q.size_text = f"over {m[1]} {m[2].upper()}"
        t = t.replace(m.group(0), " ")
    elif re.search(r"\b(?:large|big|huge)\b", t):
        q.min_size, q.size_text = 50 * 1024 ** 2, "over 50 MB"

    q.after, q.before, phrase = _time_range(t, now)
    if phrase:
        q.time_text = phrase
        t = t.replace(phrase, " ")

    names = {Path(r).name.lower() for r in roots}
    m = re.search(r"\b(?:in|from|inside|under)\s+(?:my\s+|the\s+)?(\w+)\b", t)
    if m and m[1] in names:
        q.folders.add(m[1])
        t = t.replace(m.group(0), " ")

    for word in re.findall(r"[a-z0-9_]+", t):
        if word in _WORD_TO_EXTS:
            q.exts |= _WORD_TO_EXTS[word]
        elif word not in _STOP and len(word) > 1 and not word.isdigit():
            q.keywords.append(word)
    return q


def search(query: FileQuery, roots, time_limit: float = 8.0, max_files: int = 300_000):
    """Walk the allowed folders. Cheap name/type checks come first; the file is only stat'ed after."""
    deadline = time.monotonic() + time_limit
    hits, examined, timed_out = [], 0, False
    for root in roots:
        root = Path(root)
        if query.folders and root.name.lower() not in query.folders:
            continue
        for current, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SEARCH_SKIP_DIRS and not d.startswith(".")]
            parent = Path(current).name.lower()
            for name in files:
                examined += 1
                if name.startswith((".", "~$")):
                    continue
                lowered = name.lower()
                if query.exts and os.path.splitext(lowered)[1] not in query.exts:
                    continue
                if query.keywords and not all(k in lowered + " " + parent for k in query.keywords):
                    continue
                path = Path(current) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                modified = datetime.fromtimestamp(stat.st_mtime)
                if query.after and modified < query.after:
                    continue
                if query.before and modified >= query.before:
                    continue
                if query.min_size and stat.st_size < query.min_size:
                    continue
                hits.append((path, stat.st_size, modified))
            if examined > max_files or time.monotonic() > deadline:
                timed_out = True
                break
        if timed_out:
            break

    def rank(hit):
        path, size, modified = hit
        if query.keywords and not (query.after or query.before or query.min_size):
            stem = path.stem.lower()
            score = 0 if stem == " ".join(query.keywords) else 1 if stem.startswith(query.keywords[0]) else 2
            return (score, -modified.timestamp())
        if query.min_size and not (query.after or query.before):
            return (0, -size)
        return (0, -modified.timestamp())

    hits.sort(key=rank)
    return hits[:MAX_SEARCH_RESULTS], timed_out


def _size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024


def _when(moment: datetime) -> str:
    days = (datetime.now().date() - moment.date()).days
    clock = moment.strftime("%I:%M %p").lstrip("0")
    return f"today {clock}" if days == 0 else f"yesterday {clock}" if days == 1 else moment.strftime("%d %b %Y")


def smart_search(ctx: ToolContext, query: str) -> str:
    q = parse_query(query, ctx.guard.roots)
    if not (q.keywords or q.exts or q.after or q.before or q.min_size):
        raise ToolError("Please be more specific: a name, a file type, a date or a size.")
    if not ctx.guard.roots:
        raise ToolError("No search folders are configured. See SEARCH_DIRECTORIES in config.py.")
    hits, timed_out = search(q, ctx.guard.roots)
    if not hits:
        return f"No files found ({q.describe()})."
    ctx.last_search_results = [path for path, _, _ in hits]   # So "open the first one" works
    lines = [f"Found {len(hits)} file{'s' if len(hits) != 1 else ''} ({q.describe()}):"]
    for i, (path, size, modified) in enumerate(hits, 1):
        lines.append(f"{i}. {path.name}  -  {_size(size)}, {_when(modified)}  ({path.parent})")
    if timed_out:
        lines.append("(The search stopped early, so the list may be incomplete.)")
    lines.append("Say 'open the first one' (or second, third...) to open a result.")
    return "\n".join(lines)


class FileSearchFeature(Feature):
    name = "file search"

    def register_tools(self):
        self.add_tool(Tool(
            "smart_search", "Search files by name, type, date and size using plain language.", smart_search,
            (Param("query", "string", "The request in plain language", max_length=200),),
            status_text="Searching your files..."))

    def rules(self):
        return [
            rule(r"^(?:please\s+)?(?:find|search(?:\s+for)?|look\s+for|locate|show\s+me|list|get|"
                 r"where\s+(?:is|are))\s+(?P<q>.+)$", self._search, statement_only=True,
                 guard=lambda t: bool(_FILEISH.search(t)) and not re.search(r"\b(?:web|internet|online|google)\b", t, re.I)),
            rule(r"^(?:please\s+)?open\s+(?:the\s+)?(?:(?P<word>first|second|third|fourth|fifth|sixth|seventh|"
                 r"eighth|ninth|tenth)(?:\s+(?:one|result|file))?|(?P<ord>\d+)(?:st|nd|rd|th)(?:\s+(?:one|result|file))?|"
                 r"(?:result|number|file|#)\s*(?P<n>\d+))$", self._open),
        ]

    def _search(self, match, cb):
        result = self.call("smart_search", {"query": match["q"]}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"

    def _open(self, match, cb):
        number = _ORDINALS.get((match["word"] or "").lower()) or int(match["ord"] or match["n"])
        result = self.call("open_search_result", {"number": number}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"