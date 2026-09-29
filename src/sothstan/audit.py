"""批量审计：一个 CSV 目标清单 → 受控并发验真 → 可发布的汇总报告。

CSV 格式（utf-8-sig，含表头）：name,base_url,model,key_env
- key_env 可为空（匿名请求）
- 同一 model 的多行共享注册表基线；混淆集 = 注册表中除该模型外的全部基线
  （与 `sothstan check` 同规则：demo 基线默认排除）

退出码约定（cmd_audit）：0=全部 AUTHENTIC；1=含 SUSPICIOUS；2=含 MISMATCH；
3=全部 INCONCLUSIVE/失败；4=基础设施错误（文件/表头/基线全缺）。
"""

from __future__ import annotations

import csv
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sothstan._version import __version__
from sothstan.baseline import Baseline, load_registry
from sothstan.report import HONESTY_APPENDIX, result_to_dict
from sothstan.runner import verify
from sothstan.verdict import VerdictLabel

REQUIRED_COLUMNS = {"name", "base_url", "model", "key_env"}


@dataclass
class AuditTarget:
    name: str
    base_url: str
    model: str
    key_env: str = ""


@dataclass
class AuditReport:
    rows: list[dict] = field(default_factory=list)
    created_at: str = ""
    seed: int = 0
    summary: dict = field(default_factory=dict)


def load_targets(path: str | Path) -> tuple[list[AuditTarget], list[str]]:
    """解析目标 CSV，返回 (targets, problems)。缺列/空行/缺值如实收集。"""
    problems: list[str] = []
    targets: list[AuditTarget] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            return [], [f"表头缺列：需要 {sorted(REQUIRED_COLUMNS)}，实际 {reader.fieldnames}"]
        for i, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            base_url = (row.get("base_url") or "").strip()
            model = (row.get("model") or "").strip()
            key_env = (row.get("key_env") or "").strip()
            if not name and not base_url and not model:
                continue  # 整行空白，跳过
            if not name or not base_url or not model:
                problems.append(f"第 {i} 行：name/base_url/model 均不能为空")
                continue
            targets.append(AuditTarget(name=name, base_url=base_url, model=model, key_env=key_env))
    if not targets and not problems:
        problems.append("清单为空：没有任何目标")
    return targets, problems


def _rivals_for(model: str, registry: dict[str, Baseline], include_demo: bool) -> list[Baseline]:
    return [
        b for mid, b in registry.items()
        if mid != model and (include_demo or not b.is_demo)
    ]


def audit_one(
    target: AuditTarget,
    registry: dict[str, Baseline],
    include_demo: bool,
    seed: int,
    timeout: float,
    retries: int,
    max_requests: int,
    max_prompt_tokens: int,
    adversarial: bool,
) -> dict:
    """验真单个目标，返回一行报告数据（不抛异常——失败也是一行）。"""
    row: dict = {
        "name": target.name,
        "base_url": target.base_url,
        "claimed_model": target.model,
        "error": None,
        "report": None,
    }
    baseline = registry.get(target.model)
    if baseline is None:
        row["error"] = f"注册表中没有 {target.model} 的基线"
        return row
    api_key = os.environ.get(target.key_env) if target.key_env else None
    result = verify(
        base_url=target.base_url,
        model=target.model,
        baseline=baseline,
        rivals=_rivals_for(target.model, registry, include_demo),
        api_key=api_key,
        seed=seed,
        timeout=timeout,
        retries=retries,
        max_requests=max_requests,
        max_prompt_tokens=max_prompt_tokens,
        options={"adversarial": True} if adversarial else None,
    )
    row["report"] = result_to_dict(result, target.base_url, target.model, seed)
    return row


def run_audit(
    targets: list[AuditTarget],
    registry_dir: str | Path | None = None,
    include_demo: bool = False,
    seed: int = 20260928,
    max_workers: int = 4,
    timeout: float = 30.0,
    retries: int = 2,
    max_requests: int = 64,
    max_prompt_tokens: int = 200_000,
    adversarial: bool = False,
) -> AuditReport:
    """受控并发跑批。注册表只加载一次，逐目标共享。"""
    registry = load_registry(registry_dir)
    report = AuditReport(
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        seed=seed,
    )
    if not registry:
        report.summary = {"error": "注册表为空：没有任何可用基线"}
        return report

    def _one(t: AuditTarget) -> dict:
        return audit_one(
            t, registry, include_demo, seed, timeout, retries,
            max_requests, max_prompt_tokens, adversarial,
        )

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        report.rows = list(pool.map(_one, targets))

    labels = [
        r["report"]["verdict"]["label"] for r in report.rows if r["report"] is not None
    ]
    report.summary = {
        "total": len(report.rows),
        "AUTHENTIC": labels.count(VerdictLabel.AUTHENTIC.value),
        "SUSPICIOUS": labels.count(VerdictLabel.SUSPICIOUS.value),
        "MISMATCH": labels.count(VerdictLabel.MISMATCH.value),
        "INCONCLUSIVE": labels.count(VerdictLabel.INCONCLUSIVE.value),
        "errors": sum(1 for r in report.rows if r["error"]),
        "registry_models": sorted(registry),
    }
    return report


def render_audit_markdown(report: AuditReport) -> str:
    """可发布的汇总报告：摘要表 + 声明。逐端点完整证据在 JSON。"""
    s = report.summary
    lines = [
        "# Sothstan批量审计报告",
        "",
        f"- 生成时间：{report.created_at}（sothstan {__version__}）",
        f"- seed：{report.seed}（同 seed 同探测集，证据链可复现）",
        f"- 目标：{s.get('total', 0)} 个｜"
        f"AUTHENTIC {s.get('AUTHENTIC', 0)}｜SUSPICIOUS {s.get('SUSPICIOUS', 0)}｜"
        f"MISMATCH {s.get('MISMATCH', 0)}｜INCONCLUSIVE {s.get('INCONCLUSIVE', 0)}｜"
        f"失败 {s.get('errors', 0)}",
        f"- 混淆集基线：{', '.join(s.get('registry_models', [])) or '（无）'}",
        "",
        "| 目标 | 声称模型 | 判决 | margin | 最强竞争解释 | 证据链 |",
        "|---|---|---|---|---|---|",
    ]
    for r in report.rows:
        rep = r["report"]
        if rep is None:
            lines.append(f"| {r['name']} | {r['claimed_model']} | 失败 | — | — | {r['error']} |")
            continue
        v = rep["verdict"]
        lines.append(
            f"| {r['name']} | {v['claimed_model']} | **{v['label']}** "
            f"| {v['margin_total']:+.1f} | {v['runner_up'] or '—'} "
            f"| `{rep['transcript_sha256'][:8]}…` |"
        )
    lines += [
        "",
        "> 逐端点完整信号证据表见同报告的 JSON（含每个信号的观测值/基线值/竞争者得分）。",
        "",
        HONESTY_APPENDIX,
        "",
    ]
    return "\n".join(lines)


def audit_exit_code(report: AuditReport) -> int:
    s = report.summary
    if s.get("MISMATCH"):
        return 2
    if s.get("SUSPICIOUS"):
        return 1
    if s.get("total") and s.get("AUTHENTIC"):
        return 0
    return 3  # 全部 INCONCLUSIVE/失败/空
