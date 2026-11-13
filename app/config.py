"""
Central configuration for OPTIMUS.
Every other module imports paths and settings from here, so changing
a setting means editing exactly one file.
"""
from pathlib import Path

# Project root = the folder that contains the 'app' folder.
# Path(__file__) is this file; .parent.parent climbs two levels up.
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
APP_VERSION = "0.2.0"

# Database file (used from Phase 4 onward)
DATABASE_PATH = DATA_DIR / "optimus.db"

# Local LLM settings (used from Phase 2 onward)
OLLAMA_MODEL = "qwen2.5:3b"
