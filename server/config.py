import os
from pathlib import Path

# Load env variables from root directory .env file if it exists
try:
    from dotenv import load_dotenv
    root_dir = Path(__file__).resolve().parent.parent
    dotenv_path = root_dir / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

class Config:
    # OpenRouter API configurations
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nousresearch/hermes-3-llama-3.1-8b")
    OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    
    # Deepgram configurations
    DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
    DEEPGRAM_STT_MODEL = os.environ.get("DEEPGRAM_STT_MODEL", "nova-2-medical")
    DEEPGRAM_TTS_MODEL = os.environ.get("DEEPGRAM_TTS_MODEL", "aura-helios-en")
    
    # Twilio configurations
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
    
    # SQLite configurations
    # We resolve it relative to the root directory
    root_dir = Path(__file__).resolve().parent.parent
    DEFAULT_DB_PATH = str(root_dir / "db" / "dental_clinic.sqlite")
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", DEFAULT_DB_PATH)
    
    # Qdrant configurations
    DEFAULT_QDRANT_HOST = str(root_dir / "db" / "qdrant_storage")
    QDRANT_HOST = os.environ.get("QDRANT_HOST", DEFAULT_QDRANT_HOST)
    QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
    QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")
    
    # Server host/port
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", "8000"))

    @classmethod
    def validate_keys(cls):
        """Validates that required keys are present and warns the console if not."""
        warnings = []
        if not cls.OPENROUTER_API_KEY:
            warnings.append("OPENROUTER_API_KEY is not set. OpenRouter LLM will not function.")
        if not cls.DEEPGRAM_API_KEY:
            warnings.append("DEEPGRAM_API_KEY is not set. Deepgram speech STT/TTS will not function.")
        
        if warnings:
            print("\n" + "="*60)
            print("WARNING: Missing essential API keys in configuration:")
            for w in warnings:
                print(f" - {w}")
            print("Please ensure your .env file is configured correctly in the root folder.")
            print("="*60 + "\n")
            return False
        return True

# Validate keys on configuration import
Config.validate_keys()
