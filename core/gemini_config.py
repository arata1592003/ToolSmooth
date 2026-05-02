import os
from dotenv import load_dotenv

load_dotenv()

def load_gemini_models():
    models = os.getenv("GEMINI_MODELS", "")
    return [m.strip() for m in models.split(",") if m.strip()]

def load_default_model():
    return os.getenv("DEFAULT_GEMINI_MODEL")
