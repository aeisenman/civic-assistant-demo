#!/usr/bin/env python3
"""A fake OpenAI-protocol server so CI can boot the API without a real model.

Started by .github/workflows/compose-smoke.yml before `docker compose up`; the
api container reaches it on host.docker.internal:4010 via .env.ci. Depends on
nothing but the standard library, so the workflow needs no Python install step.
"""

import argparse
import hashlib
import json
import re
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# One canned answer for every plain chat call. Short on purpose: compose-smoke
# proves the wiring (api -> gateway -> reply), never the quality of a reply.
REPLY = "CI stub reply."

# Set once by main(). Prod runs Titan v2 at 1024 while the local Ollama profile
# is 768, and migration 002 bakes whichever one is configured into the vector
# column, so CI runs the whole stack at both widths and the stub has to follow.
EMBED_DIM = 768

# The answer handed back when a caller asks for JSON but the request carries no
# schema we can read. It is a valid `app.llm.router.Classification`, which is
# the only schema the API needs before it can route a turn at all: without it
# every chat turn takes the error path and the smoke check proves nothing but
# the apology template (the load-test caveat in docs/HARDENING_AUDIT.md).
CLASSIFICATION = {
    "intent": "smalltalk",
    "confidence": 0.95,
    "complexity": "low",
    "secondary_intents": [],
}

# Preferred over "the first enum member" when a schema offers a choice, so a
# Literal["permits", ..., "smalltalk"] resolves to the one intent whose profile
# calls no tools and retrieves nothing — the cheapest path through a turn.
PREFERRED_ENUM = ("smalltalk", "low")

# app/llm/client.py's json_object fallback pastes the schema into the prompt
# ("...against this JSON Schema named Classification:\n{...}") for models that
# reject a json_schema response_format. Bedrock's Anthropic models do exactly
# that, so the stub has to be able to read the schema back out of the text.
SCHEMA_IN_PROMPT = re.compile(r"JSON Schema named \w+:\s*(\{.*)", re.DOTALL)


def fake_vector(text: str, dim: int | None = None) -> list[float]:
    """A deterministic vector for `text`, so a rerun embeds the KB identically.

    SHA-256 of the text seeds a counter hash chain; each 4-byte word becomes a
    float in [-1, 1). Same text in, same vector out, and no numpy dependency.
    """
    dim = EMBED_DIM if dim is None else dim
    out: list[float] = []
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    counter = 0
    while len(out) < dim:
        block = hashlib.sha256(seed + struct.pack(">I", counter)).digest()
        for i in range(0, len(block), 4):
            if len(out) >= dim:
                break
            (word,) = struct.unpack(">I", block[i : i + 4])
            out.append((word / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    return out


# --------------------------------------------------------------- JSON answers
def _resolve(node: dict, defs: dict) -> dict:
    """Follow a local `$ref` into `$defs`; anything else comes back unchanged."""
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return defs.get(ref.split("/")[-1], {})
    return node


def value_for(node: dict, defs: dict) -> object:
    """The smallest value that satisfies one JSON Schema node.

    Deliberately dumb: enums pick a preferred member, numbers pick 0.95 (inside
    every ge/le bound this repo uses), containers come back empty. That covers
    `Classification` exactly and keeps the stub honest about what it is —
    plumbing under test, not a model.
    """
    node = _resolve(node, defs)
    if "const" in node:
        return node["const"]
    for branch in node.get("anyOf") or node.get("oneOf") or []:
        resolved = _resolve(branch, defs)
        if resolved.get("type") != "null":
            return value_for(resolved, defs)
    enum = node.get("enum")
    if enum:
        for preferred in PREFERRED_ENUM:
            if preferred in enum:
                return preferred
        return enum[0]
    kind = node.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "string")
    if kind == "object":
        return object_for(node, defs)
    if kind == "array":
        return []
    if kind == "integer":
        return 1
    if kind == "number":
        return 0.95
    if kind == "boolean":
        return False
    return ""


def object_for(schema: dict, defs: dict) -> dict:
    """Fill every property of an object schema; nothing required is left out."""
    props = schema.get("properties") or {}
    return {name: value_for(node, defs) for name, node in props.items()}


def _schema_in_messages(body: dict) -> dict | None:
    """Pull a schema back out of a prompt written by client._schema_in_prompt."""
    for message in reversed(body.get("messages") or []):
        content = message.get("content")
        if not isinstance(content, str):
            continue
        found = SCHEMA_IN_PROMPT.search(content)
        if not found:
            continue
        try:
            return json.loads(found.group(1))
        except json.JSONDecodeError:
            continue
    return None


def schema_from(body: dict) -> dict | None:
    """The JSON Schema this chat request wants back, or None if it wants prose.

    Three shapes reach us: a `json_schema` response_format (most providers), a
    bare `json_object` response_format with the schema pasted into the prompt
    (the Bedrock fallback in app/llm/client.py), and a `tool_choice` naming one
    function, whose `parameters` are the schema. A request that merely *offers*
    tools is not one of them: the agent loop offers tools on every answer turn
    and wants prose back, so answering it with JSON would break the reply.
    """
    fmt = body.get("response_format") or {}
    if fmt.get("type") == "json_schema":
        return (fmt.get("json_schema") or {}).get("schema") or {}
    choice = body.get("tool_choice")
    wanted = choice.get("function", {}).get("name") if isinstance(choice, dict) else None
    if wanted:
        for tool in body.get("tools") or []:
            fn = tool.get("function") or {}
            if fn.get("name") == wanted:
                return fn.get("parameters") or {}
    if fmt.get("type") == "json_object" or choice in ("required", "any"):
        return _schema_in_messages(body) or {}
    return None


def json_answer(schema: dict) -> str:
    """A JSON string that validates against `schema`, as chat message content."""
    if not schema.get("properties"):
        return json.dumps(CLASSIFICATION)
    return json.dumps(object_for(schema, schema.get("$defs") or {}))


def answer_for(body: dict) -> str:
    """Content for one chat request: JSON when it asked for JSON, prose otherwise."""
    schema = schema_from(body)
    return REPLY if schema is None else json_answer(schema)


def chat_body(model: str, content: str = REPLY) -> dict:
    """A minimal non-streaming chat completion the openai SDK will parse."""
    return {
        "id": "chatcmpl-ci-stub",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 3, "total_tokens": 4},
    }


