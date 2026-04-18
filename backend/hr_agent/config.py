from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "HR Recruitment Agent"
    database_url: str = "sqlite+aiosqlite:///./hr_agent.db"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    mock_llm: bool = False
    mock_email: bool = True
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    hr_notify_email: str = "hr@example.com"
    default_meeting_base: str = "https://meet.google.com"
    ats_pass_threshold: float = 80.0
    interview_question_count: int = 3
    interview_answer_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
