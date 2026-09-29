"""报告与 CLI。"""

from __future__ import annotations

import pytest

from sothstan.baseline import load_registry
from sothstan.cli import main
from sothstan.mockserver import AQUA, BREEZE, shutdown_server, start_server
from sothstan.report import HONESTY_APPENDIX, render_markdown, result_to_dict
from sothstan.runner import verify

REGISTRY = load_registry()
AQUA_B = REGISTRY["aqua-70b"]
BREEZE_B = REGISTRY["breeze-8b"]


def test_report_markdown_contains_verdict_and_honesty():
    server, url = start_server(BREEZE, claim="aqua-70b")
    try:
        r = verify(url, "aqua-70b", AQUA_B, [BREEZE_B])
    finally:
        shutdown_server(server)
    report = result_to_dict(r, url, "aqua-70b", 20260928)
    md = render_markdown(report)
    assert "MISMATCH" in md
    assert "诚实声明" in md
    assert "token_count.prompt_curve" in md
    # JSON 报告可序列化且带证据链
    assert len(report["transcript_sha256"]) == 64
    assert report["verdict"]["runner_up"] == "breeze-8b"


def test_honesty_appendix_is_auto():
    assert "统计证据" in HONESTY_APPENDIX


def test_cli_selftest_offline(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["selftest"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.count("PASS") >= 4
    assert "ALL PASS" in out


def test_cli_check_mismatch_exit_code(capsys):
    server, url = start_server(BREEZE, claim="aqua-70b")
    try:
        with pytest.raises(SystemExit) as exc:
            main(["check", url, "--model", "aqua-70b", "--include-demo"])
    finally:
        shutdown_server(server)
    assert exc.value.code == 2  # MISMATCH
    assert "breeze-8b" in capsys.readouterr().out


def test_cli_check_authentic_exit_code(capsys):
    server, url = start_server(AQUA)
    try:
        with pytest.raises(SystemExit) as exc:
            main(["check", url, "--model", "aqua-70b", "--include-demo"])
    finally:
        shutdown_server(server)
    assert exc.value.code == 0


def test_cli_check_missing_baseline_errors():
    server, url = start_server(AQUA)
    try:
        with pytest.raises(SystemExit) as exc:
            main(["check", url, "--model", "nonexistent-model"])
    finally:
        shutdown_server(server)
    assert exc.value.code == 4


def test_cli_collect_then_check_roundtrip(tmp_path, capsys):
    """collect 与 check 走的是同一条采集/判决管线（生产路径即测试路径）。"""
    baseline_path = tmp_path / "myaqua.json"
    server, url = start_server(AQUA)
    try:
        with pytest.raises(SystemExit) as exc:
            main([
                "collect", url, "--model", "aqua-70b", "--family", "aqua",
                "--out", str(baseline_path), "--honesty-note", "本地 aqua",
            ])
        assert exc.value.code == 0
        with pytest.raises(SystemExit) as exc2:
            main([
                "check", url, "--model", "aqua-70b",
                "--baseline", str(baseline_path),
                "--registry", str(tmp_path),  # 空注册表 → 无竞争者，需自带 rival
            ])
    finally:
        shutdown_server(server)
    assert exc2.value.code == 3  # 无竞争基线 → INCONCLUSIVE（混淆集不成立）
    data = baseline_path.read_text(encoding="utf-8")
    assert "aqua-70b" in data
