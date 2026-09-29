"""LimitsProbe：参数限额与能力开关指纹。

max_tokens 上限的处理方式、logprobs / n 参数是否支持、响应体 model 字段回显——
组合起来构成端点服务端实现的指纹（换成别的模型/别的服务端实现，这些行为跟着变）。

信号：
- limits.max_tokens_huge    categorical  weight 1.0   （"accepted" 或错误码族）
- limits.logprobs_support   bool         weight 1.0
- limits.n_param_support    bool         weight 1.0
- limits.model_field_echo   categorical  weight 0.0   （仅展示，不计分：最易伪造）
"""

from __future__ import annotations

from sothstan.http import ApiError
from sothstan.probes.base import Probe
from sothstan.probes.canon import CANON_BY_ID
from sothstan.types import ProbeOutcome, Signal


class LimitsProbe(Probe):
    name = "limits"
    tier = 1

    def run(self) -> ProbeOutcome:
        text = CANON_BY_ID["zh_short_1"]
        signals: list[Signal] = []
        notes: list[str] = []
        model_field: str | None = None

        # 1) 巨型 max_tokens：不同服务端是收下、钳制还是报错，报错文案各不相同
        try:
            resp = self.ctx.client.chat(
                self._user(text), self.ctx.model, max_tokens=10**9, temperature=0
            )
            family = "accepted"
            model_field = resp.model_field
        except ApiError as exc:
            family = "transient" if exc.transient else exc.family
            if exc.transient:
                notes.append(f"max_tokens_huge: 端点持续返回瞬时错误（{exc.status}）")
        except Exception as exc:
            family = f"client|{type(exc).__name__}"
            notes.append(f"max_tokens_huge: {type(exc).__name__}")
        signals.append(Signal("limits.max_tokens_huge", "categorical", family, 1.0))

        # 2) logprobs 支持
        try:
            resp = self.ctx.client.chat(
                self._user(text),
                self.ctx.model,
                max_tokens=8,
                temperature=0,
                extra={"logprobs": True, "top_logprobs": 3},
            )
            signals.append(Signal("limits.logprobs_support", "bool", resp.logprobs_present, 1.0))
            model_field = model_field or resp.model_field
        except Exception as exc:
            signals.append(Signal("limits.logprobs_support", "bool", False, 1.0))
            notes.append(f"logprobs: {type(exc).__name__}")

        # 3) n 参数支持
        try:
            self.ctx.client.chat(self._user(text), self.ctx.model, max_tokens=4, extra={"n": 2})
            signals.append(Signal("limits.n_param_support", "bool", True, 1.0))
        except Exception as exc:
            signals.append(Signal("limits.n_param_support", "bool", False, 1.0))
            notes.append(f"n_param: {type(exc).__name__}")

        # 4) model 字段回显——零权重，纯展示（证明"改字段"骗不过指纹）
        signals.append(
            Signal("limits.model_field_echo", "categorical", model_field or "unknown", 0.0)
        )
        return ProbeOutcome(probe=self.name, ok=True, signals=signals, notes=notes)
