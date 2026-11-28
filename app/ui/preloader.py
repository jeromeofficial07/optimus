"""
PreloaderOverlay - the intro: a huge counter, a progress line and status lines on the blueprint
sheet, then the whole curtain slides up to reveal the interface. Click to skip.
"""
from PySide6.QtCore import QElapsedTimer, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.ui.blueprint_theme import INK, _render_background
from app.ui.theme import rgba

STATUS = ["MOUNTING MEMORY", "CALIBRATING VOICE", "LOADING LANGUAGE CORE", "ARMING SAFETY LAYER", "SYSTEMS ONLINE"]


class PreloaderOverlay(QWidget):
    COUNT_MS = 2400

    def __init__(self, parent, family: str = "Segoe UI"):
        super().__init__(parent)
        self._family = family
        self._phase = "count"           # count -> hold -> lift
        self._progress = 0.0
        self._hold_started = 0
        self._skip = False
        self._bg = None
        self._bg_key = None
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._lift = QPropertyAnimation(self, b"pos", self)
        self._lift.setDuration(750)
        self._lift.setEasingCurve(QEasingCurve.InOutCubic)
        self._lift.finished.connect(self._finish)
        self.setGeometry(parent.rect())
        if hasattr(parent, "resized"):
            parent.resized.connect(self._fit)
        self.raise_()
        self.show()

    def start(self):
        self._clock.start()
        self._timer.start()

    def _fit(self):
        if self._phase != "lift":
            self.setGeometry(self.parentWidget().rect())

    def mousePressEvent(self, event):
        self._skip = True

    def _tick(self):
        elapsed = self._clock.elapsed()
        if self._phase == "count":
            x = 1.0 if self._skip else min(1.0, elapsed / self.COUNT_MS)
            self._progress = x * x * (3 - 2 * x)           # Smooth start and finish
            if x >= 1.0:
                self._phase = "hold"
                self._hold_started = elapsed
        elif self._phase == "hold":
            if self._skip or elapsed - self._hold_started >= 250:
                self._begin_lift()
        self.update()

    def _begin_lift(self):
        self._phase = "lift"
        self._timer.stop()
        self._progress = 1.0
        self.update()
        self._lift.setStartValue(self.pos())
        self._lift.setEndValue(QPoint(0, -self.height()))   # The curtain slides up
        self._lift.start()

    def _finish(self):
        try:
            self.parentWidget().resized.disconnect(self._fit)
        except (AttributeError, RuntimeError, TypeError):
            pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        key = (w, h, self.devicePixelRatioF())
        if self._bg_key != key:
            self._bg = _render_background(*key)
            self._bg_key = key
        p.drawPixmap(0, 0, self._bg)
        ink, progress = QColor(INK), self._progress

        counter = QFont(self._family)                       # The big counter
        counter.setPixelSize(int(max(90, min(h * 0.34, 280))))
        counter.setWeight(QFont.Light)
        counter.setLetterSpacing(QFont.AbsoluteSpacing, -3)
        p.setFont(counter)
        p.setPen(ink)
        p.drawText(QRectF(40, h * 0.30, w * 0.7, h * 0.50), Qt.AlignLeft | Qt.AlignBottom, f"{int(progress * 100):03d}")

        title = QFont(self._family)
        title.setPixelSize(20)
        title.setBold(True)
        title.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        p.setFont(title)
        p.drawText(QPointF(40, 56), "OPTIMUS")
        mono = QFont("Consolas", 9)
        mono.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(mono)
        p.setPen(rgba(INK, 0.65))
        p.drawText(QPointF(40, 78), "PERSONAL AI ASSISTANT  //  LOCAL  //  OFFLINE FIRST")
        p.drawText(QPointF(w - 190, 56), "SHEET 01 / 01")
        status = STATUS[min(len(STATUS) - 1, int(progress * len(STATUS)))]
        p.setPen(ink)
        p.drawText(QPointF(40, h - 66), f"> {status}")
        p.drawText(QPointF(w - 80, h - 66), f"{int(progress * 100):>3d} %")

        y = h - 44                                          # Progress line
        p.setPen(QPen(rgba(INK, 0.25), 1))
        p.drawLine(QPointF(40, y), QPointF(w - 40, y))
        p.setPen(QPen(ink, 2))
        p.drawLine(QPointF(40, y), QPointF(40 + (w - 80) * progress, y))

        cx, cy, r = w - 90, 128, 34                         # Sweeping ring
        p.setPen(QPen(rgba(INK, 0.25), 1))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(ink, 1.6))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90 * 16, int(-360 * 16 * progress))

        p.setPen(QPen(rgba(INK, 0.7), 1))                   # Corner crosshairs
        for x, yy in ((22, 22), (w - 22, 22), (22, h - 22), (w - 22, h - 22)):
            p.drawLine(QPointF(x - 8, yy), QPointF(x + 8, yy))
            p.drawLine(QPointF(x, yy - 8), QPointF(x, yy + 8))


# --- end of file ---