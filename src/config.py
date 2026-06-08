from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./captures.db"
    max_retries: int = 3
    retry_base_delay_seconds: int = 30
    gateway_success_rate: float = 0.85
    execution_poll_interval_seconds: int = 60
    alert_threshold_hours: int = 48
    testing: bool = False


settings = Settings()
