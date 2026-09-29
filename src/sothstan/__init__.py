"""Sothstan — LLM API 模型验真。

一个端点声称自己在服务模型 X，它真的在服务 X 吗？
sothstan 用探测（probe）提取指纹信号（signal），与官方模型指纹基线（baseline）
做混淆集似然比比较（confusion-set likelihood ratio），给出统计判决（verdict）。
"""

from sothstan._version import __version__
from sothstan.baseline import Baseline, load_baseline, save_baseline
from sothstan.http import ApiClient, ApiError, BudgetExceeded
from sothstan.runner import collect_baseline_signals, verify
from sothstan.types import Signal, VerdictLabel
from sothstan.verdict import Verdict, decide

__all__ = [
    "ApiError",
    "ApiClient",
    "Baseline",
    "BudgetExceeded",
    "Signal",
    "Verdict",
    "VerdictLabel",
    "collect_baseline_signals",
    "decide",
    "load_baseline",
    "save_baseline",
    "verify",
    "__version__",
]
