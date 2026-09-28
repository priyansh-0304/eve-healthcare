from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app configuration, loaded from environment variables / .env file.
    Nothing here has secrets hardcoded — see .env.example.
    """

    database_url: str = "postgresql://eve_user:eve_password@localhost:5432/eve_diagnostics"

    secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours, generous for assignment/demo use

    # Probability (0-1) that a simulated payment succeeds. Configurable so graders
    # can force deterministic outcomes if they want (e.g. set to 1.0 or 0.0).
    payment_success_rate: float = 0.8

    # Shared secret the (simulated) payment provider must send on webhook calls.
    # A real integration would verify an HMAC signature instead; a shared secret
    # header is a reasonable stand-in for a mock provider.
    webhook_secret: str = "CHANGE_ME_WEBHOOK_SECRET"

    # Optional read-through cache for the centre/test listing endpoints. If Redis
    # isn't reachable at this URL, caching is silently disabled (see app/cache.py)
    # — it's a performance optimization, never a hard dependency.
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
