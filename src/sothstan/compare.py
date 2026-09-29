"""混淆集似然比评分：本项目的方法论核心。

不做"与声称模型的距离"这种一元比较，而是把声称模型与基线注册表中
全部竞争模型放在同一证据下打分，取 margin = claimed - best rival：

- 每个信号按 kind 计分（见下），分数 ≤ 0，0 代表完美匹配；
- margin > 0：证据更支持"声称模型"；margin < 0：证据更支持某个竞争模型；
- 与其最像的竞争模型比较，是"验真"区别于"测距离"的关键——
  一个 deepseek-r1 冒充 deepseek-v3，两者彼此很像，但真正的 v3 基线
  应当在大多数信号上严格更优。

计分规则（工程先验，标定见 ROADMAP iter3 的对抗实验）：
- int_vector：逐元素，精确匹配 0 分；否则 -min(6, 2*log2(1+|o-e|/scale))，
  scale = max(1, 2%*|e|)（容忍模板微差；确定性端点上精确匹配占绝对主导）
- int：同上，scale = max(1, 5%*|e|)
- categorical：匹配 0；不匹配 -5（错误码族/风格类要么对要么错）
- bool：匹配 0；不匹配 -4
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sothstan.baseline import Baseline
from sothstan.types import Signal

_EPS = 1e-9


def _element_points(observed: float, expected: float, scale: float) -> float:
    if observed == expected:
        return 0.0
    diff = abs(observed - expected) / max(1.0, scale)
    return -min(6.0, 2.0 * math.log2(1.0 + diff))


def signal_points(observed: Signal, expected_value: object, expected_kind: str) -> float:
    """观测信号在"期望值为 expected_value"假设下的对数证据分（≤0，0 最佳）。"""
    if expected_kind != observed.kind:
        # 基线与观测类型不一致视为不匹配（记录层应避免出现）
        return -5.0
    if observed.kind in {"int_vector", "int"}:
        exp_list = list(expected_value) if observed.kind == "int_vector" else [expected_value]
        obs_list = list(observed.value) if observed.kind == "int_vector" else [observed.value]
        if len(exp_list) != len(obs_list):
            return -6.0
        total = 0.0
        for o, e in zip(obs_list, exp_list, strict=True):
            if not isinstance(o, (int, float)) or not isinstance(e, (int, float)):
                return -6.0
            rel = 0.02 if observed.kind == "int_vector" else 0.05
            total += _element_points(float(o), float(e), max(1.0, rel * abs(float(e))))
        return total
    if observed.kind in {"categorical", "bool"}:
        penalty = -5.0 if observed.kind == "categorical" else -4.0
        return 0.0 if observed.value == expected_value else penalty
    raise ValueError(f"未知信号类型: {observed.kind}")


@dataclass
class SignalEvidence:
    """一个信号在混淆集下的完整证据。"""

    probe: str
    signal: str
    kind: str
    weight: float
    observed: object
    claimed_value: object | None
    # 每个候选模型的分数（≤0）；claimed 也在其中
    candidate_points: dict[str, float] = field(default_factory=dict)
    note: str = ""

    claimed_model: str = ""

    @property
    def margin(self) -> float:
        """claimed 分数减去最强竞争者的分数，乘以权重。"""
        rivals = {m: p for m, p in self.candidate_points.items() if m != self.claimed_model}
        if not rivals:
            return 0.0
        best_rival = max(rivals.values())
        return self.weight * (self.candidate_points.get(self.claimed_model, -6.0) - best_rival)


def evaluate_signal(
    observed: Signal,
    claimed_model: str,
    claimed_baseline: Baseline,
    rivals: list[Baseline],
) -> SignalEvidence:
    """对一个观测信号，在 {claimed} ∪ rivals 全体候选下打分。"""
    spec = claimed_baseline.get_signal(observed.name)
    candidates: dict[str, object] = {}
    kinds: dict[str, str] = {}

    if spec is not None:
        candidates[claimed_model] = spec.value
        kinds[claimed_model] = spec.kind
    for r in rivals:
        rs = r.get_signal(observed.name)
        if rs is not None:
            candidates[r.model_id] = rs.value
            kinds[r.model_id] = rs.kind

    points = {
        model: signal_points(observed, value, kinds.get(model, observed.kind))
        for model, value in candidates.items()
    }
    note = ""
    if spec is None:
        note = "基线缺失该信号"
    return SignalEvidence(
        probe=observed.name.split(".", 1)[0],
        signal=observed.name,
        kind=observed.kind,
        weight=observed.weight,
        observed=observed.value,
        claimed_value=spec.value if spec is not None else None,
        candidate_points=points,
        claimed_model=claimed_model,
        note=note,
    )
