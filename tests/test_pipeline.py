"""端到端管线：在 mock 服务器上验证全部判决行为（无网络、无 key）。

这组测试就是Sothstan的核心主张：
1. 诚实服务器 → AUTHENTIC
2. 换模型中转（只改 model 字段）→ MISMATCH，且 runner-up 正确指向替代模型
3. 只改 model 字段、其余诚实 → 仍 AUTHENTIC（证明字段回显骗不过指纹）
4. 完美说谎中转（改字段 + 用声称模型的 tokenizer 重算 usage）→ 行为/错误层仍暴露
"""

from __future__ import annotations

import pytest

from sothstan.baseline import load_registry
from sothstan.mockserver import AQUA, BREEZE, shutdown_server, start_server
from sothstan.runner import verify
from sothstan.types import VerdictLabel

REGISTRY = load_registry()
AQUA_B = REGISTRY["aqua-70b"]
BREEZE_B = REGISTRY["breeze-8b"]


@pytest.fixture()
def honest_aqua():
    server, url = start_server(AQUA)
    yield url
    shutdown_server(server)


@pytest.fixture()
def relay_breeze():
    server, url = start_server(BREEZE, claim="aqua-70b")
    yield url
    shutdown_server(server)


@pytest.fixture()
def liar_relay():
    server, url = start_server(BREEZE, claim="aqua-70b", liar_usage=AQUA)
    yield url
    shutdown_server(server)


def test_honest_endpoint_is_authentic(honest_aqua):
    r = verify(honest_aqua, "aqua-70b", AQUA_B, [BREEZE_B])
    assert r.verdict.label is VerdictLabel.AUTHENTIC
    assert r.verdict.runner_up == "breeze-8b"
    assert r.verdict.margin_total > 0
    assert r.requests_used < 64  # 预算内完成
    assert len(r.transcript_sha256) == 64


def test_model_swap_relay_is_mismatch(relay_breeze):
    r = verify(relay_breeze, "aqua-70b", AQUA_B, [BREEZE_B])
    assert r.verdict.label is VerdictLabel.MISMATCH
    assert r.verdict.runner_up == "breeze-8b"
    assert r.verdict.margin_total < 0


def test_field_spoof_alone_is_not_enough():
    """把诚实 Aqua 的 model 字段改成别的名字——判决不受影响（权重为 0 的教训）。"""
    s, u = start_server(AQUA, claim="totally-not-aqua")
    try:
        r = verify(u, "aqua-70b", AQUA_B, [BREEZE_B])
        assert r.verdict.label is VerdictLabel.AUTHENTIC
    finally:
        shutdown_server(s)


def test_liar_relay_caught_by_behavior_and_errors(liar_relay):
    """usage 都伪造了，但错误码族 / logprobs / 行为风格仍是 Breeze 的。"""
    r = verify(liar_relay, "aqua-70b", AQUA_B, [BREEZE_B])
    assert r.verdict.label is VerdictLabel.MISMATCH
    assert r.verdict.runner_up == "breeze-8b"
    # token 层确实被骗过（这正是要证明"多层指纹必要性"的证据）
    token_ev = [e for e in r.verdict.evidences if e.signal == "token_count.prompt_curve"]
    assert token_ev and token_ev[0].margin > 0


def test_no_rivals_is_inconclusive(honest_aqua):
    """注册表里只有声称模型自己、没有竞争者时，margin 恒为 0——诚实返回不足。"""
    r = verify(honest_aqua, "aqua-70b", AQUA_B, [])
    assert r.verdict.label is VerdictLabel.INCONCLUSIVE
    assert r.verdict.runner_up is None
    assert any("竞争基线" in n for n in r.verdict.notes)


def test_budget_exhaustion_returns_partial_evidence(honest_aqua):
    r = verify(
        honest_aqua,
        "aqua-70b",
        AQUA_B,
        [BREEZE_B],
        max_requests=3,
    )
    assert r.skipped_probes  # 有探测被预算跳过
    assert r.verdict.label is VerdictLabel.INCONCLUSIVE  # tier-1 覆盖不足 → 诚实说不足
    assert r.verdict.notes


def test_seed_makes_runs_reproducible(honest_aqua):
    r1 = verify(honest_aqua, "aqua-70b", AQUA_B, [BREEZE_B], seed=123)
    r2 = verify(honest_aqua, "aqua-70b", AQUA_B, [BREEZE_B], seed=123)
    assert r1.transcript_sha256 == r2.transcript_sha256
    r3 = verify(honest_aqua, "aqua-70b", AQUA_B, [BREEZE_B], seed=456)
    # 不同 seed 允许不同（抽样文本不同），判决必须一致
    assert r3.verdict.label == r1.verdict.label
