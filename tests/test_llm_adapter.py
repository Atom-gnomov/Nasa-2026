"""Клієнт LLM: справжній HTTP-обмін із локальним тестовим сервером (OpenAI-сумісний /chat/completions)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.adapters import llm

TOKEN = "test-secret-token-do-not-leak"


class Handler(BaseHTTPRequestHandler):
    seen: list[dict] = []
    mode = "ok"

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Handler.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if Handler.mode == "401":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "bad key %s"}' % TOKEN.encode())
            return
        payload = {"ok": {"model": "fake-1", "choices": [{"message": {"content": '{"summary": "ok"}'}}]},
                   "bad": {"unexpected": True}, "empty": {"choices": [{"message": {"content": "  "}}]}}[Handler.mode]
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # тиша в тестах
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    Handler.seen, Handler.mode = [], "ok"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def cfg(base, key=TOKEN):
    return llm.LlmConfig(base, "fake-model", key, timeout_s=5)


def test_roundtrip_sends_bearer_and_openai_payload(server):
    text, model = llm.chat(cfg(server), "системна інструкція", "запит користувача")
    assert (text, model) == ('{"summary": "ok"}', "fake-1")
    seen = Handler.seen[0]
    assert seen["path"] == "/v1/chat/completions" and seen["auth"] == f"Bearer {TOKEN}"
    assert seen["body"]["model"] == "fake-model"
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


def test_endpoint_accepts_full_url_and_no_auth_without_key(server):
    llm.chat(cfg(server + "/chat/completions", key=None), "s", "u")
    assert Handler.seen[0]["path"] == "/v1/chat/completions" and Handler.seen[0]["auth"] is None


@pytest.mark.parametrize("mode, text", [("bad", "неочікуваному форматі"), ("empty", "порожню")])
def test_malformed_responses_raise_llm_error(server, mode, text):
    Handler.mode = mode
    with pytest.raises(llm.LlmError, match=text):
        llm.chat(cfg(server), "s", "u")


def test_http_error_never_leaks_key_or_body(server):
    Handler.mode = "401"
    with pytest.raises(llm.LlmError) as err:
        llm.chat(cfg(server), "s", "u")
    assert "401" in str(err.value) and TOKEN not in str(err.value) and "bad key" not in str(err.value)


def test_unreachable_service(server):
    with pytest.raises(llm.LlmError, match="недоступний"):
        llm.chat(cfg("http://127.0.0.1:1/v1"), "s", "u")


@pytest.mark.parametrize("url", ["http://example.com/v1", "ftp://example.com", "example.com/v1"])
def test_plain_http_to_remote_hosts_is_refused(url):
    with pytest.raises(llm.LlmError, match="https"):
        llm.chat(cfg(url), "s", "u")


def test_config_from_requires_url_and_model():
    assert llm.config_from({}) is None
    assert llm.config_from({"LLM_BASE_URL": "https://x/v1"}) is None
    c = llm.config_from({"LLM_BASE_URL": "https://x/v1", "LLM_MODEL": "m", "LLM_API_KEY": "k", "LLM_TIMEOUT_S": "7"})
    assert (c.base_url, c.model, c.api_key, c.timeout_s) == ("https://x/v1", "m", "k", 7.0)
