"""共享类型：信号（Signal）与探测结果（ProbeOutcome）。

信号是证据的最小单位。命名约定：全局唯一名 ``{probe}.{signal}``。
四种 kind，对应四种比较方式（见 sothstan.compare）：

- ``int_vector``  ：整数向量（如 canonical 文本的 prompt_tokens 曲线）
- ``int``         ：单个整数（如 completion_tokens、template 开销）
- ``categorical`` ：类别（如错误码族、回复风格标记）
- ``bool``        ：布尔（如是否支持 logprobs）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

SIGNAL_KINDS = frozenset({"int_vector", "int", "categorical", "bool"})


class VerdictLabel(str, Enum):
    """判决标签。含义与阈值见 sothstan.verdict。"""

    AUTHENTIC = "AUTHENTIC"
    SUSPICIOUS = "SUSPICIOUS"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class Signal:
    """一次探测产出的一个指纹信号。"""

    name: str  # 全局唯一："{probe}.{signal}"
    kind: str
    value: object  # int_vector -> list[int]；int -> int；categorical -> str；bool -> bool
    weight: float = 1.0
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in SIGNAL_KINDS:
            raise ValueError(f"未知信号类型: {self.kind!r}（合法: {sorted(SIGNAL_KINDS)}）")


@dataclass
class ProbeOutcome:
    """一个探测的运行结果：产出的信号 + 如实的备注（跳过原因等）。"""

    probe: str
    ok: bool
    signals: list[Signal] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
