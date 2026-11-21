"""
Date and time understanding for reminders and task due dates, without any AI.

extract_time("remind me to stretch in 10 minutes")
    -> (datetime for 10 minutes from now, "remind me to stretch")

Understands: "in 10 minutes", "in an hour", "in half an hour", "at 6 pm", "at 6:30",
"tomorrow", "tomorrow at 9am", "today", "tonight", weekdays ("on friday") and
"2026-12-01 14:30". Plain "at 3" means 3 pm, because hours 1 to 6 are almost always afternoon.
"""
import re
from datetime import datetime, time, timedelta

_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_ISO = re.compile(r"\b(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})"
                  r"(?:[ T](?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?")
_REL = re.compile(
    r"\bin\s+half\s+an\s+hour\b"
    r"|\bin\s+(?P<n>\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty)\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.IGNORECASE)
_DAY = re.compile(r"\b(?P<day>tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|"
                  r"saturday|sunday)\b", re.IGNORECASE)
_TIME = re.compile(
    r"\b(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)(?!\w)"
    r"|\bat\s+(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\b", re.IGNORECASE)


def _delta(amount: int, unit: str) -> timedelta:
    unit = unit.lower()
    if unit.startswith("sec"):
        return timedelta(seconds=amount)
    if unit.startswith("min"):
        return timedelta(minutes=amount)
    if unit.startswith(("hour", "hr")):
        return timedelta(hours=amount)
    if unit.startswith("day"):
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def _remove(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    return re.sub(r"\s+", " ", text).strip()


def extract_time(text: str, now: datetime | None = None) -> tuple[datetime | None, str]:
    """Find a time expression. Returns (moment or None, the text with that expression removed)."""
    now = now or datetime.now()

    iso = _ISO.search(text)
    if iso:
        try:
            when = datetime(int(iso["y"]), int(iso["mo"]), int(iso["d"]),
                            int(iso["h"] or 9), int(iso["mi"] or 0), int(iso["s"] or 0))
            return when, _remove(text, [iso.span()])
        except ValueError:
            pass

    rel = _REL.search(text)
    if rel:
        if rel["n"] is None:
            delta = timedelta(minutes=30)
        else:
            raw = rel["n"].lower()
            delta = _delta(int(raw) if raw.isdigit() else _NUMBERS[raw], rel["unit"])
        return now + delta, _remove(text, [rel.span()])

    day_m, time_m = _DAY.search(text), _TIME.search(text)
    if not day_m and not time_m:
        return None, text

    spans: list[tuple[int, int]] = []
    base = now.date()
    default_hour = 9
    if day_m:
        word = day_m["day"].lower()
        if word == "tomorrow":
            base += timedelta(days=1)
        elif word == "tonight":
            default_hour = 20
        elif word != "today":
            base += timedelta(days=(_WEEKDAYS.index(word) - now.weekday()) % 7 or 7)
        spans.append(day_m.span())

    if time_m:
        hour = int(time_m["h"] or time_m["h2"])
        minute = int(time_m["m"] or time_m["m2"] or 0)
        meridiem = (time_m["ap"] or "").lower().replace(".", "")
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        elif not meridiem and 1 <= hour <= 6:
            hour += 12  # "at 6" means 6 pm
        if hour > 23 or minute > 59:
            return None, text
        spans.append(time_m.span())
    else:
        hour, minute = default_hour, 0

    when = datetime.combine(base, time(hour, minute))
    if not day_m and when <= now:
        when += timedelta(days=1)  # "at 9am" said at 10am means tomorrow
    return when, _remove(text, spans)


def describe(when: datetime, now: datetime | None = None) -> str:
    """'today at 6:00 PM', 'tomorrow at 9:00 AM', 'Friday at 2:30 PM', 'Mon 30 Nov at 8:00 AM'."""
    now = now or datetime.now()
    clock = when.strftime("%I:%M %p").lstrip("0")  # %-I does not work on Windows
    days = (when.date() - now.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if 1 < days < 7:
        return f"{when:%A} at {clock}"
    return f"{when:%a %d %b} at {clock}"


def from_text(text: str) -> datetime:
    """Read a time stored in the database."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")