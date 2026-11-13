"""Клієнт до LLM через OpenAI-сумісний API (POST {base_url}/chat/completions).

Лише стандартна бібліотека. Ключ береться з конфігурації (змінні середовища / .env), ніколи не логується й не
потрапляє в тексти помилок. Адреса має бути https; http дозволено лише для localhost (локальна модель, тести).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_RESPONSE_BYTES = 1_000_000


class LlmError(RuntimeError):
    """Сервіс ШІ недоступний або відповів некоректно (503 для API). Текст безпечний для показу користувачу."""


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_s: float = 30.0

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def config_from(app_config) -> LlmConfig | None:
    """Конфігурація з Flask-налаштувань; None — поради вимкнені (немає адреси або моделі)."""
    base_url, model = app_config.get("LLM_BASE_URL"), app_config.get("LLM_MODEL")
    if not base_url or not model:
        return None
    return LlmConfig(base_url, model, app_config.get("LLM_API_KEY"), float(app_config.get("LLM_TIMEOUT_S") or 30))


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    local = (parts.hostname or "") in LOCAL_HOSTS
    if parts.scheme == "https" or (parts.scheme == "http" and local):
        return
    raise LlmError("LSE_LLM_BASE_URL має починатися з https:// (http дозволено лише для localhost)")


def chat(cfg: LlmConfig, system: str, user: str, max_tokens: int = 900) -> tuple[str, str]:
    """Один запит чату. Повертає (текст відповіді, назва моделі зі відповіді сервісу)."""
    _check_url(cfg.endpoint)
    payload = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "lunar-site-explorer"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    req = urllib.request.Request(cfg.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_s) as resp:  # noqa: S310 — адреса перевірена _check_url
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise LlmError(f"Сервіс ШІ відповів помилкою {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LlmError("Сервіс ШІ недоступний або не відповів вчасно") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise LlmError("Сервіс ШІ повернув надто велику відповідь")
    try:
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LlmError("Сервіс ШІ повернув відповідь у неочікуваному форматі") from None
    if not isinstance(text, str) or not text.strip():
        raise LlmError("Сервіс ШІ повернув порожню відповідь")
    return text, str(data.get("model") or cfg.model)
