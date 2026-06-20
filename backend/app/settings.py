from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    google_api_key: str | None = None
    google_model: str = "gemini-2.0-flash"
    google_base_url: str | None = None
    # Vertex AI (same shape as voice2navigation/backend/.env)
    gemini_provider: str = "ai_studio"
    gcp_project: str | None = None
    gcp_location: str = "global"
    browser_headless: bool = False
    # Skip optional page.screenshot / CDP screencast in headed mode (prevents flashing)
    browser_skip_headed_screenshots: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720
    fuzzy_max_steps: int = 8
    vision_max_steps: int = 8
    # items data model
    inline_binary_max_bytes: int = 262144
    max_items_per_node: int = 10000
    # expression engine
    expr_max_len: int = 2048
    expr_max_nodes: int = 500
    expr_max_iter: int = 10000
    expr_timeout_ms: int = 250
    # oauth2 connect callback base (no trailing slash)
    oauth_callback_base: str = "http://localhost:8000"
    # frontend origin for post-oauth redirect (no trailing slash)
    frontend_base_url: str = "http://localhost:5173"
    # run artifacts
    artifact_retention_days: int = 30
    max_artifact_bytes: int = 52_428_800  # 50 MiB
    record_playwright_trace: bool = False
    har_enabled: bool = True
    video_recording_enabled: bool = False
    # browser livestream (CDP screencast over /ws/stream/{run_id})
    stream_fps: int = 8
    stream_jpeg_quality: int = 60
    stream_max_width: int = 1280
    # concurrent browser runs (context pool + dispatcher)
    max_concurrent_browser_runs: int = 3
    max_queue_depth: int = 100
    max_parked_contexts: int = 10
    session_idle_minutes: int = 30
    max_live_sessions: int = 5
    allow_parallel_per_workflow: bool = False
    # scheduler trigger hygiene (startup registration caps)
    trigger_max_active: int = 50
    trigger_stale_days: int = 30
    trigger_max_poll_per_workflow: int = 10
    # outbound webhooks
    webhook_max_attempts: int = 6
    webhook_backoff_schedule: list[int] = [60, 300, 1800, 7200, 21600]
    # public API
    rate_limit_per_min: int = 60
    # multi-user / org tenancy
    admin_email: str = "admin@localhost"
    admin_password: str | None = None
    bootstrap_platform_admin: bool = False
    session_secret: str = "change-me-in-production"
    single_user_mode: bool = False
    # selector action cache
    cache_max_misses: int = 3
    cache_ttl_days: int = 30
    cache_replay_timeout_ms: int = 3000
    # reCAPTCHA v2 (Google FAQ test keys — override via RECAPTCHA_* env vars)
    recaptcha_site_key: str = "6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"
    recaptcha_secret_key: str = "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe"
    # captcha / anti-bot / proxy
    captcha_detection_enabled: bool = True
    captcha_builtin_heuristics_enabled: bool = True
    captcha_solver: str = "manual"  # manual | external
    captcha_external_solver_url: str | None = None
    captcha_external_solver_key: str | None = None
    default_proxy_id: str | None = None
    proxy_url: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    antibot_stealth: bool = False
    antibot_user_agent: str | None = None
    antibot_locale: str | None = None
    antibot_timezone_id: str | None = None
    antibot_viewport_width: int | None = None
    antibot_viewport_height: int | None = None
    # computer use fallback (disabled by default)
    computer_use_enabled: bool = False
    computer_use_provider: str = "local_playwright"
    # credential backend default mount: local (Fernet vault) | env | vault
    credential_backend: str = "local"
    # read-only HTTP vault mount ({{cred.http_vault:<name>.<field>}})
    http_vault_url: str | None = None
    http_vault_auth_header: str | None = None
    # local runtime worker
    worker_heartbeat_interval_sec: int = 30
    worker_heartbeat_timeout_sec: int = 90
    worker_session_ttl_days: int = 30
    execution_backend: str = "full"  # full | control_plane_only
    # production / cloud
    database_url: str = "sqlite:///./auto_agent.db"
    cors_origins: str = "http://localhost:5173"
    # platform user OAuth (Google login)
    oauth_google_client_id: str | None = None
    oauth_google_client_secret: str | None = None
    bootstrap_oauth_only: bool = False
    oauth_password_login_enabled: bool = True
    oauth_signup_policy: str = "existing_users_only"  # existing_users_only | domain_allowlist
    oauth_allowed_email_domains: str = ""  # comma-separated when domain_allowlist
    oauth_default_role: str = "member"

    def enabled_oauth_providers(self) -> list[str]:
        providers: list[str] = []
        if self.oauth_google_client_id and self.oauth_google_client_secret:
            providers.append("google")
        return providers


settings = Settings()


def cors_origin_list() -> list[str]:
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


def apply_llm_env() -> None:
    """Push Vertex settings into os.environ for google.genai / ADK."""
    if settings.gemini_provider.lower() == "vertex" and settings.gcp_project:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.gcp_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.gcp_location


def llm_is_configured() -> bool:
    provider = (settings.llm_provider or "openai").lower()
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider in ("google", "gemini"):
        if settings.gemini_provider.lower() == "vertex" and settings.gcp_project:
            return True
        return bool(settings.google_api_key)
    return False


apply_llm_env()
