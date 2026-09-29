"""mock 人格的伪 tokenizer：确定性、类别敏感。"""

from __future__ import annotations

from sothstan.mockserver import AQUA, BREEZE, pseudo_tokens


def test_deterministic():
    text = "出租方同意将房屋出租给承租方，租金每月 ¥8,000。"
    assert pseudo_tokens(AQUA, text) == pseudo_tokens(AQUA, text)
    assert pseudo_tokens(BREEZE, text) == pseudo_tokens(BREEZE, text)


def test_empty_is_zero():
    assert pseudo_tokens(AQUA, "") == 0


def test_personalities_diverge_on_cjk():
    """CJK 比率不同 → 同一文本两家人格计数不同（这是 CJK 指纹信号的根据）。"""
    text = "大语言模型在中文场景下的分词行为与英文存在显著差异。"
    assert pseudo_tokens(AQUA, text) != pseudo_tokens(BREEZE, text)


def test_personalities_diverge_on_ascii():
    text = "please verify the model identity carefully 12345"
    assert pseudo_tokens(AQUA, text) != pseudo_tokens(BREEZE, text)


def test_cjk_denser_than_ascii_for_aqua():
    """Aqua: 1 char/token for CJK vs 4 chars/token for ASCII。"""
    zh = pseudo_tokens(AQUA, "一二三四五六七八九十八")
    en = pseudo_tokens(AQUA, "abcdefghijklmnopqrst")
    assert zh > en * 2
