"""对抗性文本生成器：探测集不可预知是对抗"中转站硬编码答案"的核心机制。

canonical 文本池随包发布，是公开信息——中转可以对固定文本预置答案。
adversarial 模式改为按 seed 确定性生成探测文本：
- 同 seed 同文本（证据链可复现，fuzz 测试锁定）；
- 换 seed 即换题（--seed 旋转 = 探测集轮换）；
- 构造上最大化 tokenizer 分歧：混合文种、ZWJ emoji 序列、分解组合字符、
  罕见 CJK 区块、全角形式、长数字串——各家族 tokenizer 在这些类别上分歧最大。

诚实边界：字符池在源码里公开，安全性与 canonical 一样不依赖保密，
依赖的是"探测集随 seed 轮换"带来的不可预置性（见 ROADMAP seed 轮换条目）。
"""

from __future__ import annotations

import random

_CJK_COMMON = (
    "的一是了我不人在他有这上们来到时大地为子中你说生国年着就那和要她出也得里后自以"
    "会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想作种开"
    "美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱老因很给名法间"
    "斯知世什两次使身者被高已亲其进此话常与活正感见问没理心明关文点几认工"
)
_CJK_RARE = "饕餮貔貅魑魅魍魉龘靐齉爩鱻麤龗灪彧翀赟燚垚犇骉羴猋龠龥黁燊淼焱鑫"
_ASCII_WORDS = [
    "model", "verify", "fingerprint", "token", "relay", "anchor", "quartz",
    "pixel", "vector", "lambda", "kernel", "matrix", "signal", "cipher", "drift",
    "baseline", "probe", "verdict", "margin", "evidence",
]
_EMOJI_SINGLE = ["🚀", "🎉", "🔥", "💡", "🤖", "📌", "🧠", "✨", "🎯", "🧩"]
_EMOJI_ZWJ_PARTS = [
    ["👨", "👩", "👧"],  # 家庭 ZWJ 序列
    ["🧑", "🍳"],  # 职业_ZWJ_器具
    ["👩", "🔬"],
    ["🏳", "🌈"],  # 旗_ZWJ_彩虹
]
_FULLWIDTH = "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９"
_SEPARATORS = ["、", "·", "-", "_", "|", "／", "～", "#"]


def generate_adversarial_texts(seed: int, count: int = 12) -> list[tuple[str, str]]:
    """按 seed 确定性生成 count 条对抗文本，返回 [(id, text), ...]。

    id 形如 adv_<seed>_<i>——进入信号 meta，保证证据链可复现。
    """
    rng = random.Random(seed)
    out: list[tuple[str, str]] = []
    for i in range(count):
        parts: list[str] = []

        # 1) 常用 CJK（覆盖率最大）+ 罕见 CJK 区块（tokenizer 分歧最大）
        parts.append("".join(rng.sample(_CJK_COMMON, rng.randint(8, 16))))
        parts.append("".join(rng.sample(_CJK_RARE, rng.randint(3, 6))))

        # 2) ASCII 词串（英文侧 token 曲线）
        parts.append(" ".join(rng.sample(_ASCII_WORDS, rng.randint(3, 6))))

        # 3) 长数字串（数字聚合差异）
        parts.append(str(rng.randrange(10**11, 10**12)))

        # 4) 单 emoji + ZWJ 组合序列（多码点聚簇差异）
        emoji_bits = rng.sample(_EMOJI_SINGLE, rng.randint(1, 3))
        zwj = rng.choice(_EMOJI_ZWJ_PARTS)
        emoji_bits.append("\u200d".join(zwj))
        parts.append("".join(emoji_bits))

        # 5) 全角形式
        parts.append("".join(rng.sample(_FULLWIDTH, rng.randint(4, 8))))

        # 6) 分解组合字符（NFC/NFD 分歧：e + U+0301）
        base = rng.choice("aenu")
        parts.append(base + "\u0301" + base + "\u0308")

        # 用抽样的分隔符拼装，前缀固定字样保证"像正常输入"
        seps = rng.sample(_SEPARATORS, 3)
        body = parts[0]
        for j, p in enumerate(parts[1:]):
            body += seps[j % len(seps)] + p
        text = f"样本{i}（seed{seed}）：{body}"
        out.append((f"adv_{seed}_{i}", text))

    # 类别不变量：每条都含 CJK 与 ASCII（保证对各家 tokenizer 都有分歧信号）
    for _, text in out:
        assert any("\u4e00" <= ch <= "\u9fff" for ch in text), text
        assert any(ch.isascii() and ch.isalnum() for ch in text), text
    return out
