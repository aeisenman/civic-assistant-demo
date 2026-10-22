"""The CI stub model server, exercised as a real subprocess over real HTTP.

Run by `uv run pytest`. Depends on: scripts/ci/stub_openai.py, httpx and a free
loopback port; no database, no S3, no model. The stub is the only thing standing
between compose-smoke and a $0 run, and it is the one file in the repo the unit
suite would otherwise never import, so it gets started the way CI starts it.
"""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.llm.router import Classification

STUB = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "stub_openai.py"

# Not 768 and not 1024: a wrong length can only pass if the flag is really read.
STUB_EMBED_DIM = 48


def _free_port() -> int:
    """Ask the kernel for a port nobody is listening on, then let it go."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def stub_url() -> str:
    """Start the stub on a free port, wait for /v1/models, stop it afterwards."""
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            str(STUB),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--embed-dim",
            str(STUB_EMBED_DIM),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/v1"
    try:
        for _ in range(100):
            if proc.poll() is not None:
                pytest.fail(f"stub exited early:\n{proc.stdout.read() if proc.stdout else ''}")
            try:
                httpx.get(f"{base}/models", timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            pytest.fail("stub never answered /v1/models")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_models_lists_the_three_tier_aliases(stub_url: str):
    body = httpx.get(f"{stub_url}/models", timeout=5).json()
    assert {m["id"] for m in body["data"]} == {"stub-small", "stub-smart", "stub-embed"}


def test_plain_chat_returns_the_fixed_reply(stub_url: str):
    body = httpx.post(
        f"{stub_url}/chat/completions",
        json={"model": "stub-small", "messages": [{"role": "user", "content": "hello"}]},
        timeout=5,
    ).json()
    assert body["choices"][0]["message"]["content"] == "CI stub reply."
    assert body["choices"][0]["finish_reason"] == "stop"


def test_json_schema_request_returns_a_valid_classification(stub_url: str):
    """The whole point: a routable turn instead of the error path.

    Before this, the stub answered `chat_json` with prose, the classifier raised
    and every CI chat turn ended in the fallback apology — the load-test caveat
    in docs/HARDENING_AUDIT.md.
    """
    schema = Classification.model_json_schema()
    body = httpx.post(
        f"{stub_url}/chat/completions",
        json={
            "model": "stub-small",
            "messages": [{"role": "user", "content": "hello"}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "Classification", "schema": schema},
            },
        },
        timeout=5,
    ).json()
    parsed = Classification.model_validate_json(body["choices"][0]["message"]["content"])
    assert parsed.intent == "smalltalk"
    assert parsed.complexity == "low"


def test_json_object_fallback_reads_the_schema_out_of_the_prompt(stub_url: str):
    """Bedrock's Anthropic models reject json_schema, so client.py pastes it inline."""
    schema = Classification.model_json_schema()
    prompt = f"Reply with JSON only against this JSON Schema named Classification:\n{json.dumps(schema)}"
    body = httpx.post(
        f"{stub_url}/chat/completions",
        json={
            "model": "stub-small",
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": "hi"}],
            "response_format": {"type": "json_object"},
        },
        timeout=5,
    ).json()
    assert Classification.model_validate_json(body["choices"][0]["message"]["content"]).intent == "smalltalk"


def test_offering_tools_still_gets_prose(stub_url: str):
    """The agent loop offers tools on every answer turn and wants text back."""
    body = httpx.post(
        f"{stub_url}/chat/completions",
        json={
            "model": "stub-smart",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"type": "function", "function": {"name": "get_trash_schedule", "parameters": {}}}],
        },
        timeout=5,
    ).json()
    assert body["choices"][0]["message"]["content"] == "CI stub reply."


def test_embeddings_honour_the_embed_dim_flag(stub_url: str):
    """`--embed-dim` exists so a CI job can run the stack at 1024 like prod does."""
    body = httpx.post(
        f"{stub_url}/embeddings",
        json={"model": "stub-embed", "input": ["one", "two"]},
        timeout=5,
    ).json()
    assert [len(row["embedding"]) for row in body["data"]] == [STUB_EMBED_DIM, STUB_EMBED_DIM]
    # Deterministic: the same text always embeds to the same vector, so a rerun
    # of the KB ingest does not churn the index.
    again = httpx.post(
        f"{stub_url}/embeddings", json={"model": "stub-embed", "input": ["one"]}, timeout=5
    ).json()
    assert again["data"][0]["embedding"] == body["data"][0]["embedding"]


def test_streaming_chat_ends_with_done(stub_url: str):
    with httpx.stream(
        "POST",
        f"{stub_url}/chat/completions",
        json={"model": "stub-small", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        timeout=5,
    ) as response:
        lines = [line for line in response.iter_lines() if line.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    text = "".join(json.loads(line[6:])["choices"][0]["delta"].get("content", "") for line in lines[:-1])
    assert text == "CI stub reply."


def test_unknown_route_is_a_json_404(stub_url: str):
    response = httpx.post(f"{stub_url}/completions", json={}, timeout=5)
    assert response.status_code == 404
    assert "no stub route" in response.json()["error"]["message"]
