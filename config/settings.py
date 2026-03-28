"""
Platform-wide settings loaded from environment variables.

All secrets and connection strings live in .env — never hardcoded.
Uses pydantic-settings for typed validation with sensible defaults.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Providers ────────────────────────────────────────────────────────
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    openai_research_model: str = Field("gpt-4o-mini", env="OPENAI_RESEARCH_MODEL")
    openai_synthesis_model: str = Field("gpt-4o-mini", env="OPENAI_SYNTHESIS_MODEL")
    # Best-quality model for email composition — uses full research context
    openai_email_model: str = Field("gpt-4o", env="OPENAI_EMAIL_MODEL")

    # ── Local Storage ─────────────────────────────────────────────────────────
    nester_data_dir: str = Field("~/.nester", env="NESTER_DATA_DIR")

    # ── Mem0 (agent memory) ───────────────────────────────────────────────────
    mem0_llm_model: str = Field("gpt-4o-mini", env="MEM0_LLM_MODEL")
    mem0_embedding_model: str = Field("text-embedding-3-small", env="MEM0_EMBEDDING_MODEL")

    # ── Langfuse ─────────────────────────────────────────────────────────────
    langfuse_public_key: str = Field("", env="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field("", env="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field("http://localhost:3000", env="LANGFUSE_HOST")

    # ── OAuth2 Providers ──────────────────────────────────────────────────────
    # Google (Gmail, Calendar, Drive)
    google_client_id: str = Field("", env="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", env="GOOGLE_CLIENT_SECRET")

    # GitHub (repos, issues, PRs)
    github_client_id: str = Field("", env="GITHUB_CLIENT_ID")
    github_client_secret: str = Field("", env="GITHUB_CLIENT_SECRET")

    # Slack (messaging, channels)
    slack_client_id: str = Field("", env="SLACK_CLIENT_ID")
    slack_client_secret: str = Field("", env="SLACK_CLIENT_SECRET")

    # OAuth callback base URL (your backend)
    oauth_redirect_base: str = Field("http://localhost:8000", env="OAUTH_REDIRECT_BASE")

    # ── MCP Tool Credentials (fallback / non-OAuth) ─────────────────────────
    github_token: str = Field("", env="GITHUB_TOKEN")
    github_webhook_secret: str = Field("", env="GITHUB_WEBHOOK_SECRET")
    firecrawl_api_key: str = Field("", env="FIRECRAWL_API_KEY")
    tavily_api_key: str = Field("", env="TAVILY_API_KEY")
    slack_bot_token: str = Field("", env="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field("", env="SLACK_SIGNING_SECRET")

    # ── Email (fallback SMTP — replaced by Gmail OAuth when connected) ─────
    smtp_host: str = Field("smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(587, env="SMTP_PORT")
    smtp_user: str = Field("", env="SMTP_USER")
    smtp_password: str = Field("", env="SMTP_PASSWORD")

    # ── Browser (Playwright) ─────────────────────────────────────────────────
    playwright_headless: bool = Field(True, env="PLAYWRIGHT_HEADLESS")
    browser_pool_size: int = Field(2, env="BROWSER_POOL_SIZE")
    browser_page_timeout_ms: int = Field(30000, env="BROWSER_PAGE_TIMEOUT_MS")

    # ── Cost Budgets ─────────────────────────────────────────────────────────
    default_cost_budget_per_flow: float = Field(5.0, env="DEFAULT_COST_BUDGET_PER_FLOW")
    default_cost_budget_per_user: float = Field(50.0, env="DEFAULT_COST_BUDGET_PER_USER")
    cost_alert_threshold: float = Field(0.8, env="COST_ALERT_THRESHOLD")

    # ── Platform ─────────────────────────────────────────────────────────────
    platform_org_id: str = Field("nester", env="PLATFORM_ORG_ID")
    api_secret_key: str = Field("change-me", env="API_SECRET_KEY")
    log_level: str = Field("INFO", env="LOG_LEVEL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
