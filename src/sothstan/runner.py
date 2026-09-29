"""运行器：编排探测计划 → 观测 → 混淆集评分 → 判决。

预算优先：任何一步 BudgetExceeded 都会让剩余探测如实标记为 skipped，
而不是让整个运行崩掉——生产环境里"带着部分证据诚实返回"比"抛异常"有用。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sothstan._version import __version__
from sothstan.baseline import Baseline, SignalSpec, save_baseline
from sothstan.compare import SignalEvidence, evaluate_signal
from sothstan.http import ApiClient, BudgetExceeded, Transcript
from sothstan.probes import ALL_PROBES, TIER_OF
from sothstan.probes.base import ProbeContext
from sothstan.types import ProbeOutcome
from sothstan.verdict import Verdict, decide

EXIT_CODES = {
    "AUTHENTIC": 0,
    "SUSPICIOUS": 1,
    "MISMATCH": 2,
    "INCONCLUSIVE": 3,
    "ERROR": 4,
}


@dataclass
class VerificationResult:
    verdict: Verdict
    transcript_sha256: str
    outcomes: list[ProbeOutcome] = field(default_factory=list)
    requests_used: int = 0
    prompt_tokens_used: int = 0
    skipped_probes: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict.label.value]


def _all_tier1_signal_names(baselines: list[Baseline]) -> dict[str, bool]:
    """tier-1 信号全集：来自基线注册表中已知信号名。"""
    names: set[str] = set()
    for b in baselines:
        for name in b.signals:
            probe = name.split(".", 1)[0]
            if TIER_OF.get(probe) == 1:
                names.add(name)
    return {n: False for n in sorted(names)}


def run_probes(
    client: ApiClient,
    model: str,
    seed: int = 20260928,
    probe_names: list[str] | None = None,
    options: dict | None = None,
) -> tuple[list[ProbeOutcome], list[str]]:
    """执行探测计划，返回 (outcomes, skipped_probes)。"""
    ctx = ProbeContext(client=client, model=model, rng=random.Random(seed), options=options or {})
    plan = [p for p in ALL_PROBES if probe_names is None or p.name in probe_names]
    outcomes: list[ProbeOutcome] = []
    skipped: list[str] = []
    for probe_cls in plan:
        try:
            outcomes.append(probe_cls(ctx).run())
        except BudgetExceeded:
            already = {o.probe for o in outcomes}
            skipped.append(probe_cls.name)
            skipped.extend(
                p.name for p in plan if p.name not in already and p.name != probe_cls.name
            )
            break
        except Exception as exc:  # 探测器自身崩溃不拖垮整体，如实记录
            outcomes.append(
                ProbeOutcome(
                    probe=probe_cls.name,
                    ok=False,
                    notes=[f"探测器异常: {type(exc).__name__}: {exc}"],
                )
            )
    return outcomes, skipped


def collect_evidence(
    outcomes: list[ProbeOutcome],
    claimed_model: str,
    claimed_baseline: Baseline,
    rivals: list[Baseline],
) -> list[SignalEvidence]:
    evidences: list[SignalEvidence] = []
    for outcome in outcomes:
        for sig in outcome.signals:
            if sig.weight <= 0.0:
                continue  # 零权重信号（如 model 字段回显）只展示不计分
            evidences.append(evaluate_signal(sig, claimed_model, claimed_baseline, rivals))
    return evidences


def _tier1_observed_map(outcomes: list[ProbeOutcome], registry: dict[str, bool]) -> dict[str, bool]:
    observed: dict[str, bool] = dict(registry)
    for outcome in outcomes:
        for sig in outcome.signals:
            if sig.name in observed and sig.weight > 0.0:
                observed[sig.name] = True
    return observed


def verify(
    base_url: str,
    model: str,
    baseline: Baseline,
    rivals: list[Baseline],
    api_key: str | None = None,
    seed: int = 20260928,
    probe_names: list[str] | None = None,
    max_requests: int = 64,
    max_prompt_tokens: int = 200_000,
    options: dict | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> VerificationResult:
    """对目标端点做完整验真。

    对抗模式（options={"adversarial": True}）：token 探测使用按 seed 生成的
    对抗文本。基线必须以同模式采集；模式不一致时判决附诚实警示（token 曲线不可比）。
    """
    options = dict(options or {})
    options.setdefault("seed", seed)
    transcript = Transcript()
    client = ApiClient(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        transcript=transcript,
        max_requests=max_requests,
        max_prompt_tokens=max_prompt_tokens,
        retries=retries,
    )
    outcomes, skipped = run_probes(
        client, model, seed=seed, probe_names=probe_names, options=options
    )
    evidences = collect_evidence(outcomes, model, baseline, rivals)
    tier1_map = _tier1_observed_map(outcomes, _all_tier1_signal_names([baseline, *rivals]))
    notes: list[str] = []
    mode_warning = _mode_mismatch_note(baseline, options)
    if mode_warning:
        notes.append(mode_warning)
    verdict = decide(evidences, model, tier1_map, notes=notes)
    return VerificationResult(
        verdict=verdict,
        transcript_sha256=transcript.sha256(),
        outcomes=outcomes,
        requests_used=client.requests_used,
        prompt_tokens_used=client.prompt_tokens_used,
        skipped_probes=skipped,
    )


def _mode_mismatch_note(baseline: Baseline, options: dict) -> str:
    """基线与本次运行的探测模式不一致时给出诚实警示（不阻断判决）。"""
    spec = baseline.get_signal("token_count.prompt_curve")
    baseline_mode = (spec.meta or {}).get("mode", "canon") if spec else None
    run_mode = "adversarial" if options.get("adversarial") else "canon"
    if baseline_mode is not None and baseline_mode != run_mode:
        return (
            f"模式不一致：基线采集于 {baseline_mode} 模式，本次运行为 {run_mode} 模式"
            "——token 曲线不可比，本判决仅供警示，请以同模式重采基线"
        )
    return ""


def collect_baseline_signals(
    base_url: str,
    model: str,
    family: str,
    api_key: str | None = None,
    seed: int = 20260928,
    endpoint_hint: str = "",
    tags: list[str] | None = None,
    honesty_note: str = "",
    probe_names: list[str] | None = None,
    adversarial: bool = False,
) -> Baseline:
    """对（官方）端点采集完整指纹，产出 Baseline。"""
    client = ApiClient(base_url=base_url, api_key=api_key)
    options = {"adversarial": True} if adversarial else None
    if options is not None:
        options.setdefault("seed", seed)  # 与 verify 相同的 seed 注入，保证同 seed 同题
    outcomes, skipped = run_probes(
        client, model, seed=seed, probe_names=probe_names, options=options
    )
    signals = {}
    for outcome in outcomes:
        for sig in outcome.signals:
            signals[sig.name] = {
                "kind": sig.kind,
                "value": sig.value,
                "weight": sig.weight,
                "meta": sig.meta,
            }
    if not signals:
        raise RuntimeError(f"采集失败：未获得任何信号。跳过: {skipped or '无'}")
    if skipped:
        honesty_note = (honesty_note + f" | 采集时跳过的探测: {','.join(skipped)}").strip(" |")
    return Baseline(
        model_id=model,
        family=family,
        signals={
            name: SignalSpec(
                name=name,
                kind=spec["kind"],
                value=spec["value"],
                weight=float(spec["weight"]),
                meta=spec.get("meta", {}),
            )
            for name, spec in signals.items()
        },
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        collector=f"sothstan {__version__}",
        endpoint_hint=endpoint_hint,
        tags=tags or [],
        honesty_note=honesty_note,
    )


def collect_and_save(
    base_url: str,
    model: str,
    family: str,
    out_path: str | Path,
    api_key: str | None = None,
    seed: int = 20260928,
    tags: list[str] | None = None,
    honesty_note: str = "",
    adversarial: bool = False,
) -> Path:
    baseline = collect_baseline_signals(
        base_url,
        model,
        family,
        api_key=api_key,
        seed=seed,
        tags=tags,
        honesty_note=honesty_note,
        adversarial=adversarial,
    )
    return save_baseline(baseline, out_path)
