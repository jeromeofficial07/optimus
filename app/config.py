"""
Central configuration for OPTIMUS.
Every other module imports paths and settings from here, so changing
a setting means editing exactly one file.
"""
from pathlib import Path

# Project root = the folder that contains the 'app' folder.
BASE_DIR = Path(__file__).resolve().parent.parent

# Folders used by the application
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

# Create the folders if they are missing, so the app never crashes on startup
for folder in (DATA_DIR, MODELS_DIR, LOGS_DIR):
    folder.mkdir(exist_ok=True)

# Application identity
APP_NAME = "OPTIMUS"
APP_VERSION = "0.5.0"

# Database file (used in a later phase)
DATABASE_PATH = DATA_DIR / "optimus.db"

# ---------------------------------------------------------------- Local LLM
# 127.0.0.1 is used instead of "localhost" because on some Windows setups
# "localhost" tries IPv6 first and adds a delay.
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:3b"     # Change this to switch models (must be pulled first)
OLLAMA_TIMEOUT = 120            # Seconds to wait for Ollama before giving up
OLLAMA_KEEP_ALIVE = "30m"       # Keep the model loaded in RAM between messages

LLM_TEMPERATURE = 0.7           # Higher = more creative, lower = more focused
LLM_CONTEXT_TOKENS = 4096       # Model "memory window". Bigger = more RAM and slower
MAX_HISTORY_MESSAGES = 16       # How many past messages are sent each time (8 exchanges)

# The system prompt tells the model who it is and how it may use its tools.
SYSTEM_PROMPT = (
    "You are OPTIMUS, a friendly and capable personal desktop assistant running locally "
    "on the user's Windows computer. Answer clearly and concisely in short natural "
    "sentences, because answers may be read aloud. "
    "You can control this computer ONLY by calling the provided tools. Call a tool only "
    "when the user asks you to do something on the computer or asks about the computer "
    "itself; for normal conversation just answer. "
    "After a tool runs, tell the user the result in one or two short sentences, and show "
    "lists as numbered lists. Never claim you did something unless a tool reported success. "
    "If a tool fails or the user declines, say so plainly. If a request needs something no "
    "tool can do, say you cannot do that yet. If you are unsure about anything else, say so "
    "instead of guessing."
)

# ---------------------------------------------------------------- Voice input (Faster-Whisper)
WHISPER_MODEL = "small.en"      # "base.en" is faster, "small.en" is more accurate
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"   # Fastest option on a CPU
WHISPER_LANGUAGE = "en"         # Use None with a multilingual model such as "small"
WHISPER_DIR = MODELS_DIR / "whisper"

SAMPLE_RATE = 16000             # Whisper expects 16 kHz mono audio
MIN_RECORD_SECONDS = 0.5        # Shorter recordings are treated as accidental clicks
MAX_RECORD_SECONDS = 30         # Recording stops by itself after this long
SILENCE_RMS_THRESHOLD = 0.003   # Below this loudness a recording counts as silence

# ---------------------------------------------------------------- Voice output (Piper)
PIPER_VOICE = "en_US-ryan-medium"
PIPER_DIR = MODELS_DIR / "piper"
PIPER_MODEL_PATH = PIPER_DIR / f"{PIPER_VOICE}.onnx"
PIPER_LENGTH_SCALE = 1.0        # Above 1.0 = slower speech, below 1.0 = faster

# ---------------------------------------------------------------- Automation (Phase 5)
# The ONLY folders OPTIMUS may search or open files from. Folders that do not exist are ignored.
_HOME = Path.home()
SEARCH_DIRECTORIES = [
    _HOME / "Documents",
    _HOME / "Desktop",
    _HOME / "Downloads",
    # Add your own project folders here, for example:  Path("D:/Projects"),
]
SEARCH_DIRECTORIES = [BASE_DIR] + [
    folder for folder in SEARCH_DIRECTORIES if folder.exists()
]

SEARCH_SKIP_DIRS = {"venv", ".venv", "node_modules", ".git", "__pycache__",
                    "site-packages", "$recycle.bin", "appdata"}
SEARCH_TIME_LIMIT = 8           # Seconds before a file search gives up
MAX_SEARCH_RESULTS = 10

SCREENSHOT_DIR = DATA_DIR / "screenshots"
ACTION_LOG_PATH = LOGS_DIR / "actions.log"

CONFIRMATION_TIMEOUT = 60       # Seconds before an unanswered permission prompt auto-denies
MAX_TOOL_CALLS_PER_TURN = 3     # Upper limit of actions per message
TOOL_INTENT_GATE = True         # Only offer tools when the message looks like an action

