"""基线：官方模型指纹的版本化存储。

一个 Baseline = 一个官方模型在某一时刻的完整指纹快照。
注册表（registry 目录）里的全部基线互为"混淆集"候选。

诚实边界：基线必须用 `sothstan collect` 对**官方端点**采集；
仓库内置的 `_demo_*.json` 描述的是本库自带 mock 人格，仅用于离线
测试与 selftest，绝不可当作任何真实模型的指纹使用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sothstan.types import SIGNAL_KINDS

SCHEMA_VERSION = 1
PACKAGE_REGISTRY = Path(__file__).parent / "baselines"


@dataclass
class SignalSpec:
    name: str
    kind: str
    value: object
    weight: float = 1.0
    meta: dict = field(default_factory=dict)


@dataclass
class Baseline:
    model_id: str
    family: str
    signals: dict[str, SignalSpec]
    collected_at: str = ""
    collector: str = ""
    endpoint_hint: str = ""
    tags: list[str] = field(default_factory=list)
    honesty_note: str = ""

    def get_signal(self, name: str) -> SignalSpec | None:
        return self.signals.get(name)

    @property
    def is_demo(self) -> bool:
        return "demo" in self.tags

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "model_id": self.model_id,
            "family": self.family,
            "tags": self.tags,
            "collected_at": self.collected_at,
            "collector": self.collector,
            "endpoint_hint": self.endpoint_hint,
            "honesty_note": self.honesty_note,
            "signals": {
                name: {
                    "kind": s.kind,
                    "value": s.value,
                    "weight": s.weight,
                    "meta": s.meta,
                }
                for name, s in sorted(self.signals.items())
            },
        }


def validate_baseline_dict(data: dict) -> list[str]:
    """返回问题列表；空列表 = 合法。"""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"]
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version 必须为 {SCHEMA_VERSION}")
    if not data.get("model_id") or not isinstance(data.get("model_id"), str):
        problems.append("model_id 缺失或非字符串")
    if not isinstance(data.get("family"), str) or not data.get("family"):
        problems.append("family 缺失")
    signals = data.get("signals")
    if not isinstance(signals, dict) or not signals:
        problems.append("signals 必须为非空对象")
        return problems
    for name, spec in signals.items():
        if not isinstance(spec, dict):
            problems.append(f"{name}: 必须为对象")
            continue
        weight = spec.get("weight", 1.0)
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            problems.append(f"{name}: weight 必须为数值")
        kind = spec.get("kind")
        if kind not in SIGNAL_KINDS:
            problems.append(f"{name}: 非法 kind {kind!r}")
            continue
        value = spec.get("value")
        if kind == "int_vector" and not (isinstance(value, list) and value):
            problems.append(f"{name}: int_vector 需要非空数组")
        if kind == "int" and not isinstance(value, int):
            problems.append(f"{name}: int 需要整数")
        if kind == "categorical" and not isinstance(value, str):
            problems.append(f"{name}: categorical 需要字符串")
        if kind == "bool" and not isinstance(value, bool):
            problems.append(f"{name}: bool 需要布尔值")
    return problems


def baseline_from_dict(data: dict) -> Baseline:
    problems = validate_baseline_dict(data)
    if problems:
        raise ValueError("基线不合法: " + "; ".join(problems))
    signals = {
        name: SignalSpec(
            name=name,
            kind=spec["kind"],
            value=spec["value"],
            weight=float(spec.get("weight", 1.0)),
            meta=spec.get("meta", {}),
        )
        for name, spec in data["signals"].items()
    }
    return Baseline(
        model_id=data["model_id"],
        family=data["family"],
        signals=signals,
        collected_at=data.get("collected_at", ""),
        collector=data.get("collector", ""),
        endpoint_hint=data.get("endpoint_hint", ""),
        tags=list(data.get("tags", [])),
        honesty_note=data.get("honesty_note", ""),
    )


def load_baseline(path: str | Path) -> Baseline:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return baseline_from_dict(data)


def save_baseline(baseline: Baseline, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(baseline.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return p


def load_registry(directory: str | Path | None = None) -> dict[str, Baseline]:
    """加载目录下全部 *.json 基线，按 model_id 索引。坏文件如实跳过并收集错误。"""
    out: dict[str, Baseline] = {}
    errors: list[str] = []
    d = Path(directory) if directory is not None else PACKAGE_REGISTRY
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            b = baseline_from_dict(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{f.name}: {exc}")
            continue
        out[b.model_id] = b
    return out
