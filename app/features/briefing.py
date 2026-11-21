"""
Daily briefing: the date, tasks (overdue, due today, coming up), today's reminders and the battery.
Built from your own data with plain code, so it is instant and always accurate.
"""
from datetime import datetime

import psutil

from app.agent.registry import Tool, ToolContext
from app.agent.timeparse import describe, from_text
from app.features.base import Feature, rule


def _greeting(now: datetime) -> str:
    return "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"


def build_briefing(storage, now: datetime | None = None) -> str:
    now = now or datetime.now()
    today = now.date()
    name = storage.memory.get("name")
    lines = [f"Daily briefing for {now:%A, %d %B %Y}.", "",
             f"**{_greeting(now)}{', ' + name if name else ''}.**", ""]

    tasks = storage.tasks.open_tasks()
    if not tasks:
        lines.append("**Tasks:** none open. Nice and clear.")
    else:
        lines.append(f"**Tasks:** {len(tasks)} open")
        shown = 0
        for i, task in enumerate(tasks, 1):
            due = from_text(task["due_at"]) if task["due_at"] else None
            if due and due.date() < today:
                label = "Overdue"
            elif due and due.date() == today:
                label = "Due today"
            else:
                continue
            lines.append(f"- **{label}:** {i}. {task['title']} ({describe(due, now)})")
            shown += 1
        rest = len(tasks) - shown
        if rest:
            lines.append(f"- {rest} more open task{'s' if rest != 1 else ''} (say 'show my tasks')")

    due_today = [r for r in storage.reminders.pending() if from_text(r["remind_at"]).date() == today]
    lines.append("")
    if due_today:
        lines.append("**Reminders today:**")
        lines += [f"- {from_text(r['remind_at']):%I:%M %p}: {r['text']}".replace("- 0", "- ") for r in due_today]
    else:
        lines.append("**Reminders today:** none.")

    try:
        battery = psutil.sensors_battery()
        if battery:
            lines += ["", f"**Computer:** battery {battery.percent:.0f}%"
                          + (" (charging)" if battery.power_plugged else " (on battery)")]
    except Exception:
        pass
    return "\n".join(lines)


class BriefingFeature(Feature):
    name = "daily briefing"

    def register_tools(self):
        self.add_tool(Tool("daily_briefing", "Summarise today's tasks, reminders and battery.",
                           lambda ctx: build_briefing(self.s.storage), status_text="Preparing your briefing..."))

    def rules(self):
        return [rule(
            r"^(?:please\s+)?(?:good\s+(?:morning|afternoon|evening)|"
            r"(?:give\s+me\s+|show\s+me\s+|what(?:'s|\s+is)\s+)?(?:my\s+)?(?:daily\s+)?(?:briefing|agenda)|"
            r"brief\s+me|what(?:'s|\s+is)\s+(?:on\s+)?(?:for\s+)?today|what\s+do\s+i\s+have\s+(?:on\s+)?today)$",
            self._briefing)]

    def _briefing(self, match, cb):
        result = self.call("daily_briefing", {}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"