"""zac の案件名・売上項目名に含まれる年月表記の読み取り。"""

from __future__ import annotations

import re
import unicodedata

# 期間（例：(2026/09-2026/12)）は特定の月ではないため対象年月なしとする
_RANGE = re.compile(r"\d{4}/\d{1,2}\s*[-~〜]\s*\d{4}/\d{1,2}")
_PATTERNS: tuple[tuple[re.Pattern[str], bool], ...] = (
    (re.compile(r"(?<!\d)(\d{4})/(\d{1,2})(?!\d)"), False),  # （2026／10）
    (re.compile(r"(?<!\d)(\d{4})年(\d{1,2})月"), False),  # （2026年8月分）
    (re.compile(r"(?<![\d/])(\d{2})/(\d{1,2})(?![\d/])"), True),  # (26/10)
)
_BRACKETED = re.compile(r"[(\[][^()\[\]]*[)\]]")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


def _find(text: str) -> re.Match[str] | None:
    for pattern, _ in _PATTERNS:
        match = pattern.search(text)
        if match:
            return match
    return None


def parse_valid_month(name: str) -> str | None:
    """名前の年月表記から対象年月（YYYY-MM）を読み取る。年月がない・期間の場合は None。"""
    text = normalize(name)
    if _RANGE.search(text):
        return None
    for pattern, two_digit_year in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year, month = int(match.group(1)), int(match.group(2))
        if two_digit_year:
            year += 2000
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}"
    return None


def series_name_of(name: str) -> str | None:
    """年月表記を含む案件名から、年月を除いたシリーズ名を求める（年月がなければ None）。"""
    if parse_valid_month(name) is None:
        return None
    text = normalize(name)
    # 年月を含む括弧ごと除く。括弧がなければ年月の部分だけを除く
    without = _BRACKETED.sub(lambda m: "" if _find(m.group(0)) else m.group(0), text)
    if without == text:
        match = _find(text)
        assert match is not None
        without = text[: match.start()] + text[match.end() :]
    return re.sub(r"\s+", " ", without).strip() or None
