"""ErrorFamilyProbe：错误处理路径指纹。

非法参数如何被拒绝（状态码、错误体结构、文案）由服务端实现决定，
是换不掉的深层指纹——中转可以转发请求，但替代模型的错误风格会漏出来。

信号（全部 categorical，weight 1.0）：
- errors.temperature_out_of_range
- errors.unknown_param
- errors.empty_messages
- errors.invalid_role
"""

from __future__ import annotations

from sothstan.http import ApiError
from sothstan.probes.base import Probe
from sothstan.types import ProbeOutcome, Signal

_CASES: list[tuple[str, list[dict], dict]] = [
    ("temperature_out_of_range", [{"role": "user", "content": "hi"}], {"temperature": 42}),
    ("unknown_param", [{"role": "user", "content": "hi"}], {"sothstan_probe_unknown": 1}),
    ("empty_messages", [], {}),
    ("invalid_role", [{"role": "robot", "content": "hi"}], {}),
]


class ErrorFamilyProbe(Probe):
    name = "errors"
    tier = 1

    def run(self) -> ProbeOutcome:
        signals: list[Signal] = []
        notes: list[str] = []
        for label, messages, extra in _CASES:
            try:
                resp = self.ctx.client.chat(messages, self.ctx.model, max_tokens=1, extra=extra)
                family = f"accepted|finish={resp.finish_reason}"
            except ApiError as exc:
                # 瞬时错误（限流/5xx）已由客户端重试；仍失败说明端点此刻不可用，
                # 记 "transient" 固定类别——它不区分模型，不能冒充指纹。
                family = "transient" if exc.transient else exc.family
                if exc.transient:
                    notes.append(f"{label}: 端点持续返回瞬时错误（{exc.status}）")
            except Exception as exc:
                family = f"client|{type(exc).__name__}"
                notes.append(f"{label}: {type(exc).__name__}")
            signals.append(Signal(f"errors.{label}", "categorical", family, 1.0))
        return ProbeOutcome(probe=self.name, ok=True, signals=signals, notes=notes)
