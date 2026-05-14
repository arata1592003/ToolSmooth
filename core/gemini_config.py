import os
import json

CONFIG_DIR = "configs"
MODEL_CONFIG_PATH = os.path.join(CONFIG_DIR, "models.json")

DEFAULT_MODELS = [
    "gemini-2.0-flash-lite-preview-02-05",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro"
]

def load_gemini_models():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    if not os.path.exists(MODEL_CONFIG_PATH):
        save_gemini_models(DEFAULT_MODELS)
        return DEFAULT_MODELS
    
    try:
        with open(MODEL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_MODELS

def save_gemini_models(models):
    with open(MODEL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(models, f, ensure_ascii=False, indent=4)

def load_default_model():
    models = load_gemini_models()
    return models[0] if models else "gemini-2.0-flash-lite-preview-02-05"
