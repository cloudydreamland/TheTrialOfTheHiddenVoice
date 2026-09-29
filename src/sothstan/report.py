"""报告渲染：JSON 与 Markdown，带自动附加的诚实声明。"""

from __future__ import annotations

from sothstan.runner import VerificationResult

HONESTY_APPENDIX = (
    "## 诚实声明\n\n"
    "- 指纹验证给出的是**统计证据**，不是数学证明。高置信 AUTHENTIC 也可能被\n"
    "  足够狡猾的转发代理欺骗；MISMATCH 则意味着存在比声称模型显著更优的解释。\n"
    "- **本工具输出是技术评估，不构成对任何服务提供方的法律指控**；公开点名\n"
    "  请遵循 docs/audit_methodology.md 的证据与回应流程。\n"
    "- 基线必须来自**官方端点**采集（`sothstan collect`）；使用来路不明的基线会让\n"
    "  整个判决失去意义。\n"
    "- 响应体 `model` 字段回显是零权重展示项：改字段是最廉价的伪造，不参与计分。\n"
    "- 权重与阈值是公开的工程先验（见 `verdict.THRESHOLDS_DOC`），欢迎用对抗实验挑战。"
)


def _fmt_value(value: object, limit: int = 8) -> str:
    if isinstance(value, list):
        head = ", ".join(str(v) for v in value[:limit])
        return f"[{head}{' …' if len(value) > limit else ''}] ({len(value)}项)"
    return str(value)


def result_to_dict(result: VerificationResult, base_url: str, model: str, seed: int) -> dict:
    v = result.verdict
    return {
        "verdict": v.to_dict(),
        "target": {"base_url": base_url, "claimed_model": model, "seed": seed},
        "exit_code": result.exit_code,
        "evidence": [
            {
                "signal": ev.signal,
                "kind": ev.kind,
                "weight": ev.weight,
                "observed": ev.observed,
                "claimed_value": ev.claimed_value,
                "candidate_points": {k: round(p, 2) for k, p in ev.candidate_points.items()},
                "margin": round(ev.margin, 2),
                "note": ev.note,
            }
            for ev in v.evidences
        ],
        "probe_notes": {o.probe: o.notes for o in result.outcomes if o.notes},
        "skipped_probes": result.skipped_probes,
        "budget": {
            "requests_used": result.requests_used,
            "prompt_tokens_used": result.prompt_tokens_used,
        },
        "transcript_sha256": result.transcript_sha256,
        "honesty": "指纹验证是统计证据，非数学证明；基线必须来自官方端点。",
    }


def render_markdown(report: dict) -> str:
    v = report["verdict"]
    lines: list[str] = []
    icon = {"AUTHENTIC": "✅", "SUSPICIOUS": "⚠️", "MISMATCH": "❌", "INCONCLUSIVE": "❓"}[
        v["label"]
    ]
    lines.append(f"# Sothstan验真报告 {icon} {v['label']}")
    lines.append("")
    lines.append(f"- 目标端点：`{report['target']['base_url']}`")
    lines.append(f"- 声称模型：`{v['claimed_model']}`")
    lines.append(f"- 判决：**{v['label']}**（margin {v['margin_total']:+.1f}）")
    if v["runner_up"]:
        lines.append(
            f"- 最强竞争解释：`{v['runner_up']}`"
            f"（总分 {v['rival_totals'].get(v['runner_up'], 0.0):+.1f}）"
        )
    lines.append(
        f"- 覆盖：{v['covered']} 个信号（tier-1 有效 {v['tier1_covered']}，"
        f"精确匹配 {v['exact_matches']}）"
    )
    lines.append(f"- 证据链哈希：`{report['transcript_sha256'][:16]}…`")
    lines.append("")
    lines.append("## 信号证据")
    lines.append("")
    lines.append("| 信号 | 观测值 | 声称模型基线 | margin |")
    lines.append("|---|---|---|---|")
    for ev in report["evidence"]:
        lines.append(
            f"| `{ev['signal']}` | {_fmt_value(ev['observed'])} "
            f"| {_fmt_value(ev['claimed_value'])} | {ev['margin']:+.1f} |"
        )
    if v["missing_baseline"]:
        lines.append("")
        lines.append(f"基线缺失信号：{', '.join(v['missing_baseline'])}")
    if report["skipped_probes"]:
        lines.append("")
        lines.append(f"预算内跳过的探测：{', '.join(report['skipped_probes'])}")
    notes = [n for ns in report["probe_notes"].values() for n in ns]
    if v["notes"] or notes:
        lines.append("")
        lines.append("## 备注")
        lines.extend(f"- {n}" for n in (v["notes"] + notes))
    lines.append("")
    lines.append(HONESTY_APPENDIX)
    lines.append("")
    return "\n".join(lines)
