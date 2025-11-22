import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # --- Discord ---
    DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
    GUILD_ID = int(os.getenv("GUILD_ID", "0"))
    OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Bot owner ID - bypasses all permission checks
    COUNCIL_LOG_CHANNEL_ID = int(os.getenv("COUNCIL_LOG_CHANNEL_ID", "0"))

    # --- Channels ---
    SUBMISSIONS_CHANNEL_ID = int(os.getenv("SUBMISSIONS_CHANNEL_ID", "0"))
    HIATUS_CHANNEL_ID = int(os.getenv("HIATUS_CHANNEL_ID", "0"))
    CHARACTER_BACKSTORIES_CHANNEL_ID = int(os.getenv("CHARACTER_BACKSTORIES_CHANNEL_ID", "0"))
    NPC_BACKSTORIES_CHANNEL_ID = int(os.getenv("NPC_BACKSTORIES_CHANNEL_ID", "0"))
    CHARACTER_GRAVEYARD_CHANNEL_ID = int(os.getenv("CHARACTER_GRAVEYARD_CHANNEL_ID", "0"))
    ENCYCLOPEDIA_CHANNEL_ID = int(os.getenv("ENCYCLOPEDIA_CHANNEL_ID", "0"))
    RESOURCES_CHANNEL_ID = int(os.getenv("RESOURCES_CHANNEL_ID", "0"))
    HELP_CHANNEL_ID = int(os.getenv("HELP_CHANNEL_ID", "0"))  # For border change announcements

    # --- Google Sheets (replaces GAS) ---
    GOOGLE_SHEET_ID = (os.getenv("GOOGLE_SHEET_ID") or "").strip()
    
    # --- GAS (legacy, optional for migration period) ---
    WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()
    GSCRIPT_SECRET = (os.getenv("GSCRIPT_SECRET") or "").strip()

    # --- Submissions ---
    SUBMISSION_WINDOW_SECONDS = int(os.getenv("SUBMISSION_WINDOW_SECONDS", "900"))
    COURTS = {"day", "night", "dawn", "spring", "summer", "autumn", "winter"}

    # --- Hiatus DM scheduler ---
    HIATUS_DM_HOUR = int(os.getenv("HIATUS_DM_HOUR", "10"))  # local hour to run
    TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "-4"))
    HIATUS_SNOOZE_FILE = os.getenv("HIATUS_SNOOZE_FILE", "hiatus_snooze.json")
    
    # --- AI / RAG Settings ---
    OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano-2025-08-07")  # 400k context window, 128k token window
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./data/chroma_db")
    
    # Rate limiting for indexing
    INDEX_DELAY_SECONDS = float(os.getenv("INDEX_DELAY_SECONDS", "2.0"))  # Delay between threads
    EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "50"))  # Chunks per batch
    EMBEDDING_DELAY_SECONDS = float(os.getenv("EMBEDDING_DELAY_SECONDS", "0.1"))  # Delay between batches
    
    # Roleplay AI context settings
    ROLEPLAY_MAX_TOKENS = int(os.getenv("ROLEPLAY_MAX_TOKENS", "4000"))  # Max tokens for summaries/stories (increased for GPT-5 nano)
    ROLEPLAY_CONTEXT_LIMIT = int(os.getenv("ROLEPLAY_CONTEXT_LIMIT", "10"))  # Number of context chunks to retrieve
    
    # Development settings
    ENABLE_COGWATCH = os.getenv("ENABLE_COGWATCH", "false").lower() in ("true", "1", "yes")  # Enable file watching for hot-reloading
    USE_POLLING_WATCHER = os.getenv("USE_POLLING_WATCHER", "false").lower() in ("true", "1", "yes")  # Use polling instead of cogwatch (better for Docker)
    COGWATCH_POLL_INTERVAL = float(os.getenv("COGWATCH_POLL_INTERVAL", "2.0"))  # Polling interval in seconds

# Instantiate settings object
settings = Settings()

# --- Guards (fail fast if misconfigured) ---
if not settings.DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing in .env")

# Google Sheets API (new method) - optional, only required by cogs that use it
# if not settings.GOOGLE_SHEET_ID:
#     raise RuntimeError("GOOGLE_SHEET_ID missing in .env (required for direct Sheets API access)")

# GAS (legacy) - optional, only needed during migration
# if not settings.WEBHOOK_URL.startswith("https://script.google.com/macros/s/"):
#     raise RuntimeError("WEBHOOK_URL looks wrong (must be a Google Apps Script endpoint)")
# if not settings.GSCRIPT_SECRET:
#     raise RuntimeError("GSCRIPT_SECRET missing in .env")

# Character backstories channel - optional, only required by cogs that use it
# if not settings.CHARACTER_BACKSTORIES_CHANNEL_ID:
#     raise RuntimeError("CHARACTER_BACKSTORIES_CHANNEL_ID missing in .env")

# --- Other defaults ---
MIA_STATE_FILE            = os.getenv("MIA_STATE_FILE", "data/mia_state.json")
MIA_INACTIVE_DAYS         = int(os.getenv("MIA_INACTIVE_DAYS", "30"))
MIA_LONG_INACTIVE_DAYS    = int(os.getenv("MIA_LONG_INACTIVE_DAYS", "180"))
MIA_MESSAGES_TO_CLEAR     = int(os.getenv("MIA_MESSAGES_TO_CLEAR", "5"))
MIA_CHECK_HOUR            = int(os.getenv("MIA_CHECK_HOUR", "9"))
HIGH_COUNCIL_ROLE_ID      = int(os.getenv("HIGH_COUNCIL_ROLE_ID", "0"))
LEGACY_ACTIVITY_FILE      = os.getenv("LEGACY_ACTIVITY_FILE", "activity_store.json")
BORDER_STATE_FILE         = os.getenv("BORDER_STATE_FILE", "data/border_state.json")
BORDER_CHECK_INTERVAL_MIN = int(os.getenv("BORDER_CHECK_INTERVAL_MIN", "15"))  # Check every 15 minutes
