from __future__ import annotations

from datetime import date

import pytest

from laborman_agent.business_days import parse_date_arg, previous_business_day, resolve_target_date


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        # 火曜は前日の月曜
        (date(2026, 10, 6), date(2026, 10, 5)),
        # 月曜は前週の金曜
        (date(2026, 10, 19), date(2026, 10, 16)),
        # 祝日（10/12 スポーツの日）明けの火曜は金曜
        (date(2026, 10, 13), date(2026, 10, 9)),
        # 連休（9/19〜9/23 シルバーウィーク）明け
        (date(2026, 9, 24), date(2026, 9, 18)),
        # ゴールデンウィーク（5/2〜5/6）明け
        (date(2026, 5, 7), date(2026, 5, 1)),
    ],
)
def test_previous_business_day(today: date, expected: date) -> None:
    assert previous_business_day(today) == expected


def test_resolve_target_date_defaults_to_previous_business_day() -> None:
    assert resolve_target_date(None, today=date(2026, 10, 12)) == date(2026, 10, 9)


def test_resolve_target_date_uses_explicit_date() -> None:
    # 祝日・土日でも指定どおり
    assert resolve_target_date("2026-10-12", today=date(2026, 10, 13)) == date(2026, 10, 12)


@pytest.mark.parametrize("value", ["2026/10/09", "2026-10-9", "20261009", "2026-13-01", "yesterday"])
def test_parse_date_arg_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_date_arg(value)
