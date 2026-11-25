"""Minimal OpenAI Chat Completions client over httpx (JSON mode).

We call the REST API directly instead of the `openai` SDK so the backend has no compiled
dependencies (some Windows machines block unsigned native extensions).
"""

import json
import re
import logging
import time

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.base_url = (base_url or settings.OPENAI_BASE_URL).rstrip("/")
        self.last_error: str | None = None  # last non-retryable error (shown in the dashboard)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def json_completion(self, system: str, user: str, temperature: float = 0.2,
                        max_tokens: int = 2000, retries: int = 4) -> dict:
        if not self.available:
            raise LLMError("OPENAI_API_KEY is not configured")
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if "gpt-oss" in self.model:
            # Reasoning models spend output tokens on thinking: keep it short and leave room for the answer.
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = max_tokens + 1500
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                resp = httpx.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=90)
            except httpx.HTTPError as e:  # network problem -> retry
                last_err = e
            else:
                fatal = self._fatal_error(resp)
                if fatal:
                    self.last_error = fatal
                    log.warning("LLM unavailable: %s", fatal)
                    raise LLMError(fatal)
                if resp.status_code in (429, 500, 502, 503, 504) or "json_validate_failed" in resp.text[:500]:
                    last_err = LLMError(f"OpenAI transient error {resp.status_code}: {resp.text[:200]}")
                    wait = self._retry_after(resp)
                    if wait is not None and attempt < retries - 1:
                        log.info("LLM rate limited, waiting %.1fs as requested by the provider", wait)
                        time.sleep(wait)
                        continue
                elif resp.status_code >= 400:
                    raise LLMError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
                else:
                    try:
                        data = json.loads(resp.json()["choices"][0]["message"]["content"])
                        self.last_error = None
                        return data
                    except (ValueError, KeyError, IndexError) as e:
                        last_err = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
        log.warning("LLM call failed: %s", last_err)
        raise LLMError(str(last_err))

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        """Seconds the provider asks us to wait (Retry-After header or 'try again in 7.5s'), capped at 60."""
        if resp.status_code != 429:
            return None
        header = resp.headers.get("retry-after")
        try:
            if header:
                return min(float(header) + 0.5, 60.0)
        except ValueError:
            pass
        m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", resp.text)
        if m:
            secs = float(m.group(2)) / (1000 if m.group(3) == "ms" else 1) + 60 * int(m.group(1) or 0)
            return min(secs + 0.5, 60.0)
        return 10.0

    def _fatal_error(self, resp: httpx.Response) -> str | None:
        """Errors that retrying cannot fix: bad key, no credits, unknown model."""
        if resp.status_code not in (401, 403, 404, 429):
            return None
        try:
            err = resp.json().get("error") or {}
        except ValueError:
            err = {}
        code, etype = err.get("code") or "", err.get("type") or ""
        if resp.status_code == 401 or code == "invalid_api_key":
            return "OpenAI rejected the API key (401). Check OPENAI_API_KEY in backend/.env."
        if etype == "insufficient_quota" or code in ("insufficient_quota", "credit_balance_exhausted"):
            return ("OpenAI account has no credits/quota. Add credits at "
                    "https://platform.openai.com/settings/organization/billing")
        if code == "model_not_found" or resp.status_code == 404:
            return (f"Model '{self.model}' is not available to this key at {self.base_url}. "
                    "Change OPENAI_MODEL in backend/.env.")
        if resp.status_code == 403:
            return f"OpenAI access denied (403): {err.get('message', '')[:200]}"
        return None

    def check(self) -> dict:
        """Live check of the key (used by the dashboard status)."""
        if not self.available:
            return {"ok": False, "error": "OPENAI_API_KEY is not set in backend/.env"}
        try:
            self.json_completion("Reply with JSON {\"ok\": true}.", "ping", max_tokens=300, retries=2)
            return {"ok": True, "error": None}
        except LLMError as e:
            return {"ok": False, "error": str(e)}


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Override (used by tests)."""
    global _client
    _client = client
