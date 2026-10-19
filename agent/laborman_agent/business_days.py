from __future__ import annotations

from datetime import date, timedelta

import jpholiday


def is_business_day(day: date) -> bool:
    """土日と日本の祝日以外を営業日とする。"""
    return day.weekday() < 5 and not jpholiday.is_holiday(day)


def previous_business_day(today: date) -> date:
    day = today - timedelta(days=1)
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


def parse_date_arg(value: str) -> date:
    """--date の値（YYYY-MM-DD）を解釈する。不正な値は ValueError。"""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"日付は YYYY-MM-DD 形式で指定してください: {value}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"日付は YYYY-MM-DD 形式で指定してください: {value}")
    return parsed


def resolve_target_date(value: str | None, today: date | None = None) -> date:
    """対象日。指定がなければ実行日の前営業日。"""
    if value:
        return parse_date_arg(value)
    return previous_business_day(today or date.today())