def stream_frames(model: str, content: str = REPLY) -> list[str]:
    """SSE frames for `stream: true`: a role frame, the words, stop, [DONE]."""

    def frame(delta: dict, finish: str | None = None) -> str:
        payload = {
            "id": "chatcmpl-ci-stub",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload)}\n\n"

    # Split into pieces that still concatenate back to `content` exactly, so a
    # client that joins the deltas gets the same text the non-stream route gives.
    pieces = re.findall(r"\S+\s*", content)
    frames = [frame({"role": "assistant", "content": ""})]
    frames += [frame({"content": piece}) for piece in pieces]
    frames.append(frame({}, finish="stop"))
    frames.append("data: [DONE]\n\n")
    return frames


class Handler(BaseHTTPRequestHandler):
    """Three routes, no state; every unknown path is an honest 404 JSON body."""

    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        """One readable line per request in the Actions log, no client address."""
        print("stub_openai: " + (fmt % args), flush=True)

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": name, "object": "model", "created": 0, "owned_by": "ci-stub"}
                        for name in ("stub-small", "stub-smart", "stub-embed")
                    ],
                },
            )
            return
        self._json(404, {"error": {"message": f"no stub route for {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        body = self._read_json()
        path = self.path.rstrip("/")
        model = body.get("model") or "stub-small"

        if path in ("/v1/chat/completions", "/chat/completions"):
            content = answer_for(body)
            if body.get("stream"):
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "close")
                self.end_headers()
                for chunk in stream_frames(model, content):
                    self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
                # HTTP/1.1 with no content-length: the close is the terminator.
                self.close_connection = True
                return
            self._json(200, chat_body(model, content))
            return

        if path in ("/v1/embeddings", "/embeddings"):
            raw = body.get("input") or [""]
            texts = [raw] if isinstance(raw, str) else [str(t) for t in raw]
            self._json(
                200,
                {
                    "object": "list",
                    "model": model,
                    "data": [
                        {"object": "embedding", "index": i, "embedding": fake_vector(t)}
                        for i, t in enumerate(texts)
                    ],
                    "usage": {"prompt_tokens": len(texts), "total_tokens": len(texts)},
                },
            )
            return

        self._json(404, {"error": {"message": f"no stub route for {self.path}"}})


def main() -> None:
    global EMBED_DIM
    parser = argparse.ArgumentParser(description="Stub OpenAI-protocol server for CI")
    # 0.0.0.0 on purpose: the api container reaches it over host.docker.internal.
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=4010)
    parser.add_argument(
        "--embed-dim",
        type=int,
        default=EMBED_DIM,
        help="vector length /v1/embeddings returns; must equal EMBED_DIM (default 768)",
    )
    args = parser.parse_args()
    EMBED_DIM = args.embed_dim
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"stub_openai listening on {args.host}:{args.port} (embed dim {EMBED_DIM})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
