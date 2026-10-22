"""Config tests: env parsing, tier->model mapping, embed endpoint fallback.

Run by `uv run pytest`. Depends on: app.config only; no services required.
"""

import pytest

from app.config import Settings


def _settings(**env) -> Settings:
    # _env_file=None keeps a developer's local .env out of the assertions.
    return Settings(_env_file=None, **env)


def test_tier_to_model_map():
    s = _settings(
        llm_model_small="small-m",
        llm_model_smart="smart-m",
        llm_model_escalate="escalate-m",
        llm_model_extract="extract-m",
    )
    assert s.model_for_tier("small") == "small-m"
    assert s.model_for_tier("SMART") == "smart-m"  # case-insensitive
    assert s.models_by_tier == {
        "small": "small-m",
        "smart": "smart-m",
        "escalate": "escalate-m",
        "extract": "extract-m",
    }


def test_unknown_tier_raises():
    with pytest.raises(KeyError):
        _settings().model_for_tier("gigantic")


def test_embed_endpoint_defaults_to_chat_endpoint():
    s = _settings(llm_base_url="http://x:1/v1", llm_api_key="k")
    assert s.embed_base_url == "http://x:1/v1"
    assert s.embed_api_key == "k"


def test_embed_endpoint_can_be_overridden():
    s = _settings(llm_base_url="http://x:1/v1", embed_base_url="http://y:2/v1")
    assert s.embed_base_url == "http://y:2/v1"


def test_env_vars_are_read_uppercase(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SMART", "from-env")
    monkeypatch.setenv("EMBED_DIM", "1536")
    monkeypatch.setenv("SEED_ON_STARTUP", "false")
    s = Settings(_env_file=None)
    assert s.llm_model_smart == "from-env"
    assert s.embed_dim == 1536
    assert s.seed_on_startup is False


def test_prices_parse_from_json_env(monkeypatch):
    monkeypatch.setenv("LLM_PRICES_JSON", '{"gpt-5": {"input_per_1m": 1.25, "output_per_1m": 10.0}}')
    s = Settings(_env_file=None)
    assert s.llm_prices_json["gpt-5"]["output_per_1m"] == 10.0


def test_prices_default_empty():
    assert _settings().llm_prices_json == {}


# --- ENVIRONMENT=prod placeholder refusal (M16) ------------------------------
# The point of these: every credential in this repo is public (committed .env
# profiles, code defaults, deploy/aws/litellm.yaml), so the only safe prod
# behaviour is to refuse to start rather than to serve with them.

REAL = dict(
    environment="prod",
    staff_password="a-real-generated-password",
    s3_secret_key="a-real-s3-secret",
    llm_api_key="sk-real-key",
    embed_api_key="sk-real-key",
    session_secret="a-real-session-secret",
    web_origin="https://civic.example.gov",
)


def test_prod_with_placeholders_names_every_offender():
    with pytest.raises(ValueError) as exc:
        _settings(
            environment="prod",
            staff_password="staff",
            s3_secret_key="civicsecret",
            llm_api_key="sk-litellm-demo",
            embed_api_key="ollama",
            web_origin="http://localhost:3001",
        )
    message = str(exc.value)
    for name in ("STAFF_PASSWORD", "S3_SECRET_KEY", "LLM_API_KEY", "EMBED_API_KEY", "WEB_ORIGIN"):
        assert name in message, f"{name} missing from: {message}"


def test_prod_rejects_empty_secret():
    # "" is in the denylist: a secret nobody set is not a secret.
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "staff_password": ""})
    assert "STAFF_PASSWORD" in str(exc.value)


def test_prod_rejects_the_committed_session_secret():
    """M20: the resident cookie is only an HMAC, so the secret is the whole guard."""
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "session_secret": "dev-session-secret"})
    assert "SESSION_SECRET" in str(exc.value)


def test_prod_rejects_changeme():
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "s3_secret_key": "CHANGEME"})
    assert "S3_SECRET_KEY" in str(exc.value)


def test_prod_rejects_placeholder_inherited_by_the_embed_fallback():
    # EMBED_API_KEY unset copies LLM_API_KEY, so the denylist has to run after
    # that fallback or a placeholder walks in through the back door.
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "llm_api_key": "ollama", "embed_api_key": ""})
    assert "EMBED_API_KEY" in str(exc.value)
    assert "LLM_API_KEY" in str(exc.value)


def test_prod_rejects_localhost_web_origin_even_with_real_secrets():
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "web_origin": "https://civic.example.gov,http://localhost:3002"})
    assert "WEB_ORIGIN" in str(exc.value)


def test_prod_rejects_a_plaintext_web_origin():
    """Audit finding 8: prod validated placeholder *values* but never the scheme.

    A public `http://` origin means the staff session cookie and every resident
    message cross the wire in clear, so it is refused the same way `localhost`
    is — no hostname involved, the scheme alone is the offence.
    """
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "web_origin": "http://civic.example.gov"})
    assert "WEB_ORIGIN" in str(exc.value)


def test_prod_rejects_a_plaintext_origin_hidden_in_a_list():
    with pytest.raises(ValueError) as exc:
        _settings(**{**REAL, "web_origin": "https://civic.example.gov,http://203.0.113.10:3001"})
    assert "WEB_ORIGIN" in str(exc.value)


def test_prod_accepts_https_which_merely_starts_with_http():
    """`https://` does not contain `http://` — the check must not be a prefix test."""
    s = _settings(**{**REAL, "web_origin": "https://civic.example.gov,https://staff.example.gov"})
    assert s.web_origins == ["https://civic.example.gov", "https://staff.example.gov"]


def test_dev_with_placeholders_is_fine():
    # This is the committed demo: .env.bedrock copied to .env, nothing else.
    s = _settings(
        staff_password="staff",
        s3_secret_key="civicsecret",
        llm_api_key="sk-litellm-demo",
        web_origin="http://localhost:3001,http://localhost:3002",
    )
    assert s.environment == "dev"
    assert s.staff_password == "staff"


def test_prod_with_real_values_is_fine():
    s = _settings(**REAL)
    assert s.environment == "prod"
    assert s.web_origins == ["https://civic.example.gov"]


def test_unknown_environment_rejected():
    with pytest.raises(ValueError):
        _settings(environment="staging")


def test_cookie_secure_defaults_to_none_so_the_scheme_decides():
    assert _settings().cookie_secure is None


@pytest.mark.parametrize("value,expected", [("true", True), ("false", False)])
def test_cookie_secure_overrides_the_scheme(monkeypatch, value, expected):
    monkeypatch.setenv("COOKIE_SECURE", value)
    assert Settings(_env_file=None).cookie_secure is expected
