"""评分与判决：混淆集似然比的行为锁定。"""

from __future__ import annotations

from sothstan.baseline import Baseline, SignalSpec
from sothstan.compare import evaluate_signal, signal_points
from sothstan.types import Signal, VerdictLabel
from sothstan.verdict import decide


def _signal(name: str, kind: str, value: object, weight: float = 1.0) -> Signal:
    return Signal(name=name, kind=kind, value=value, weight=weight)


def _baseline(model_id: str, specs: dict[str, tuple[str, object]]) -> Baseline:
    return Baseline(
        model_id=model_id,
        family=model_id.split("-")[0],
        signals={
            name: SignalSpec(name=name, kind=kind, value=value)
            for name, (kind, value) in specs.items()
        },
    )


def test_exact_vector_scores_zero():
    pts = signal_points(
        _signal("s", "int_vector", [10, 20, 30]), [10, 20, 30], "int_vector"
    )
    assert pts == 0.0


def test_off_by_one_scores_small_negative():
    pts = signal_points(_signal("s", "int_vector", [10, 20, 31]), [10, 20, 30], "int_vector")
    assert -1.0 >= pts > -6.0


def test_way_off_scores_floor():
    """逐元素地板 -6，3 个元素全偏 → 总分 -18（地板按元素计，保证可解释性）。"""
    pts = signal_points(_signal("s", "int_vector", [99, 98, 97]), [10, 20, 30], "int_vector")
    assert pts == -18.0


def test_categorical_mismatch_is_minus_five():
    assert signal_points(_signal("s", "categorical", "a"), "a", "categorical") == 0.0
    assert signal_points(_signal("s", "categorical", "b"), "a", "categorical") == -5.0


def test_vector_length_mismatch_is_hard_penalty():
    assert signal_points(_signal("s", "int_vector", [1, 2]), [1, 2, 3], "int_vector") == -6.0


def test_evaluate_signal_margin_prefers_true_model():
    observed = _signal("token_count.prompt_curve", "int_vector", [20, 20, 20], weight=2.0)
    claimed = _baseline("true-model", {"token_count.prompt_curve": ("int_vector", [20, 20, 20])})
    rival = _baseline("fake-model", {"token_count.prompt_curve": ("int_vector", [48, 48, 48])})
    ev = evaluate_signal(observed, "true-model", claimed, [rival])
    assert ev.margin > 0
    assert ev.candidate_points["true-model"] == 0.0
    assert ev.candidate_points["fake-model"] < 0


def test_decide_authentic_requires_margin_and_exact_ratio():
    observed = _signal("p.sig", "int_vector", [20, 20, 20], weight=2.0)
    claimed = _baseline("true", {"p.sig": ("int_vector", [20, 20, 20])})
    rival = _baseline("rival", {"p.sig": ("int_vector", [48, 48, 48])})
    ev = evaluate_signal(observed, "true", claimed, [rival])
    tier1 = {"p.sig": True}
    v = decide([ev], "true", tier1)
    # 单信号覆盖 < 3 → INCONCLUSIVE（诚实不足）
    assert v.label is VerdictLabel.INCONCLUSIVE


def test_decide_mismatch_when_rival_explains_better():
    observed = _signal("token_count.prompt_curve", "int_vector", [48, 48, 48], weight=2.0)
    claimed = _baseline("claimed", {"token_count.prompt_curve": ("int_vector", [20, 20, 20])})
    rival = _baseline("actual", {"token_count.prompt_curve": ("int_vector", [48, 48, 48])})
    evs = [
        evaluate_signal(observed, "claimed", claimed, [rival]),
        evaluate_signal(
            _signal("t.s2", "categorical", "rival_family"), "claimed", claimed, [rival]
        ),
        evaluate_signal(_signal("t.s3", "categorical", "x"), "claimed", claimed, [rival]),
        evaluate_signal(_signal("t.s4", "categorical", "y"), "claimed", claimed, [rival]),
    ]
    tier1 = {
        "token_count.prompt_curve": True,
        "t.s2": True,
        "t.s3": True,
        "t.s4": True,
    }
    v = decide(evs, "claimed", tier1)
    assert v.label is VerdictLabel.MISMATCH
    assert v.runner_up == "actual"


def test_missing_baseline_signals_do_not_crash():
    observed = _signal("p.new_signal", "categorical", "whatever")
    claimed = _baseline("m", {"p.old": ("categorical", "x")})
    ev = evaluate_signal(observed, "m", claimed, [])
    assert ev.note == "基线缺失该信号"
    assert ev.margin == 0.0
