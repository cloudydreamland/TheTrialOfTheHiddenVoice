"""零依赖 OpenAI 兼容 HTTP 客户端（urllib）+ 请求预算 + 证据链转录。

设计约束：
- 核心零必装依赖：只用标准库。
- 证据链：每次请求/响应进入 Transcript，可计算稳定 sha256（审计报告可复现）。
- 预算：max_requests / max_prompt_tokens 双熔断，防止探测失控烧钱。
- API key 永不写入转录（redact）。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


def _slug(text: str, limit: int = 32) -> str:
    """错误消息的稳定摘要：小写、仅字母数字、截断。用于构造错误码族。"""
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower())[:limit].strip("_")


class ApiError(Exception):
    """端点返回错误。family 是可用于指纹的"错误码族"字符串。"""

    # 瞬时状态码：限流/服务端临时故障。它们反映的是中转的负载而非模型指纹，
    # 必须在客户端重试消耗掉；重试耗尽后探测器应记 "transient" 而非伪指纹。
    TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(self, status: int, message: str, body: Any = None) -> None:
        self.status = status
        self.message = message
        self.body = body
        self.family = f"{status}|{_slug(message)}"
        self.transient = status in self.TRANSIENT_STATUSES
        super().__init__(f"HTTP {status}: {message}")

    def __reduce__(self) -> tuple:  # 允许 pytest 在断言消息里展示
        return (ApiError, (self.status, self.message, self.body))


class BudgetExceeded(BaseException):
    """探测预算熔断（请求数或 prompt tokens 超限）。

    继承 BaseException 而非 Exception：这是控制流信号，必须穿透探测器的
    "单条失败不拖垮探测"兜底逻辑（except Exception）直达运行器——
    否则熔断会被当作普通探测失败吞掉。
    """


@dataclass
class ChatResponse:
    """一次 chat completion 的归一化结果。usage 字段可能缺失（有些中转会剥掉）。"""

    content: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    finish_reason: str | None
    model_field: str | None  # 响应体回显的 model 字段（可被中转改写，仅低权重展示）
    reasoning_present: bool  # 是否带 reasoning_content / reasoning 字段
    logprobs_present: bool
    raw: dict = field(default_factory=dict)
    latency_ms: float = 0.0


@dataclass
class TranscriptEntry:
    request: dict
    response: dict | None  # 出错时为 {"error": {...}}
    latency_ms: float
    ok: bool


class Transcript:
    """证据链：记录全部请求/响应（key 已脱敏），可计算稳定哈希。"""

    def __init__(self) -> None:
        self.entries: list[TranscriptEntry] = []

    def add(self, entry: TranscriptEntry) -> None:
        self.entries.append(entry)

    def canonical(self) -> list[dict]:
        """哈希用规范化视图：不含 latency（环境噪声），保证同输入同哈希。"""
        out = []
        for e in self.entries:
            out.append(
                {
                    "request": _redact(e.request),
                    "response": e.response,
                    "ok": e.ok,
                }
            )
        return out

    def sha256(self) -> str:
        payload = json.dumps(self.canonical(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __len__(self) -> int:
        return len(self.entries)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        sensitive = {"authorization", "api-key", "x-api-key"}
        return {
            k: ("***REDACTED***" if k.lower() in sensitive else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class ApiClient:
    """OpenAI 兼容 /chat/completions 客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        transcript: Transcript | None = None,
        max_requests: int | None = None,
        max_prompt_tokens: int | None = None,
        retries: int = 2,
        retry_backoff: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transcript = transcript if transcript is not None else Transcript()
        self.max_requests = max_requests
        self.max_prompt_tokens = max_prompt_tokens
        self.retries = retries
        self.retry_backoff = retry_backoff
        self._requests = 0
        self._prompt_tokens = 0

    @property
    def requests_used(self) -> int:
        return self._requests

    @property
    def prompt_tokens_used(self) -> int:
        return self._prompt_tokens

    def chat(
        self,
        messages: list[dict],
        model: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra: dict | None = None,
    ) -> ChatResponse:
        """发送一次请求（429/5xx/网络错误自动重试）。端点返回 4xx/5xx 时抛 ApiError。

        每次尝试（含失败重试）都进转录——证据链如实反映重试行为；
        重试退避为确定性的 0.5×2^k 秒（无随机抖动，保证测试与哈希可复现）。
        """
        attempt = 0
        while True:
            try:
                return self._chat_once(messages, model, temperature, max_tokens, extra)
            except ApiError as exc:
                if exc.transient and attempt < self.retries:
                    attempt += 1
                    time.sleep(self.retry_backoff * (2 ** (attempt - 1)))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < self.retries:
                    attempt += 1
                    time.sleep(self.retry_backoff * (2 ** (attempt - 1)))
                    continue
                raise

    def _chat_once(
        self,
        messages: list[dict],
        model: str,
        temperature: float | None,
        max_tokens: int | None,
        extra: dict | None,
    ) -> ChatResponse:
        if self.max_requests is not None and self._requests >= self.max_requests:
            raise BudgetExceeded(f"请求数预算已用尽（{self.max_requests}）")
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if extra:
            payload.update(extra)

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        start = time.perf_counter()
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            latency = (time.perf_counter() - start) * 1000.0
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw[:500]}
            message = _extract_error_message(parsed)
            self.transcript.add(
                TranscriptEntry(
                    request={"url": url, "headers": headers, "body": payload},
                    response={"error": parsed},
                    latency_ms=latency,
                    ok=False,
                )
            )
            self._requests += 1
            raise ApiError(exc.code, message, parsed) from exc

        latency = (time.perf_counter() - start) * 1000.0
        self._requests += 1
        self.transcript.add(
            TranscriptEntry(
                request={"url": url, "headers": headers, "body": payload},
                response=body,
                latency_ms=latency,
                ok=True,
            )
        )

        usage = body.get("usage") or {}
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        if isinstance(pt, int):
            self._prompt_tokens += pt
            if self.max_prompt_tokens is not None and self._prompt_tokens > self.max_prompt_tokens:
                raise BudgetExceeded(
                    f"prompt tokens 预算已超（{self._prompt_tokens} > {self.max_prompt_tokens}）"
                )

        choices = body.get("choices") or [{}]
        choice = choices[0]
        message_obj = choice.get("message") or {}
        content = message_obj.get("content")
        reasoning_present = bool(
            message_obj.get("reasoning_content") or message_obj.get("reasoning")
        )
        logprobs_present = bool(choice.get("logprobs") or choice.get("top_logprobs"))
        return ChatResponse(
            content=content,
            prompt_tokens=pt if isinstance(pt, int) else None,
            completion_tokens=ct if isinstance(ct, int) else None,
            finish_reason=choice.get("finish_reason"),
            model_field=body.get("model"),
            reasoning_present=reasoning_present,
            logprobs_present=logprobs_present,
            raw=body,
            latency_ms=latency,
        )


def _extract_error_message(parsed: Any) -> str:
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"]
        if isinstance(parsed.get("detail"), str):
            return parsed["detail"]
        if isinstance(parsed.get("message"), str):
            return parsed["message"]
        return json.dumps(parsed, ensure_ascii=False)
    return str(parsed)
