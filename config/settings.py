"""
The Architect — Configuration
All settings loaded from environment variables or .env file.
API keys NEVER in code, NEVER in YAML task files, NEVER in git.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class BudgetLimits(BaseSettings):
    """Per-provider and total budget limits (USD)."""
    claude_daily: float = 10.00
    claude_monthly: float = 200.00
    grok_daily: float = 5.00
    grok_monthly: float = 100.00
    openrouter_daily: float = 5.00
    openrouter_monthly: float = 100.00
    vast_daily: float = 20.00
    vast_monthly: float = 200.00
    twilio_daily: float = 5.00
    twilio_monthly: float = 50.00
    total_daily: float = 40.00
    total_monthly: float = 500.00
    self_improve_daily: float = 25.00
    self_improve_per_cycle: float = 5.00
    self_improve_monthly: float = 300.00
    warn_at: float = 0.70
    pause_at: float = 0.90
    emergency_only_at: float = 0.95


class Settings(BaseSettings):
    """Core platform settings. Override via env vars prefixed ARCHITECT_."""
    redis_url: str = "redis://localhost:6379/0"
    ollama_host: str = "http://localhost:11434"
    ollama_default_model: str = "qwen3.5:14b-q5_K_M"
    anthropic_api_key: str = ""
    xai_api_key: str = ""
    openrouter_api_key: str = ""
    vast_api_key: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    notify_phone_number: str = ""
    budget: BudgetLimits = Field(default_factory=BudgetLimits)
    prefer_local: bool = True
    local_confidence_threshold: float = 0.7
    max_concurrent_self_improve: int = 2
    self_improve_cooldown_seconds: int = 900
    max_daily_self_improve_cycles: int = 20
    mandatory_human_review_every_n: int = 50
    default_max_rounds: int = 3
    hard_max_rounds: int = 10
    guardrail_version: str = "1.0.0"
    platform_name: str = "The Architect"
    platform_version: str = "0.1.0"

    model_config = {"env_file": ".env", "env_prefix": "ARCHITECT_"}


settings = Settings()
