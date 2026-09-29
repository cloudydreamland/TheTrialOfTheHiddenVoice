"""iter1 评审修复的回归测试：重试、瞬时错误隔离、探测子集、schema 校验。"""

from __future__ import annotations

import pytest

from sothstan.baseline import load_registry, validate_baseline_dict
from sothstan.http import ApiClient, ApiError
from sothstan.mockserver import AQUA, FlakyServer, shutdown_server
from sothstan.runner import verify
from sothstan.types import VerdictLabel

REGISTRY = load_registry()
AQUA_B = REGISTRY["aqua-70b"]
BREEZE_B = REGISTRY["breeze-8b"]


@pytest.fixture()
def flaky_aqua():
    server = FlakyServer(AQUA, fail_times=2)
    thread_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    import threading

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield server, thread_url
    shutdown_server(server)


def test_client_retries_transient_then_succeeds(flaky_aqua):
    """前 2 次 429，retries=2 → 第 3 次成功。"""
    server, url = flaky_aqua
    client = ApiClient(base_url=url, retries=2, retry_backoff=0.01)
    resp = client.chat([{"role": "user", "content": "hi"}], "aqua-70b", max_tokens=1)
    assert resp.prompt_tokens is not None
    assert client.requests_used == 3  # 两次失败 + 一次成功，全部进转录
    assert len(client.transcript) == 3


def test_client_no_retry_raises_immediately(flaky_aqua):
    server, url = flaky_aqua
    client = ApiClient(base_url=url, retries=0)
    with pytest.raises(ApiError) as exc:
        client.chat([{"role": "user", "content": "hi"}], "aqua-70b", max_tokens=1)
    assert exc.value.transient is True
    assert exc.value.status == 429


def test_errors_probe_marks_persistent_transient_as_transient():
    """限流不因重试恢复时，错误码族必须记 'transient' 而非伪指纹。"""
    import random

    from sothstan.probes.base import ProbeContext
    from sothstan.probes.errors import ErrorFamilyProbe

    server = FlakyServer(AQUA, fail_times=10**9)  # 永远限流
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        client = ApiClient(base_url=url, retries=1, retry_backoff=0.01)
        outcome = ErrorFamilyProbe(ProbeContext(client, "aqua-70b", random.Random(1))).run()
        families = {s.name: s.value for s in outcome.signals}
        assert all(v == "transient" for v in families.values())
        assert outcome.notes  # 如实记录瞬时错误
    finally:
        shutdown_server(server)


def test_verify_with_probe_subset_is_inconclusive():
    """--probes reasoning（tier-2）子集 → tier-1 覆盖 = 0 < 3 → 诚实 INCONCLUSIVE。"""
    server = FlakyServer(AQUA, fail_times=0)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        r = verify(url, "aqua-70b", AQUA_B, [BREEZE_B], probe_names=["reasoning"])
        assert r.verdict.label is VerdictLabel.INCONCLUSIVE
        assert r.verdict.tier1_covered == 0
    finally:
        shutdown_server(server)


def test_verify_errors_only_full_match_is_authentic():
    """iter1 评审发现（行为锁定）：errors 单探测器 4 个 tier-1 信号全部精确命中时
    判 AUTHENTIC 是当前公开阈值的合法输出——该宽松度是否该收紧交 iter3 对抗实验定夺。"""
    server = FlakyServer(AQUA, fail_times=0)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        r = verify(url, "aqua-70b", AQUA_B, [BREEZE_B], probe_names=["errors"])
        assert r.verdict.label is VerdictLabel.AUTHENTIC
        assert r.verdict.exact_matches == r.verdict.covered
    finally:
        shutdown_server(server)


def test_baseline_weight_must_be_numeric():
    bad = {
        "schema_version": 1,
        "model_id": "m",
        "family": "f",
        "signals": {"x": {"kind": "int", "value": 3, "weight": "heavy"}},
    }
    assert any("weight" in p for p in validate_baseline_dict(bad))


def test_report_contains_exit_code():
    server = FlakyServer(AQUA, fail_times=0)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        from sothstan.report import result_to_dict
        from sothstan.runner import verify as _verify

        r = _verify(url, "aqua-70b", AQUA_B, [BREEZE_B])
        report = result_to_dict(r, url, "aqua-70b", 1)
        assert report["exit_code"] == r.exit_code
    finally:
        shutdown_server(server)


def test_cli_version_flag(capsys):
    from sothstan.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "sothstan" in capsys.readouterr().out
