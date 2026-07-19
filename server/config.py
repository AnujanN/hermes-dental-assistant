import os
from pathlib import Path

import logging

# Load env variables from root directory .env file if it exists
try:
    from dotenv import load_dotenv
    root_dir = Path(__file__).resolve().parent.parent
    dotenv_path = root_dir / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

# Configure global logger
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

class Config:
    # OpenRouter API configurations
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nousresearch/hermes-3-llama-3.1-8b")
    OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    
    # Groq configurations
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_TRANSCRIPTION_MODEL = os.environ.get("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3")
    GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    
    # ElevenLabs configurations
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")
    
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
        if not cls.GROQ_API_KEY:
            warnings.append("GROQ_API_KEY is not set. Groq Whisper STT will not function.")
        if not cls.ELEVENLABS_API_KEY:
            warnings.append("ELEVENLABS_API_KEY is not set. ElevenLabs TTS will not function.")
        
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
