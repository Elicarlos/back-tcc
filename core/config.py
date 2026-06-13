import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

def obter_languagetool_url():
    url = os.getenv("LANGUAGETOOL_URL")
    if url:
        return url
    if os.path.exists("/.dockerenv"):
        return "http://languagetool:8010"
    return "https://api.languagetool.org"

class Settings:
    LANGUAGETOOL_URL: str = obter_languagetool_url()
    LANGUAGETOOL_TIMEOUT: float = float(os.getenv("LANGUAGETOOL_TIMEOUT", "30.0"))
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-pro")
    ENABLE_LLM: bool = os.getenv("ENABLE_LLM", "true").lower() == "true"
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

settings = Settings()
