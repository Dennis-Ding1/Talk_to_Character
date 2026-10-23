from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    boson_api_key: str = ""
    boson_base_url: str = "https://api.boson.ai/v1"

    data_dir: Path = Path("data/movies")

    llm_backend: str = "ollama"  # "ollama" | "higgs_text"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"

    frontend_origin: str = "http://localhost:5173"

    # How much recent dialogue (seconds before t) goes verbatim into the prompt
    recent_window_s: float = 180.0

    @property
    def movies_dir(self) -> Path:
        return self.data_dir if self.data_dir.is_absolute() else REPO_ROOT / self.data_dir


@lru_cache
def get_settings() -> Settings:
    return Settings()
