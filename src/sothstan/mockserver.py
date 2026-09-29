"""内置 mock 模型服务器：离线测试与 selftest 的基础设施。

两个"人格"（Aqua/Breeze）用确定性的伪 tokenizer（按字符类别比率计数）模拟
不同模型家族在 token 曲线、模板开销、限额、错误风格、行为风格上的差异。
这不是对任何真实模型的仿真——它的职责是让整条验真管线可以在 CI 里
无网络、无 key 地被端到端验证。

三种服务器形态：
- 诚实服务器：personality 原样响应
- 换模型中转（relay）：声称 claim，实际由 upstream 人格响应，只改写 model 字段
- 完美说谎中转（liar relay）：改 model 字段，且用 claim 人格重算 usage
  —— 模拟"中转知道要伪造 token 数"的最强攻击者
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@dataclass(frozen=True)
class Personality:
    model_id: str
    family: str
    # 每 64 字符的 token 数（按字符类别）
    rate_cjk: float
    rate_cjk_punct: float
    rate_ascii: float
    rate_ws: float
    rate_emoji: float
    rate_other: float
    overhead_per_msg: int
    system_extra: int
    reply_style: str  # "steps" | "terse"
    error_style: str  # "openai" | "detail"
    logprobs: bool
    unknown_param: str  # "reject" | "ignore"
    max_tokens_limit: int | None  # None = 不设上限


AQUA = Personality(
    model_id="aqua-70b",
    family="aqua",
    rate_cjk=64.0,
    rate_cjk_punct=56.0,
    rate_ascii=16.0,
    rate_ws=8.0,
    rate_emoji=32.0,
    rate_other=48.0,
    overhead_per_msg=4,
    system_extra=3,
    reply_style="steps",
    error_style="openai",
    logprobs=True,
    unknown_param="reject",
    max_tokens_limit=None,
)

BREEZE = Personality(
    model_id="breeze-8b",
    family="breeze",
    rate_cjk=48.0,
    rate_cjk_punct=40.0,
    rate_ascii=20.0,
    rate_ws=6.0,
    rate_emoji=48.0,
    rate_other=56.0,
    overhead_per_msg=7,
    system_extra=1,
    reply_style="terse",
    error_style="detail",
    logprobs=False,
    unknown_param="ignore",
    max_tokens_limit=100000,
)

# 同家族近亲：与 Aqua 只差 token 比率与模板开销（最难的冒充场景——
# 行为/错误/风格层完全一致，只有确定性计数层有 ~6% 偏移）
AQUA_LITE = Personality(
    model_id="aqua-lite",
    family="aqua",
    rate_cjk=58.0,
    rate_cjk_punct=52.0,
    rate_ascii=17.0,
    rate_ws=8.0,
    rate_emoji=32.0,
    rate_other=48.0,
    overhead_per_msg=5,
    system_extra=3,
    reply_style="steps",
    error_style="openai",
    logprobs=True,
    unknown_param="reject",
    max_tokens_limit=None,
)

DEMO_PERSONALITIES = [AQUA, BREEZE]


def _classes(text: str) -> dict[str, int]:
    counts = {"cjk": 0, "cjk_punct": 0, "ascii": 0, "ws": 0, "emoji": 0, "other": 0}
    for ch in text:
        o = ord(ch)
        if 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
            counts["cjk"] += 1
        elif 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
            counts["cjk_punct"] += 1
        elif ch.isascii() and (ch.isalnum()):
            counts["ascii"] += 1
        elif ch.isspace():
            counts["ws"] += 1
        elif o >= 0x1F000:
            counts["emoji"] += 1
        else:
            counts["other"] += 1
    return counts


def pseudo_tokens(p: Personality, text: str) -> int:
    c = _classes(text)
    raw = (
        c["cjk"] * p.rate_cjk
        + c["cjk_punct"] * p.rate_cjk_punct
        + c["ascii"] * p.rate_ascii
        + c["ws"] * p.rate_ws
        + c["emoji"] * p.rate_emoji
        + c["other"] * p.rate_other
    ) / 64.0
    return max(1, math.ceil(raw)) if text else 0


_STEPS_REPLY = (
    "**步骤 1**：13 × 10 = 130。\n**步骤 2**：13 × 7 = 91。\n"
    "**步骤 3**：130 + 91 = 221。\n最终答案：221"
)
_TERSE_REPLY = "221"
_GENERIC_REPLY = "好的，已收到。"


def reply_for(p: Personality, messages: list[dict]) -> str:
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = str(m.get("content") or "")
            break
    if "步骤" in last_user or "一步一步" in last_user or "step" in last_user.lower():
        return _STEPS_REPLY if p.reply_style == "steps" else _TERSE_REPLY
    return _GENERIC_REPLY


def _error(p: Personality, status_openai: int, message: str) -> tuple[int, dict]:
    if p.error_style == "openai":
        return status_openai, {"error": {"message": message, "type": "invalid_request_error"}}
    return 422, {"detail": message}


def _respond(p: Personality, payload: dict) -> tuple[int, dict]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return _error(p, 400, "Invalid parameter: messages must not be empty")
    for m in messages:
        role = m.get("role")
        if role not in {"system", "user", "assistant"}:
            return _error(p, 400, f"Invalid parameter: invalid role {role!r}")
    temp = payload.get("temperature")
    if temp is not None and not (isinstance(temp, (int, float)) and 0 <= temp <= 2):
        return _error(p, 400, "Invalid parameter: temperature must be between 0 and 2")
    if payload.get("sothstan_probe_unknown") is not None and p.unknown_param == "reject":
        return _error(p, 400, "Invalid parameter: unknown parameter 'sothstan_probe_unknown'")
    max_tokens = payload.get("max_tokens")
    if (
        max_tokens is not None
        and p.max_tokens_limit is not None
        and max_tokens > p.max_tokens_limit
    ):
        return _error(p, 400, "Invalid parameter: max_tokens is too large")

    prompt_tokens = p.overhead_per_msg * len(messages)
    if any(m.get("role") == "system" for m in messages):
        prompt_tokens += p.system_extra
    prompt_tokens += sum(pseudo_tokens(p, str(m.get("content") or "")) for m in messages)

    reply = reply_for(p, messages)
    completion_tokens = pseudo_tokens(p, reply)
    finish = "stop"
    if max_tokens is not None and completion_tokens > max_tokens:
        completion_tokens = max_tokens
        reply = reply[: max_tokens * 2]
        finish = "length"

    choice: dict = {"message": {"role": "assistant", "content": reply}, "finish_reason": finish}
    if payload.get("logprobs") and p.logprobs:
        choice["logprobs"] = {"content": [{"token": "x", "logprob": -0.12, "top_logprobs": []}]}
    body = {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 1767000000,
        "model": p.model_id,
        "choices": [choice],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return 200, body


class _MockServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, personality: Personality, claim: str | None = None,
                 liar_usage: Personality | None = None) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.personality = personality
        self.claim = claim
        self.liar_usage = liar_usage  # 非 None：用该人格重算 usage（完美说谎中转）

    def respond(self, payload: dict) -> tuple[int, dict]:
        status, body = _respond(self.personality, payload)
        if status == 200:
            if self.liar_usage is not None:
                liar_status, liar_body = _respond(self.liar_usage, payload)
                # 说谎中转只在能重算出声称模型 usage 时才伪造；否则回落真实 usage
                # （这也正是现实约束：伪造 token 数要求复刻目标 tokenizer）
                if liar_status == 200:
                    body["usage"] = liar_body["usage"]
            if self.claim:
                body["model"] = self.claim
        return status, body


class _Handler(BaseHTTPRequestHandler):
    server: _MockServer

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.rstrip("/").endswith("chat/completions"):
            self._send(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(
                400,
                {"error": {"message": "Invalid JSON body", "type": "invalid_request_error"}},
            )
            return
        status, body = self.server.respond(payload)
        self._send(status, body)

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:  # 静默
        pass


def start_server(
    personality: Personality,
    claim: str | None = None,
    liar_usage: Personality | None = None,
) -> tuple[_MockServer, str]:
    """启动 mock 服务器，返回 (server, base_url)。用完必须 shutdown_server。"""
    server = _MockServer(personality, claim=claim, liar_usage=liar_usage)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def shutdown_server(server: _MockServer) -> None:
    server.shutdown()
    server.server_close()


class FlakyServer(_MockServer):
    """前 fail_times 次请求返回 429（限流），之后交给底层人格——测试重试行为。"""

    def __init__(self, personality: Personality, fail_times: int = 2) -> None:
        super().__init__(personality)
        self.fail_times = fail_times
        self._seen = 0

    def respond(self, payload: dict) -> tuple[int, dict]:
        self._seen += 1
        if self._seen <= self.fail_times:
            return 429, {"error": {"message": "rate limited, retry later",
                                   "type": "rate_limit_error"}}
        return super().respond(payload)
