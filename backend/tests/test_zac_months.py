from __future__ import annotations

import pytest

from app.zac_months import parse_valid_month, series_name_of


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("プロジェクトサポート（2026／10）", "2026-10"),
        ("プロジェクトサポート（2026/9）", "2026-09"),
        ("bizoceanAPPs開発(26/10)", "2026-10"),
        ("第26期 XDG運営業務(26/09)", "2026-09"),
        ("第26期 ﾋﾞｽﾞｵｰｼｬﾝ運営業務（2026年8月分）", "2026-08"),
        # 期間は特定の月ではない
        ("エンジンファーム様プロジェクトサポート（2026／09-2026／12）", None),
        # 年月表記なし（「第26期」は年月ではない）
        ("社内管理業務", None),
        ("第26期 Ｒ＆Ｄ戦略室 社内管理業務", None),
        ("サービス開発本部 make.AI 業務", None),
        ("不正な月(26/13)", None),
    ],
)
def test_parse_valid_month(name: str, expected: str | None) -> None:
    assert parse_valid_month(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bizoceanAPPs開発(26/10)", "bizoceanAPPs開発"),
        ("bizoceanAPPs開発(26/11)", "bizoceanAPPs開発"),
        ("第26期 XDG運営業務(26/09)", "第26期 XDG運営業務"),
        ("第26期 ﾋﾞｽﾞｵｰｼｬﾝ運営業務（2026年8月分）", "第26期 ビズオーシャン運営業務"),
        ("エンジンファーム様プロジェクトサポート（2026／09-2026／12）", None),
        ("サービス開発本部 make.AI 業務", None),
    ],
)
def test_series_name(name: str, expected: str | None) -> None:
    assert series_name_of(name) == expected
