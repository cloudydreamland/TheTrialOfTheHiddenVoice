"""TokenCountProbe：最强的一层指纹。

原理：API 在 usage 里自报 prompt_tokens / completion_tokens。中转站若换成别的模型，
token 数会随替代模型的 tokenizer 走——尤其在 CJK 文本上，各家 tokenizer 的
字符/词元比率差异巨大（modelprint 实测 GLM 家族 4/4 命中）。要让 token 数
冒充目标模型，中转必须同时复刻目标 tokenizer 并主动说谎，伪造面远大于"转发"。

信号：
- token_count.prompt_curve   int_vector  weight 2.0
- token_count.completion_int int         weight 1.0
"""

from __future__ import annotations

from sothstan.probes.base import Probe, ProbeContext
from sothstan.probes.canon import select
from sothstan.types import ProbeOutcome, Signal


class TokenCountProbe(Probe):
    name = "token_count"
    tier = 1

    def __init__(self, ctx: ProbeContext) -> None:
        super().__init__(ctx)
        self._prompt_curve: list[int] = []
        self._used_ids: list[str] = []
        self._skipped: list[str] = []

    def run(self) -> ProbeOutcome:
        mode = "adversarial" if self.ctx.options.get("adversarial") else "canon"
        if mode == "adversarial":
            # 对抗模式：探测文本按 seed 生成（同 seed 可复现，换 seed 即换题）
            from sothstan.probes.adversarial import generate_adversarial_texts

            gen_seed = int(self.ctx.options.get("seed", 20260928))
            chosen = generate_adversarial_texts(
                gen_seed, int(self.ctx.options.get("adversarial_count", 12))
            )
        else:
            k = self.ctx.options.get("token_count_sample")
            chosen = select(self.ctx.rng, k)
        for cid, text in chosen:
            try:
                resp = self.ctx.client.chat(
                    self._user(text), self.ctx.model, max_tokens=1, temperature=0
                )
            except Exception as exc:  # 单条失败不拖垮整个探测，如实记录
                self._skipped.append(f"{cid}: {type(exc).__name__}")
                continue
            if resp.prompt_tokens is None:
                self._skipped.append(f"{cid}: usage 缺失 prompt_tokens")
                continue
            self._prompt_curve.append(resp.prompt_tokens)
            self._used_ids.append(cid)

        completion = self._completion_signal()

        signals: list[Signal] = []
        notes: list[str] = list(self._skipped)
        if self._prompt_curve:
            signals.append(
                Signal(
                    name="token_count.prompt_curve",
                    kind="int_vector",
                    value=self._prompt_curve,
                    weight=2.0,
                    meta={"canon_ids": self._used_ids, "mode": mode},
                )
            )
        else:
            notes.append("prompt_curve 无有效观测（端点未回 usage？）")
        if completion is not None:
            signals.append(completion)
        else:
            notes.append("completion_int 无有效观测")

        return ProbeOutcome(probe=self.name, ok=bool(signals), signals=signals, notes=notes)

    def _completion_signal(self) -> Signal | None:
        try:
            resp = self.ctx.client.chat(
                self._user("用一句话解释什么是 RAG。"),
                self.ctx.model,
                max_tokens=32,
                temperature=0,
            )
        except Exception as exc:
            self._skipped.append(f"completion: {type(exc).__name__}")
            return None
        if resp.completion_tokens is None:
            return None
        return Signal(
            name="token_count.completion_int",
            kind="int",
            value=resp.completion_tokens,
            weight=1.0,
            meta={"finish_reason": resp.finish_reason},
        )
