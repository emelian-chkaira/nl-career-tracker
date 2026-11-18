"""Typed settings from environment variables / .env (12-factor). Nothing deployment-specific is hard-coded elsewhere."""
from functools import lru_cache
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAREERS_", env_file=(".env", "../.env"), extra="ignore", populate_by_name=True)

    # --- infrastructure
    database_url: str = Field("postgresql+psycopg://careers:careers@localhost:5433/careers", validation_alias=AliasChoices("DATABASE_URL", "CAREERS_DATABASE_URL"))
    db_pool_size: int = 10
    data_dir: str = "./data"                      # logos, uploads
    env: str = "dev"                              # dev | prod
    # --- security
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    access_ttl_min: int = 30
    refresh_ttl_days: int = 30
    cors_origins: str = "http://localhost:5173,http://localhost:8787"
    rate_limit_per_min: int = 240
    auth_rate_limit_per_min: int = 20
    allow_registration: bool = True
    firebase_api_key: str | None = None            # Firebase project Web API key: when set, Firebase Authentication is the identity provider
    google_client_id: str | None = None           # OAuth client ID(s) from Google Cloud Console, comma separated (web, iOS, Android)
    require_verified_email: bool = False          # true: sign-in is refused until the address is confirmed
    verify_ttl_hours: int = 48
    reset_ttl_min: int = 60
    admin_emails: str = ""                        # comma separated: these accounts get the admin role on sign-up
    cookie_secure: bool = False
    trust_proxy: bool = False
    # --- crawler identity
    contact: str = "https://github.com/your-org/nl-career-tracker"
    brave_api_key: str | None = None
    browser_slots: int = 3
    scan_threads: int = 10
    # --- search / semantic
    embedding_model: str = "BAAI/bge-small-en-v1.5"   # 384-d, local ONNX via fastembed
    embedding_dim: int = 384
    semantic_enabled: bool = True
    # --- alerts / email
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_security: str = "starttls"                # starttls (587) | ssl (465) | none (local test servers such as Mailpit)
    mail_from: str = "CareerNL <no-reply@localhost>"
    public_url: str = "http://localhost:5173"        # used in email links
    # --- optional
    anthropic_api_key: str | None = None
    latex_compile: bool = True

    @property
    def user_agent(self) -> str: return f"nl-career-tracker/0.3 (+{self.contact})"
    @property
    def firebase_on(self) -> bool: return bool(self.firebase_api_key)
    @property
    def google_ids(self) -> list[str]: return [c.strip() for c in (self.google_client_id or "").split(",") if c.strip()]
    @property
    def cors_list(self) -> list[str]: return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
    @property
    def admin_list(self) -> set[str]: return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings: return Settings()
settings = get_settings()
