"""Canonical 文本池：所有 token 计数探测共用。

设计要点：
- 覆盖 tokenizer 分歧最大的类别：纯中文、中英混排、全角标点、数字、emoji、罕见字、代码。
- 完整池默认全跑（确定性）；``select()`` 支持种子化抽样，是对抗"中转站硬编码
  已知探测文本"的第一道机制——探测集不可预知，换 seed 即换题。
"""

from __future__ import annotations

CANON_TEXTS: list[tuple[str, str]] = [
    ("zh_short_1", "今天天气不错。"),
    ("zh_short_2", "账户余额不足，请及时充值。"),
    ("zh_mid_1", "出租方同意将房屋出租给承租方使用，租期自本合同签订之日起算，共计十二个月。"),
    ("zh_mid_2", "大语言模型在中文场景下的分词行为与英文存在显著差异，"
                 "这使得 token 计数成为可利用的指纹信号。"),
    ("zh_long_1", "这家小店的老板娘是重庆人，做的一碗小面麻、辣、鲜、香俱全，墙上贴着泛黄的老照片，"
                 "据说是九十年代她父母开店时拍的。每到中午，附近写字楼里的白领就排起长队，"
                 "有人专程跨过两条街来吃，吃完还要打包一份带回去。"),
    ("zh_long_2", "红楼梦是中国古典小说的巅峰之作，前八十回一般认为为曹雪芹所著。"
                  "全书以贾、史、王、薛四大家族的兴衰为背景，以贾宝玉与林黛玉、薛宝钗的爱情婚姻悲剧为主线，"
                  "展现了封建末世的社会百态。"),
    ("mix_zh_en_1", "我们采用 RLHF（Reinforcement Learning from Human Feedback）对齐模型输出。"),
    ("mix_zh_en_2", "请把这份 PDF 按 Chapter 3.2 的要求转换成 Markdown，表格保留原格式。"),
    ("numbers_1", "订单号 202609281234567890，金额 ¥12,345.67，增值税率 13%。"),
    ("numbers_2", "身份证 11010519491231002X，银行卡 6222 0202 0000 1234 567。"),
    ("fullwidth_1", "【重要】请于２０２６年１０月１日前，携带《原件》前来办理！！"),
    ("fullwidth_2", "（一）甲方应保证……（二）乙方不得……（三）本协议一式两份。"),
    ("emoji_1", "这个方案太棒了👍👍👍，明天开会再讨论一下细节🤔，辛苦大家了🙏"),
    ("emoji_2", "🚀🎉✨🔥💯🧠🤖📌"),
    ("rare_cjk_1", "饕餮貔貅魑魅魍魉，龘靐齉爩鱻麤龗灪吁。"),
    ("rare_cjk_2", "彧、翀、赟、燚、垚、犇、骉、羴——这些字做名字的人一定很困扰。"),
    ("code_1", "def verify(model_id: str) -> Verdict:\n"
               "    baseline = load(model_id)\n    return decide(baseline)"),
    ("code_2", "SELECT id, name FROM users WHERE created_at > '2026-01-01' ORDER BY id LIMIT 100;"),
    ("repeat_1", "好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好好"),
    ("mixed_all", "Hi！版本 v2.3.1 已发布🚀，含 3 个修复；"
                  "详见《发布说明》，或发邮件至 support@example.com 咨询。"),
]

CANON_BY_ID = dict(CANON_TEXTS)


def select(rng, k: int | None = None) -> list[tuple[str, str]]:
    """按 rng 选择 canonical 文本。k=None 表示全选（确定性）。"""
    if k is None or k >= len(CANON_TEXTS):
        return list(CANON_TEXTS)
    return rng.sample(CANON_TEXTS, k)
