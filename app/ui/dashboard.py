"""
DashboardDialog - live system analytics. Custom-painted charts, so no extra packages.
It samples only while it is visible, and scans processes on a background thread.
"""
from PySide6.QtCore import QPointF, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.features.analytics import AnalyticsCollector
from app.ui.theme import Colors

QSS = """
QDialog { background: #070c1c; }
QLabel { color: #e6ecff; background: transparent; }
QLabel#Small { color: #8a96b8; font-size: 12px; }
QLabel#Big { font-size: 30px; font-weight: 600; }
QFrame#Card { background: rgba(255,255,255,12); border: 1px solid rgba(96,165,250,60); border-radius: 14px; }
"""


class Sparkline(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._values: list[float] = []
        self.setMinimumHeight(64)

    def set_values(self, values):
        self._values = list(values)[-120:]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        for fraction in (0.25, 0.5, 0.75):
            painter.drawLine(0, int(h * fraction), w, int(h * fraction))
        if len(self._values) < 2:
            return
        step = w / (len(self._values) - 1)
        points = [QPointF(i * step, h - 2 - max(0.0, min(100.0, v)) / 100 * (h - 4))
                  for i, v in enumerate(self._values)]
        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)
        area = QPainterPath(line)
        area.lineTo(w, h)
        area.lineTo(0, h)
        area.closeSubpath()
        gradient = QLinearGradient(0, 0, 0, h)
        top, bottom = QColor(self._color), QColor(self._color)
        top.setAlpha(110)
        bottom.setAlpha(0)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.fillPath(area, QBrush(gradient))
        painter.setPen(QPen(self._color, 2))
        painter.drawPath(line)


class StatCard(QFrame):
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        small = QLabel(title)
        small.setObjectName("Small")
        self._value = QLabel("-")
        self._value.setObjectName("Big")
        self._chart = Sparkline(color)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(small)
        layout.addWidget(self._value)
        layout.addWidget(self._chart, 1)

    def update_card(self, value: str, history):
        self._value.setText(value)
        self._chart.set_values(history)


class ProcessScan(QThread):
    """Listing every process takes a moment, so it never runs on the interface thread."""
    done = Signal(object)

    def run(self):
        self.done.emit(AnalyticsCollector.top_processes(6))


class DashboardDialog(QDialog):
    def __init__(self, collector: AnalyticsCollector, parent=None):
        super().__init__(parent)
        self.collector = collector
        self.setWindowTitle("OPTIMUS - System analytics")
        self.resize(780, 640)
        self.setStyleSheet(QSS)
        self._scanning = False
        self._tick = 0

        self.cpu = StatCard("CPU usage", Colors.ACCENT_LIGHT)
        self.ram = StatCard("Memory usage", Colors.ACCENT_CYAN)
        self.disk = StatCard("Disk usage", "#a78bfa")
        self.battery = StatCard("Battery", Colors.WARNING)
        grid = QGridLayout()
        grid.setSpacing(12)
        for index, card in enumerate((self.cpu, self.ram, self.disk, self.battery)):
            grid.addWidget(card, index // 2, index % 2)

        self.own_label = QLabel()
        self.procs_label = QLabel("Scanning processes...")
        self.procs_label.setObjectName("Small")
        details = QFrame()
        details.setObjectName("Card")
        box = QVBoxLayout(details)
        box.setContentsMargins(16, 12, 16, 12)
        box.addWidget(self.own_label)
        box.addWidget(self.procs_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addLayout(grid, 1)
        layout.addWidget(details)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)

    def showEvent(self, event):   # Sample only while visible
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self):
        s = self.collector.sample()
        samples = self.collector.recent()
        self.cpu.update_card(f"{s.cpu:.0f}%", [x.cpu for x in samples])
        self.ram.update_card(f"{s.ram:.0f}%", [x.ram for x in samples])
        self.disk.update_card(f"{s.disk:.0f}%", [x.disk for x in samples])
        if s.battery is None:
            self.battery.update_card("n/a", [])
        else:
            self.battery.update_card(f"{s.battery:.0f}%", [x.battery or 0 for x in samples])
        self.own_label.setText(f"OPTIMUS app: {s.own_mb:.0f} MB memory, about {s.own_cpu:.0f}% CPU")
        self._tick += 1
        if self._tick % 3 == 1 and not self._scanning:     # Every ~6 seconds
            self._scanning = True
            scan = ProcessScan(self)
            scan.done.connect(self._show_processes)
            scan.finished.connect(scan.deleteLater)
            scan.start()

    def _show_processes(self, result):
        self._scanning = False
        ollama, ranked = result
        lines = []
        if ollama:
            lines.append(f"AI model (Ollama): {ollama / 2**30:.1f} GB memory")
        lines.append("Top memory users:  " + "   |   ".join(f"{name} {size / 2**20:.0f} MB" for name, size in ranked))
        self.procs_label.setText("\n".join(lines))