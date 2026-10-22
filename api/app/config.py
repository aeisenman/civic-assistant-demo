"""Every runtime knob in one typed object, read from the environment.

Read by nearly every module (llm client, db engine, storage, health); populated
from .env via docker compose `env_file`. Depends on: pydantic-settings only.
"""

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Field names are lower-case; env vars are the upper-case equivalents."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # --- Deployment mode ----------------------------------------------------
    # "dev" is the default so the committed .env.* profiles and a bare `pytest`
    # keep working untouched. "prod" turns on _refuse_placeholder_secrets below:
    # anything that ships in this repo as a demo credential becomes a hard
    # startup failure rather than a box on the internet with password "staff".
    environment: Literal["dev", "prod"] = "dev"

    # --- Postgres -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://civic:civic@db:5432/civic"

    # --- SeaweedFS (S3 API) -------------------------------------------------
    s3_endpoint: str = "http://seaweedfs:8333"
    s3_access_key: str = "civic"
    s3_secret_key: str = "civicsecret"
    s3_bucket: str = "civic-docs"

    # --- Chat models: logical tiers, concrete names per provider ------------
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str = "ollama"
    llm_model_small: str = "qwen2.5:3b"
    llm_model_smart: str = "qwen2.5:7b"
    llm_model_escalate: str = "qwen2.5:7b"
    llm_model_extract: str = "qwen2.5:7b-32k"

    # --- Embeddings (same protocol; defaults to the chat endpoint) ----------
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768

    # --- Live City data (M8) ------------------------------------------------
    # Off switches the geocoder, the ArcGIS lookups and the RSS merge back to
    # seed data, so the demo still answers on a plane.
    live_data_enabled: bool = True
    live_http_timeout_s: float = 4.0
    # "brave" needs SEARCH_API_KEY; "none" makes search_city_website report that
    # it is not configured, which is the honest answer for an unkeyed clone.
    search_provider: str = "none"
    search_api_key: str = ""

    # --- Staff login (M11) --------------------------------------------------
    # One seeded back-office account; the seed loader upserts it at startup and
    # re-hashes the password, so changing STAFF_PASSWORD here changes the login.
    staff_username: str = "staff"
    staff_password: str = "staff"
    staff_display_name: str = "City Staff"
    # The browser origin allowed to send the session cookie. A wildcard cannot
    # carry credentials, so this has to be the exact origin the web app runs on.
    # Comma-separated when more than one is needed (the compose web container on
    # :3001 and the Playwright dev server on :3002).
    web_origin: str = "http://localhost:3001"
    # None means "decide from the request scheme", which is what app/api/auth.py
    # did unconditionally before. Behind a TLS-terminating proxy the scheme the
    # app sees is http even though the browser spoke https, so the cookie would
    # go out without Secure; set COOKIE_SECURE=true there. Explicit false exists
    # for the reverse case (a plain-http demo box), and is the reason this is a
    # tri-state rather than a bool with a default.
    cookie_secure: bool | None = None

    # --- Resident sessions (M20) -------------------------------------------
    # The key the `resident_session` cookie is HMAC'd with (app/resident_session.py).
    # Nothing about a resident is stored server-side, so this one value is what
    # stops a leaked session id from replaying someone else's conversation.
    # Changing it invalidates every resident cookie, which costs a resident a new
    # conversation and costs the operator nothing; it is on the placeholder
    # denylist below so prod cannot ship with the committed default.
    session_secret: str = "dev-session-secret"

    # --- Request bounds and cost controls (M14) -----------------------------
    # Defaults are deliberately generous: they are a ceiling on abuse, not on the
    # demo. Every one of them keeps the .env.bedrock walkthrough working as-is.
    # A resident question is a sentence, not a novel; 4000 chars is ~1k tokens.
    max_message_chars: int = 4000
    # Anonymous sessions are free to create, so the cap is per session id and is
    # only there to stop one browser tab looping the model forever.
    max_turns_per_session: int = 200
    # Circuit breaker on the day's spend, summed from the traces table before the
    # classifier runs. $25 is far above a demo day and far below a surprise bill.
    daily_cost_cap_usd: float = 25.0
    # Each stream holds a DB session for the whole turn; the pool is 5+10, so
    # unbounded concurrency turns into pool starvation and 30s waits.
    max_concurrent_streams: int = 16
    # The openai SDK defaults to a 600s read timeout, which means a hung provider
    # can hold a stream (and its DB session) for ten minutes.
    llm_timeout_s: float = 45.0

    # --- Per-IP rate limit (M26a) -------------------------------------------
    # A token bucket in Postgres (app/rate_limit.py) on the four routes a
    # stranger can reach. The load test filed 30 applications in 0.22s from one
    # address; the session-id guards did not notice because the attacker chooses
    # the session id. Defaults are far above a human using the web app (a burst
    # of 20 then 30/minute) and far below a script.
    rate_limit_enabled: bool = True
    rate_limit_burst: int = 20
    rate_limit_per_minute: float = 30.0

    # --- Trace retention (M26a) ---------------------------------------------
    # 0 = keep everything, which is the demo default: a reviewer wants to open
    # /staff/traces and see the conversation they just had. Set it to a number of
    # days in a real deployment and the worker sweeps `traces` and
    # `chat_messages` nightly. Note before choosing a number: California's CPRA
    # requires a public agency to keep records of a resident interaction for at
    # least two years (Gov. Code §7922.600 territory), so 730 is the floor for a
    # real City, not 90 — the shorter windows people reach for first would be a
    # records-retention violation rather than a privacy win.
    trace_retention_days: int = 0

    # --- Startup behaviour --------------------------------------------------
    seed_on_startup: bool = True
    ingest_kb_on_startup: bool = True
    # The workflow worker runs in the API process; turn it off to step an
    # application through its statuses by hand from the staff page.
    worker_enabled: bool = True
    worker_interval_seconds: float = 3

    # model name -> {"input_per_1m": USD, "output_per_1m": USD}. Empty means $0,
    # which is the truth for Ollama.
    llm_prices_json: dict[str, dict[str, float]] = Field(default_factory=dict)

    # Gateway alias ("smart") -> the model that actually answers ("claude-sonnet-4-6").
    # The trace can only record the name we send, which is the alias; this map is
    # how /health and the UI say which model that alias resolved to. Empty means
    # "the alias is the model name" (true for the Ollama profile).
    llm_provider_models_json: dict[str, str] = Field(default_factory=dict)

    #: Values that exist in this repository (committed .env profiles, code
    #: defaults, deploy/aws/litellm.yaml) and therefore are public. Empty string
    #: is in here too: a secret nobody set is not a secret.
    PLACEHOLDER_SECRETS: ClassVar[frozenset[str]] = frozenset(
        {
            "staff",
            "civic",
            "civicsecret",
            "sk-litellm-demo",
            "ollama",
            "dev-session-secret",
            "CHANGEME",
            "",
        }
    )

    @model_validator(mode="after")
    def _default_embed_endpoint(self) -> "Settings":
        """Most providers serve chat and embeddings from the same base URL."""
        if not self.embed_base_url:
            self.embed_base_url = self.llm_base_url
        if not self.embed_api_key:
            self.embed_api_key = self.llm_api_key
        return self

    @model_validator(mode="after")
    def _refuse_placeholder_secrets(self) -> "Settings":
        """In ENVIRONMENT=prod, fail closed on anything this repo ships publicly.

        Defined after _default_embed_endpoint on purpose: pydantic runs
        mode="after" model validators in definition order, so EMBED_API_KEY has
        already inherited LLM_API_KEY by the time it is checked here and a
        prod deploy cannot slip a placeholder in through the fallback.

        The message names every offending setting at once, because an operator
        fixing a deploy at 2am should need one restart, not four.
        """
        if self.environment != "prod":
            return self

        offenders = [
            name
            for name in (
                "staff_password",
                "s3_secret_key",
                "llm_api_key",
                "embed_api_key",
                "session_secret",
            )
            if getattr(self, name) in self.PLACEHOLDER_SECRETS
        ]
        # localhost in an allowed CORS origin in prod means either the deploy
        # script did not rewrite it (the browser origin is the public IP, so
        # every fetch would fail CORS anyway) or someone is about to trust a
        # local page with a session cookie.
        #
        # `http://` is the same class of mistake with a worse outcome (audit
        # finding 8): an allowed plaintext origin means the staff session cookie
        # and every resident message cross the wire in clear, and the scheme
        # check is also what makes COOKIE_SECURE default correctly. Note that
        # "https://" does not contain "http://", so only real plaintext trips it.
        if "localhost" in self.web_origin or "http://" in self.web_origin:
            offenders.append("web_origin")

        if offenders:
            raise ValueError(
                "ENVIRONMENT=prod refuses placeholder configuration. Set a real value for: "
                + ", ".join(sorted(o.upper() for o in offenders))
                + ". (These are demo values committed to the repository, so they are public.)"
            )
        return self

    def model_for_tier(self, tier: str) -> str:
        """Map a tier name ("small"/"smart"/"escalate"/"extract") to a model."""
        return {
            "small": self.llm_model_small,
            "smart": self.llm_model_smart,
            "escalate": self.llm_model_escalate,
            "extract": self.llm_model_extract,
        }[tier.lower()]

    @property
    def web_origins(self) -> list[str]:
        """WEB_ORIGIN split on commas — what CORS `allow_origins` receives."""
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]

    @property
    def models_by_tier(self) -> dict[str, str]:
        """Reported by /health so the demo can show which models are live."""
        return {t: self.model_for_tier(t) for t in ("small", "smart", "escalate", "extract")}


@lru_cache
def get_settings() -> Settings:
    """Cached so every import sees the same object; cache_clear() in tests."""
    return Settings()


settings = get_settings()
