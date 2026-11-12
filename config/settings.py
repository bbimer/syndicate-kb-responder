from pathlib import Path
import os
from typing import Optional
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self):
        self.base_dir: Path = BASE_DIR
        self.kb_dir: Path = Path(os.getenv("KB_DIR", r"D:\Obsidian\Syndicate Intelligence\Syndicate Intelligence"))
        self.db_path: Path = self.base_dir / os.getenv("DB_PATH", "data/kb_index.db")
        
        self.openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
        self.deepseek_api_key: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
        
        # Base URL resolution
        default_base_url = "https://openrouter.ai/api/v1" if self.openrouter_api_key else "https://api.deepseek.com/v1"
        self.deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", default_base_url)
        
        # Model resolution
        default_model = "deepseek/deepseek-chat" if "openrouter.ai" in self.deepseek_base_url else "deepseek-chat"
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", default_model)
        
        self.max_tokens: int = int(os.getenv("MAX_TOKENS", "180"))
        self.temperature: float = float(os.getenv("TEMPERATURE", "0.4"))

    @property
    def api_key(self) -> str:
        """Returns the effective API key (DeepSeek or OpenRouter)."""
        key = self.deepseek_api_key or self.openrouter_api_key or ""
        return key.strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


settings = Settings()
