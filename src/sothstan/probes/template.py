"""TemplateProbe：chat template 开销指纹。

不同模型渲染消息的模板不同：系统提示的额外开销、空消息的基础开销、
多轮增长的每消息边际，都是稳定可测的确定性信号。

信号：
- template.empty_user_total   int  weight 1.5
- template.system_overhead    int  weight 1.0
- template.pair_growth        int  weight 1.0
"""

from __future__ import annotations

from sothstan.probes.base import Probe
from sothstan.probes.canon import CANON_BY_ID
from sothstan.types import ProbeOutcome, Signal


class TemplateProbe(Probe):
    name = "template"
    tier = 1

    def run(self) -> ProbeOutcome:
        text = CANON_BY_ID["zh_mid_1"]
        system_text = "你是一个严谨的助手。"

        notes: list[str] = []
        empty_total = self._tokens([{"role": "user", "content": ""}], notes, "empty_user")
        with_system = self._tokens(
            [{"role": "system", "content": system_text}, {"role": "user", "content": text}],
            notes,
            "with_system",
        )
        without_system = self._tokens([{"role": "user", "content": text}], notes, "without_system")
        pair = self._tokens(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": "好的。"},
                {"role": "user", "content": text},
            ],
            notes,
            "pair",
        )

        signals: list[Signal] = []
        if empty_total is not None:
            signals.append(
                Signal("template.empty_user_total", "int", empty_total, 1.5)
            )
        if with_system is not None and without_system is not None:
            signals.append(
                Signal("template.system_overhead", "int", with_system - without_system, 1.0)
            )
        if pair is not None and without_system is not None:
            signals.append(Signal("template.pair_growth", "int", pair - without_system, 1.0))
        return ProbeOutcome(probe=self.name, ok=bool(signals), signals=signals, notes=notes)

    def _tokens(self, messages: list[dict], notes: list[str], label: str) -> int | None:
        try:
            resp = self.ctx.client.chat(messages, self.ctx.model, max_tokens=1, temperature=0)
        except Exception as exc:
            notes.append(f"{label}: {type(exc).__name__}")
            return None
        if resp.prompt_tokens is None:
            notes.append(f"{label}: usage 缺失")
            return None
        return resp.prompt_tokens
