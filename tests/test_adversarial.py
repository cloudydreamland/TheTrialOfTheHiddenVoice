"""iter2 对抗性文本模式：生成器确定性 + 探测集成。"""

from __future__ import annotations

import json

import pytest

from sothstan.baseline import load_registry
from sothstan.cli import main
from sothstan.mockserver import AQUA, shutdown_server, start_server
from sothstan.probes.adversarial import generate_adversarial_texts
from sothstan.runner import collect_baseline_signals, verify
from sothstan.types import VerdictLabel

REGISTRY = load_registry()
BREEZE_B = REGISTRY["breeze-8b"]


def test_same_seed_same_texts():
    a = generate_adversarial_texts(42, 8)
    b = generate_adversarial_texts(42, 8)
    assert a == b


def test_different_seed_different_texts():
    a = generate_adversarial_texts(1, 8)
    b = generate_adversarial_texts(2, 8)
    assert [t for _, t in a] != [t for _, t in b]


def test_fuzz_determinism_30_seeds():
    for seed in range(30):
        assert generate_adversarial_texts(seed, 5) == generate_adversarial_texts(seed, 5)


def test_generated_text_properties():
    texts = generate_adversarial_texts(20260928, 12)
    assert len(texts) == 12
    ids = [i for i, _ in texts]
    assert len(set(ids)) == 12
    assert all(i.startswith("adv_20260928_") for i in ids)
    # 最大化分歧的类别都在：ZWJ 序列、组合字符、全角、罕见 CJK、长数字
    joined = " ".join(t for _, t in texts)
    assert "\u200d" in joined  # ZWJ
    assert "\u0301" in joined  # 组合字符
    assert any("Ａ" <= ch <= "ｚ" or "０" <= ch <= "９" for ch in joined)  # 全角
    assert any(ch in "饕龘彧犇" for ch in joined)  # 罕见 CJK（抽样池含这些）


def test_adversarial_roundtrip_is_authentic():
    """对抗模式采集 → 对抗模式验证 → AUTHENTIC（同 seed 可复现）。"""
    server, url = start_server(AQUA)
    try:
        baseline = collect_baseline_signals(
            url, "aqua-70b", "aqua", tags=["demo"], adversarial=True, seed=777
        )
        r = verify(url, "aqua-70b", baseline, [BREEZE_B],
                   options={"adversarial": True}, seed=777)
        assert r.verdict.label is VerdictLabel.AUTHENTIC
        spec = baseline.get_signal("token_count.prompt_curve")
        assert spec.meta["mode"] == "adversarial"
    finally:
        shutdown_server(server)


def test_mode_mismatch_warns():
    """canon 基线 + adversarial 运行 → 判决附模式不一致警示（诚实不沉默）。"""
    server, url = start_server(AQUA)
    try:
        baseline = collect_baseline_signals(url, "aqua-70b", "aqua", tags=["demo"])
        r = verify(url, "aqua-70b", baseline, [BREEZE_B], options={"adversarial": True})
        assert any("模式不一致" in n for n in r.verdict.notes)
    finally:
        shutdown_server(server)


def test_cli_adversarial_collect_check_roundtrip(tmp_path):
    path = tmp_path / "adv.json"
    server, url = start_server(AQUA)
    try:
        with pytest.raises(SystemExit) as e1:
            main(["collect", url, "--model", "aqua-70b", "--family", "aqua",
                  "--out", str(path), "--adversarial"])
        assert e1.value.code == 0
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["signals"]["token_count.prompt_curve"]["meta"]["mode"] == "adversarial"
        with pytest.raises(SystemExit) as e2:
            main(["check", url, "--model", "aqua-70b", "--baseline", str(path),
                  "--adversarial", "--include-demo"])  # demo breeze 作为混淆集竞争者
        assert e2.value.code == 0  # AUTHENTIC
    finally:
        shutdown_server(server)
