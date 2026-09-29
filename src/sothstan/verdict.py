"""判决：把全部信号证据聚合成一个可解释的结论。

规则（阈值是公开常量，可被测试锁定、被评审挑战）：
- 覆盖率门槛：tier-1 信号至少 MIN_TIER1_COVERED 个有效（观测与基线都在），
  否则 INCONCLUSIVE——证据不足时诚实说不足，绝不硬给结论。
- margin_total = claimed 总分 − 最强竞争者总分（同一混淆集下逐信号累加）。
- margin ≥ AUTH_MIN_MARGIN 且 claimed 精确匹配率 ≥ MIN_EXACT_RATIO → AUTHENTIC
- margin ≤ MISMATCH_MARGIN → MISMATCH（runner_up 即最像的替代模型）
- 其余 → SUSPICIOUS（claimed "最不差"但对不上，或内部矛盾）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sothstan.compare import SignalEvidence
from sothstan.types import VerdictLabel

AUTH_MIN_MARGIN = 8.0
MISMATCH_MARGIN = -8.0
MIN_TIER1_COVERED = 3
MIN_EXACT_RATIO = 0.6
# claimed 总分硬地板：声称模型与自己基线的相符度深于此时，无论竞争者是谁，
# 都已证明"端点行为不是声称模型"——margin 再高也不能判 AUTHENTIC。
# 动机（对抗实验 iter0#1）：完美说谎中转伪造 usage 后，token 层的巨大分差
# 会在总分里"淹没"行为层的全面矛盾，单纯 margin 规则会漏判。
# -12 → -10（iter3 对抗实验校准）：naive 全套伪造恰好 -11 分滑过 -12 地板逃逸；
# 诚实服务器 claimed 总分恒为 0，收紧到 -10 无误判代价（见 benchmarks/evasion_matrix.md）。
MISMATCH_TOTAL_FLOOR = -10.0

THRESHOLDS_DOC = {
    "AUTH_MIN_MARGIN": AUTH_MIN_MARGIN,
    "MISMATCH_MARGIN": MISMATCH_MARGIN,
    "MIN_TIER1_COVERED": MIN_TIER1_COVERED,
    "MIN_EXACT_RATIO": MIN_EXACT_RATIO,
    "MISMATCH_TOTAL_FLOOR": MISMATCH_TOTAL_FLOOR,
}


@dataclass
class Verdict:
    label: VerdictLabel
    claimed_model: str
    runner_up: str | None = None
    margin_total: float = 0.0
    claimed_total: float = 0.0
    rival_totals: dict[str, float] = field(default_factory=dict)
    covered: int = 0
    tier1_covered: int = 0
    exact_matches: int = 0
    missing_baseline: list[str] = field(default_factory=list)
    missing_observed: list[str] = field(default_factory=list)
    evidences: list[SignalEvidence] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label.value,
            "claimed_model": self.claimed_model,
            "runner_up": self.runner_up,
            "margin_total": round(self.margin_total, 2),
            "claimed_total": round(self.claimed_total, 2),
            "rival_totals": {k: round(v, 2) for k, v in sorted(self.rival_totals.items())},
            "covered": self.covered,
            "tier1_covered": self.tier1_covered,
            "exact_matches": self.exact_matches,
            "missing_baseline": self.missing_baseline,
            "missing_observed": self.missing_observed,
            "notes": self.notes,
            "thresholds": THRESHOLDS_DOC,
        }


def _is_exact(ev: SignalEvidence) -> bool:
    return ev.candidate_points.get(ev.claimed_model, -1.0) == 0.0


def decide(
    evidences: list[SignalEvidence],
    claimed_model: str,
    tier1_names_present: dict[str, bool],
    notes: list[str] | None = None,
) -> Verdict:
    """tier1_names_present: 探测计划中每个 tier-1 信号名 → 是否有效观测到。"""
    notes = notes or []
    rival_totals: dict[str, float] = {}
    claimed_total = 0.0
    covered = 0
    exact = 0
    missing_baseline: list[str] = []
    missing_observed: list[str] = []

    tier1_covered = sum(1 for ok in tier1_names_present.values() if ok)

    for ev in evidences:
        if not ev.candidate_points:
            if ev.note == "基线缺失该信号":
                missing_baseline.append(ev.signal)
            else:
                missing_observed.append(ev.signal)
            continue
        covered += 1
        pts = ev.candidate_points.get(claimed_model, -6.0)
        claimed_total += ev.weight * pts
        if _is_exact(ev):
            exact += 1
        for model, p in ev.candidate_points.items():
            if model != claimed_model:
                rival_totals[model] = rival_totals.get(model, 0.0) + ev.weight * p

    runner_up = max(rival_totals, key=rival_totals.get) if rival_totals else None
    best_rival_total = rival_totals[runner_up] if runner_up else 0.0
    margin = claimed_total - best_rival_total

    label = VerdictLabel.SUSPICIOUS
    n_observed_signals = len([e for e in evidences if e.note != "基线缺失该信号"])
    if tier1_covered < MIN_TIER1_COVERED and n_observed_signals > 0:
        label = VerdictLabel.INCONCLUSIVE
        notes.append(
            f"tier-1 有效信号 {tier1_covered} < {MIN_TIER1_COVERED}，证据不足"
        )
    elif covered == 0:
        label = VerdictLabel.INCONCLUSIVE
        notes.append("没有任何可比对的信号（基线与观测完全不重叠？）")
    elif not rival_totals:
        label = VerdictLabel.INCONCLUSIVE
        notes.append(
            "注册表中没有竞争基线（rivals），无法构成混淆集比较——"
            "请至少再采集 1 个可作为替代品的官方模型基线"
        )
    elif claimed_total <= MISMATCH_TOTAL_FLOOR:
        label = VerdictLabel.MISMATCH
        notes.append(
            f"claimed 总分 {claimed_total:.1f} 低于硬地板 {MISMATCH_TOTAL_FLOOR}："
            "端点行为与声称模型的基线深度不符"
        )
    elif margin >= AUTH_MIN_MARGIN and covered > 0 and exact / covered >= MIN_EXACT_RATIO:
        label = VerdictLabel.AUTHENTIC
    elif margin <= MISMATCH_MARGIN:
        label = VerdictLabel.MISMATCH
    return Verdict(
        label=label,
        claimed_model=claimed_model,
        runner_up=runner_up,
        margin_total=margin,
        claimed_total=claimed_total,
        rival_totals=rival_totals,
        covered=covered,
        tier1_covered=tier1_covered,
        exact_matches=exact,
        missing_baseline=missing_baseline,
        missing_observed=missing_observed,
        evidences=evidences,
        notes=notes,
    )
