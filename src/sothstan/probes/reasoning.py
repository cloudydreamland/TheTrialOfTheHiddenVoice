"""ReasoningProbe：行为层指纹（tier 2，可伪造但伪造面大）。

让模型解一道固定数学题，记录 completion_tokens 与回答风格标记。
行为可以被中转用提示词工程部分模仿，因此权重保守（1.0），且
风格分类器刻意粗糙（steps/thinking/terse/other），只抓大类差异。

信号：
- reasoning.completion_tokens  int          weight 1.0
- reasoning.style_marker       categorical  weight 1.0
- reasoning.reasoning_field    bool         weight 1.0
"""

from __future__ import annotations

from sothstan.probes.base import Probe
from sothstan.types import ProbeOutcome, Signal

_QUESTION = "13 乘 17 等于多少？请一步一步思考后给出最终答案，最后单独一行写\"最终答案：X\"。"


def classify_style(content: str) -> str:
    low = content.lower()
    has_final = ("最终答案" in content) or ("final answer" in low)
    if ("步骤" in content or "step" in low) and has_final:
        return "steps_with_final"
    if has_final:
        return "final_only"
    if len(content) < 40:
        return "terse"
    return "other"


class ReasoningProbe(Probe):
    name = "reasoning"
    tier = 2

    def run(self) -> ProbeOutcome:
        signals: list[Signal] = []
        notes: list[str] = []
        try:
            resp = self.ctx.client.chat(
                self._user(_QUESTION), self.ctx.model, max_tokens=512, temperature=0
            )
        except Exception as exc:
            notes.append(f"{type(exc).__name__}: {exc}")
            return ProbeOutcome(probe=self.name, ok=False, signals=[], notes=notes)

        if resp.completion_tokens is not None:
            signals.append(
                Signal("reasoning.completion_tokens", "int", resp.completion_tokens, 1.0)
            )
            # usage 与内容的自洽性（iter3 对抗实验产出）：伪造 usage 的中转若按
            # "声称模型自己的标准回复"重算 token 数，而真实回复内容是替代模型的，
            # 两者比例立刻劈叉。无需额外请求。
            content = resp.content or ""
            ratio = resp.completion_tokens * 1000 // max(1, len(content))
            signals.append(Signal("reasoning.completion_per_char", "int", ratio, 1.0))
        else:
            notes.append("usage 缺失 completion_tokens")
        style = classify_style(resp.content or "")
        signals.append(Signal("reasoning.style_marker", "categorical", style, 1.0))
        signals.append(Signal("reasoning.reasoning_field", "bool", resp.reasoning_present, 1.0))
        return ProbeOutcome(probe=self.name, ok=True, signals=signals, notes=notes)