# Approved applications. 'target' is what gets launched; 'process' lists the process names
# that may be closed (None = OPTIMUS will never close it). Edit this list to add your own apps.
APPS = {
    "notepad": {"target": "notepad.exe", "process": ["notepad.exe"]},
    "calculator": {"target": "calc.exe", "process": ["CalculatorApp.exe", "Calculator.exe", "calc.exe"]},
    "paint": {"target": "mspaint.exe", "process": ["mspaint.exe"]},
    "file explorer": {"target": "explorer.exe", "process": None},
    "task manager": {"target": "taskmgr.exe", "process": None},
    "snipping tool": {"target": "snippingtool.exe", "process": ["SnippingTool.exe"]},
    "settings": {"target": "ms-settings:", "process": None},
    "edge": {"target": "msedge.exe", "process": ["msedge.exe"]},
    "chrome": {"target": "chrome.exe", "process": ["chrome.exe"]},
    "vs code": {"target": r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe", "process": ["Code.exe"]},
    "word": {"target": "winword.exe", "process": ["WINWORD.EXE"]},
    "excel": {"target": "excel.exe", "process": ["EXCEL.EXE"]},
    "powerpoint": {"target": "powerpnt.exe", "process": ["POWERPNT.EXE"]},
}

# Other names people use -> the key in APPS above
APP_ALIASES = {
    "calc": "calculator", "notes": "notepad", "note pad": "notepad",
    "explorer": "file explorer", "files": "file explorer", "file manager": "file explorer",
    "browser": "edge", "microsoft edge": "edge", "google chrome": "chrome",
    "vscode": "vs code", "visual studio code": "vs code", "code": "vs code",
    "ms word": "word", "microsoft word": "word", "ms excel": "excel", "microsoft excel": "excel",
    "ms paint": "paint", "snipping": "snipping tool", "taskmgr": "task manager",
}

# ---------------------------------------------------------------- Agent (Phase 6)
# Project folders the agent can prepare. The folder must be inside SEARCH_DIRECTORIES.
WORKSPACES = {
    "python": {"name": "OPTIMUS", "path": BASE_DIR},   # Change this to the project you want prepared
}
MAX_PLAN_STEPS = 5              # Longest plan the AI may propose
MAX_STEP_ATTEMPTS = 2           # A step whose effect cannot be confirmed is retried once
VERIFY_TIMEOUT = 8              # Seconds to wait for an app to appear after launching it
REQUIRE_PLAN_APPROVAL = True    # AI-drafted plans with 2+ steps are shown to you first


# ---------------------------------------------------------------- Advanced features (Phase 8)
# Switch any feature off by setting it to False. A feature that is off is never loaded.
FEATURES = {"file_search": True, "briefing": True, "history": True, "coding": True, "web": True}
BRIEFING_ON_STARTUP = True      # Show the daily briefing once per day when OPTIMUS starts
CODE_MAX_CHARS = 9000           # Most code sent to the AI at once (the AI's window is limited)
WEB_ENABLED = True              # Set to False to keep OPTIMUS completely offline
WEB_MAX_PAGES = 3               # How many result pages are read for a summary
WEB_PAGE_CHARS = 2000           # Text taken from each page
WEB_TIMEOUT = 8                 # Seconds before a web request gives up


# ---------------------------------------------------------------- Advanced features, part B (Phase 8B)
MULTILINGUAL_ENABLED = False            # Turn on after the setup steps for languages (see below)
WHISPER_MULTILINGUAL_MODEL = "small"    # Multilingual speech recognition (about 460 MB, downloaded once)
WHISPER_CPU_THREADS = 4                 # CPU threads for speech recognition (leaves room for the AI model)
STT_IDLE_UNLOAD_MINUTES = 15            # Free the speech model's memory after this many idle minutes (0 = never)

# language code -> name and the Piper voice used to speak it. voice=None means "text only".
# Piper's official voices cover Spanish, French, German and more, but not Hindi or Tamil.
LANGUAGES = {
    "en": {"name": "English", "voice": PIPER_VOICE},
    "es": {"name": "Spanish", "voice": "es_ES-davefx-medium"},
    "fr": {"name": "French", "voice": "fr_FR-siwis-medium"},
    "de": {"name": "German", "voice": "de_DE-thorsten-medium"},
    "hi": {"name": "Hindi", "voice": None},
    "ta": {"name": "Tamil", "voice": None},
}

# ---------------------------------------------------------------- Voice style (commander voice)
VOICE_STYLE = "prime"     # "prime" = deep, authoritative, slightly robotic voice; "normal" = plain voice
VOICE_PITCH = 0.88        # Lower = deeper (0.80 = very deep, 1.0 = unchanged; limited to 0.7 - 1.0)
VOICE_ROBOT = 0.30        # Metallic edge: 0 = none, 0.5 = strong (limited to 0.6)
VOICE_ECHO = 0.45         # Hall echo: 0 = dry, 1 = large hall

# A calm, noble speaking style for the written and spoken answers. Facts, tools and safety
# are unaffected. Set to False for a neutral tone.
PERSONA_ENABLED = True
if PERSONA_ENABLED:
    SYSTEM_PROMPT = SYSTEM_PROMPT + (
        " Speak as a calm, noble and wise leader: steady, protective, encouraging and brief. "
        "Address the user with respect. Never use catchphrases or quotes from any show or movie. "
        "The style must never change facts, tool use or safety."
    )

# ---------------------------------------------------------------- Interface theme
UI_THEME = "commander"    # "commander" = robotic red / blue / steel HUD, "glass" = the original dark glass look
