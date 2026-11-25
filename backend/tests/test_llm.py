import httpx
import pytest

from app.services import llm as llm_mod
from app.services.llm import LLMClient, LLMError


def _resp(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://x/chat/completions"))


@pytest.mark.parametrize("status,body,expect", [
    (429, {"error": {"type": "insufficient_quota", "code": "credit_balance_exhausted"}}, "no credits"),
    (401, {"error": {"code": "invalid_api_key"}}, "rejected the API key"),
    (404, {"error": {"code": "model_not_found", "param": "gpt-x"}}, "not available"),
])
def test_fatal_errors_fail_fast_without_retry(monkeypatch, status, body, expect):
    calls = []
    monkeypatch.setattr(llm_mod.httpx, "post", lambda *a, **k: calls.append(1) or _resp(status, body))
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    client = LLMClient(api_key="sk-test")
    with pytest.raises(LLMError, match=expect):
        client.json_completion("s", "u")
    assert len(calls) == 1 and expect in client.last_error
    assert client.check()["ok"] is False


def test_rate_limit_is_retried(monkeypatch):
    seq = [_resp(429, {"error": {"type": "requests", "code": "rate_limit_exceeded"}}),
           _resp(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})]
    monkeypatch.setattr(llm_mod.httpx, "post", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    client = LLMClient(api_key="sk-test")
    assert client.json_completion("s", "u") == {"ok": True}
    assert client.last_error is None


def test_rate_limit_waits_as_long_as_provider_asks(monkeypatch):
    msg = {"error": {"message": "Rate limit reached ... Please try again in 7.25s.", "code": "rate_limit_exceeded"}}
    seq = [_resp(429, msg), _resp(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})]
    sleeps = []
    monkeypatch.setattr(llm_mod.httpx, "post", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleeps.append(s))
    assert LLMClient(api_key="k").json_completion("s", "u") == {"ok": True}
    assert sleeps == [7.75]
