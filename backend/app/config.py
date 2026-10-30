from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="BOM_", extra="ignore")

    database_url: str = "postgresql+psycopg://bom:bom@localhost:5432/bom"
    test_database_url: str = "postgresql+psycopg://bom:bom@localhost:5432/bom_test"
    pkr_per_usd: float = 270.0
    environment: str = "dev"
    airtable_token: str | None = None
    airtable_base_id: str | None = None
    jwt_secret: str = "change-me-in-production"
    jwt_ttl_hours: int = 12
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    bootstrap_admin_email: str | None = None  # first admin, created on startup if no users exist
    bootstrap_admin_password: str | None = None


settings = Settings()
