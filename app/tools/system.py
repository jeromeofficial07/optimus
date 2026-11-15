"""
System tools: usage, battery, screenshot and lock.
"""
import os
import sys
import time
from datetime import datetime

import psutil

from app.agent.registry import ToolContext, ToolError
from app.config import SCREENSHOT_DIR


def _gb(value: float) -> str:
    return f"{value / (1024 ** 3):.1f}"


def get_system_usage(ctx: ToolContext) -> str:
    cpu = psutil.cpu_percent(interval=0.6)  # Measured over 0.6 seconds
    memory = psutil.virtual_memory()
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    disk = psutil.disk_usage(drive)
    return (
        f"CPU usage is {cpu:.0f}% across {psutil.cpu_count()} logical cores. "
        f"Memory: {_gb(memory.used)} of {_gb(memory.total)} GB in use ({memory.percent:.0f}%). "
        f"Disk {drive[:2]} {_gb(disk.used)} of {_gb(disk.total)} GB used ({disk.percent:.0f}%)."
    )


def get_battery_status(ctx: ToolContext) -> str:
    battery = psutil.sensors_battery()
    if battery is None:
        return "No battery was detected. This looks like a desktop or the battery info is unavailable."
    text = f"Battery is at {battery.percent:.0f}%"
    if battery.power_plugged:
        text += ", plugged in" + (" and charging." if battery.percent < 100 else " and fully charged.")
    else:
        text += ", running on battery."
        secs = battery.secsleft
        if secs not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) and secs > 0:
            text += f" About {secs // 3600}h {(secs % 3600) // 60}m remaining."
    return text


def take_screenshot(ctx: ToolContext) -> str:
    try:
        import pyautogui
    except ImportError as exc:
        raise ToolError("Screenshots need PyAutoGUI. Run:  python -m pip install pyautogui pillow") from exc

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"

    # Minimise OPTIMUS first so it does not appear in its own screenshot
    if ctx.set_window_hidden:
        ctx.set_window_hidden(True)
        time.sleep(0.9)
    try:
        image = pyautogui.screenshot()
    except Exception as exc:
        raise ToolError(f"Could not capture the screen: {exc}") from exc
    finally:
        if ctx.set_window_hidden:
            ctx.set_window_hidden(False)
    image.save(path)
    return f"Screenshot saved to {path}"


def lock_computer(ctx: ToolContext) -> str:
    if sys.platform != "win32":
        raise ToolError("Locking is only supported on Windows.")
    import ctypes
    if not ctypes.windll.user32.LockWorkStation():
        raise ToolError("Windows refused to lock the computer.")
    return "The computer is now locked."