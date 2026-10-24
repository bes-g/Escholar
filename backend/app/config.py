"""Runtime settings. Secrets come from the environment, never from the frontend."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    database_url: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_reasoning_effort: str = "low"
    max_tool_calls: int = 8
    frontend_dist: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        url = (self.database_url or "").strip()
        if not url:
            data_dir = BACKEND_DIR / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{data_dir / 'escholar.db'}"
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://") :]
        if url.startswith("postgresql://") and "+psycopg" not in url.split("://", 1)[0]:
            return "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def resolved_frontend_dist(self) -> Path:
        if self.frontend_dist.strip():
            return Path(self.frontend_dist).expanduser().resolve()
        return REPO_DIR / "frontend" / "dist"

    @property
    def model_configured(self) -> bool:
        return bool(self.llm_api_key.strip())


settings = Settings()
