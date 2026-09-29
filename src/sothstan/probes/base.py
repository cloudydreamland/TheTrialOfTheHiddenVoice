"""探测基类与上下文。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from sothstan.http import ApiClient
from sothstan.types import ProbeOutcome


class ProbeContext:
    """探测运行上下文：客户端 + 随机源 + 选项。

    rng 是种子化的 random.Random：同 seed 同探测计划 → 同 canonical 文本选择 →
    同一证据链可复现。种子默认公开固定；换种子是对抗"中转站硬编码探测文本"的手段。
    """

    def __init__(
        self,
        client: ApiClient,
        model: str,
        rng: object | None = None,
        options: dict | None = None,
    ) -> None:
        import random

        self.client = client
        self.model = model
        self.rng = rng if rng is not None else random.Random(20260928)
        self.options = options or {}


class Probe(ABC):
    """探测器子类实现 run()，产出 ProbeOutcome。

    tier 语义：
    - 1：确定性信号（token 计数、限额、错误码族）——中转站几乎无法伪造而不真正服务该模型
    - 2：行为性信号（回复风格、思维链形态）——可伪造但伪造面大
    - 3：环境性信号（延迟）——噪声大，默认关闭
    """

    name: ClassVar[str]
    tier: ClassVar[int]

    def __init__(self, ctx: ProbeContext) -> None:
        self.ctx = ctx

    @abstractmethod
    def run(self) -> ProbeOutcome: ...

    def _user(self, text: str) -> list[dict]:
        return [{"role": "user", "content": text}]
