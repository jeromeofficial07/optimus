"""
System analytics: a lightweight collector (bounded memory) plus the "system analytics" command.
The collector samples every 15 seconds in the background and every 2 seconds while the
dashboard is open. Each sample takes about a millisecond.
"""
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

import psutil

from app.agent.registry import Tool, ToolContext
from app.features.base import Feature, rule


@dataclass
class Sample:
    t: float
    cpu: float
    ram: float
    disk: float
    battery: float | None
    own_mb: float       # Memory used by the OPTIMUS application itself
    own_cpu: float      # Its share of the whole machine's CPU


class AnalyticsCollector:
    def __init__(self, maxlen: int = 300):
        self._samples: deque = deque(maxlen=maxlen)   # Old samples fall off, so memory stays small
        self._lock = threading.Lock()
        self._me = psutil.Process()
        self._drive = os.environ.get("SystemDrive", "C:") + "\\"
        psutil.cpu_percent(None)       # The first reading is meaningless, so prime the counters
        self._me.cpu_percent(None)

    def sample(self) -> Sample:
        battery = psutil.sensors_battery()
        sample = Sample(
            time.time(), psutil.cpu_percent(None), psutil.virtual_memory().percent,
            psutil.disk_usage(self._drive).percent, battery.percent if battery else None,
            self._me.memory_info().rss / 2 ** 20, self._me.cpu_percent(None) / (psutil.cpu_count() or 1))
        with self._lock:
            self._samples.append(sample)
        return sample

    def recent(self, seconds: float | None = None) -> list[Sample]:
        with self._lock:
            samples = list(self._samples)
        if seconds is None:
            return samples
        cutoff = time.time() - seconds
        return [s for s in samples if s.t >= cutoff]

    def stats(self, seconds: float = 600) -> dict | None:
        samples = self.recent(seconds)
        if len(samples) < 3:
            return None
        cpu, ram = [s.cpu for s in samples], [s.ram for s in samples]
        return {"minutes": max(1, round((samples[-1].t - samples[0].t) / 60)),
                "cpu_avg": sum(cpu) / len(cpu), "cpu_peak": max(cpu),
                "ram_avg": sum(ram) / len(ram), "ram_peak": max(ram)}

    @staticmethod
    def top_processes(count: int = 5) -> tuple[int, list[tuple[str, int]]]:
        """(bytes used by the AI model (Ollama), the biggest memory users grouped by program name)."""
        totals: dict[str, int] = {}
        ollama = 0
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                info = proc.info
                name, rss = info["name"] or "?", (info["memory_info"].rss if info["memory_info"] else 0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            totals[name] = totals.get(name, 0) + rss
            if name.lower().startswith("ollama"):
                ollama += rss
        return ollama, sorted(totals.items(), key=lambda item: item[1], reverse=True)[:count]


class AnalyticsFeature(Feature):
    name = "system analytics"

    def __init__(self, services):
        super().__init__(services)
        self.collector = AnalyticsCollector()

    def register_tools(self):
        self.add_tool(Tool("system_analytics", "Report CPU, memory, disk, battery and OPTIMUS's own resource use.",
                           self._report_text, status_text="Analysing the system..."))

    def _report_text(self, ctx: ToolContext) -> str:
        cpu_now = psutil.cpu_percent(interval=0.3)        # A short real measurement for an accurate "now"
        sample, memory = self.collector.sample(), psutil.virtual_memory()
        stats = self.collector.stats(600)
        history = f", average {stats['cpu_avg']:.0f}%, peak {stats['cpu_peak']:.0f}%" if stats else ""
        mem_history = f", peak {stats['ram_peak']:.0f}%" if stats else ""
        window = f" (last {stats['minutes']} min)" if stats else ""
        lines = [f"System analytics{window}:",
                 f"- CPU: now {cpu_now:.0f}%{history}",
                 f"- Memory: now {memory.percent:.0f}% ({memory.used / 2**30:.1f} of {memory.total / 2**30:.1f} GB){mem_history}",
                 f"- Disk: {sample.disk:.0f}% used"]
        if sample.battery is not None:
            lines.append(f"- Battery: {sample.battery:.0f}%")
        ollama, ranked = self.collector.top_processes(5)
        lines.append(f"- OPTIMUS app: {sample.own_mb:.0f} MB RAM, about {sample.own_cpu:.0f}% CPU")
        if ollama:
            lines.append(f"- AI model (Ollama): {ollama / 2**30:.1f} GB RAM")
        lines.append("Top memory users: " + ", ".join(f"{name} {size / 2**20:.0f} MB" for name, size in ranked))
        return "\n".join(lines)

    def rules(self):
        return [
            rule(r"^(?:please\s+)?(?:show|open)\s+(?:me\s+)?(?:the\s+|my\s+)?(?:system\s+)?"
                 r"(?:analytics|dashboard|performance|resource\s+monitor|system\s+monitor)(?:\s+dashboard)?$", self._dashboard),
            rule(r"^(?:system\s+analytics|performance\s+report|resource\s+report|how\s+is\s+my\s+system\s+performing)$",
                 self._report),
        ]

    def _dashboard(self, match, cb):
        self.s.ui("show_dashboard")   # The GUI opens the window
        return "Opening the system analytics dashboard."

    def _report(self, match, cb):
        result = self.call("system_analytics", {}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"