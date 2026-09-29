"""HTTP 客户端：预算、转录、脱敏。"""

from __future__ import annotations

import pytest

from sothstan.http import ApiClient, ApiError, BudgetExceeded, Transcript
from sothstan.mockserver import AQUA, BREEZE, pseudo_tokens, shutdown_server, start_server


@pytest.fixture()
def aqua_server():
    server, url = start_server(AQUA)
    yield url
    shutdown_server(server)


def test_chat_returns_usage(aqua_server):
    client = ApiClient(base_url=aqua_server)
    resp = client.chat([{"role": "user", "content": "你好"}], "aqua-70b", max_tokens=1)
    assert resp.prompt_tokens is not None and resp.prompt_tokens > 0
    assert resp.content is not None
    assert resp.model_field == "aqua-70b"


def test_error_family_is_stable(aqua_server):
    client = ApiClient(base_url=aqua_server)
    with pytest.raises(ApiError) as e1:
        client.chat([{"role": "user", "content": "hi"}], "aqua-70b", temperature=42)
    with pytest.raises(ApiError) as e2:
        client.chat([{"role": "user", "content": "hi"}], "aqua-70b", temperature=42)
    assert e1.value.family == e2.value.family
    assert e1.value.family.startswith("400|")


def test_request_budget_circuit_breaks(aqua_server):
    client = ApiClient(base_url=aqua_server, max_requests=2)
    client.chat([{"role": "user", "content": "a"}], "aqua-70b", max_tokens=1)
    client.chat([{"role": "user", "content": "b"}], "aqua-70b", max_tokens=1)
    with pytest.raises(BudgetExceeded):
        client.chat([{"role": "user", "content": "c"}], "aqua-70b", max_tokens=1)


def test_token_budget_circuit_breaks(aqua_server):
    client = ApiClient(base_url=aqua_server, max_prompt_tokens=5)
    with pytest.raises(BudgetExceeded):
        client.chat(
            [{"role": "user", "content": "这句话足够长，一定会超过五个 token 的预算限制"}],
            "aqua-70b",
            max_tokens=1,
        )


def test_transcript_redacts_key_and_hashes_stable(aqua_server):
    t1 = Transcript()
    c1 = ApiClient(base_url=aqua_server, api_key="sk-secret", transcript=t1)
    c1.chat([{"role": "user", "content": "hi"}], "aqua-70b", max_tokens=1)
    h1 = t1.sha256()

    t2 = Transcript()
    c2 = ApiClient(base_url=aqua_server, api_key="sk-secret", transcript=t2)
    c2.chat([{"role": "user", "content": "hi"}], "aqua-70b", max_tokens=1)

    assert h1 == t2.sha256()
    assert "sk-secret" not in h1
    dumped = str(t1.canonical())
    assert "sk-secret" not in dumped
    assert "***REDACTED***" in dumped


def test_relay_rewrites_model_field():
    server, url = start_server(BREEZE, claim="aqua-70b")
    try:
        client = ApiClient(base_url=url)
        resp = client.chat([{"role": "user", "content": "你好"}], "aqua-70b", max_tokens=1)
        assert resp.model_field == "aqua-70b"  # 字段被改写
        # 但 token 数仍是 Breeze 的（现实中的大多数中转不会伪造 usage）
        aqua_tokens = pseudo_tokens(AQUA, "你好") + AQUA.overhead_per_msg
        assert resp.prompt_tokens != aqua_tokens
    finally:
        shutdown_server(server)


def test_breeze_rejects_huge_max_tokens():
    server, url = start_server(BREEZE)
    try:
        client = ApiClient(base_url=url)
        with pytest.raises(ApiError) as exc:
            client.chat([{"role": "user", "content": "hi"}], "breeze-8b", max_tokens=10**9)
        assert exc.value.status == 422  # detail 风格
    finally:
        shutdown_server(server)
