from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from laborman_agent.owa.parser import (
    AttendanceRecord,
    ParseError,
    ParserRules,
    mentions_date,
    parse_attendance,
    parse_body,
    parse_subject,
)

FIXTURES = Path(__file__).parent / "fixtures"
JST = ZoneInfo("Asia/Tokyo")
TARGET = date(2026, 10, 9)


def load_mail(path: Path) -> tuple[str, str]:
    """フィクスチャは 1 行目が「件名: …」、空行のあとが本文。"""
    header, _, body = path.read_text(encoding="utf-8").partition("\n\n")
    assert header.startswith("件名: ")
    return header.removeprefix("件名: "), body


def case(name: str) -> tuple[str, str]:
    return load_mail(FIXTURES / "hr_mail_cases" / f"{name}.txt")


def test_parses_subject_without_body() -> None:
    record = parse_attendance("[勤怠情報]2026/10/09:開始08:29/終了18:38", None, TARGET)
    assert record == AttendanceRecord(TARGET, "08:29", "18:38")
    assert record.start_at() == datetime(2026, 10, 9, 8, 29, tzinfo=JST)
    assert record.end_at() == datetime(2026, 10, 9, 18, 38, tzinfo=JST)


def test_falls_back_to_body_when_subject_does_not_match() -> None:
    subject, body = case("subject_changed")
    assert parse_subject(subject) is None
    assert parse_attendance(subject, body, TARGET) == AttendanceRecord(TARGET, "08:29", "18:38")


def test_ignores_overtime_in_body() -> None:
    subject, body = case("subject_changed")
    record = parse_body(body)
    # 残業時間 12:44:49 は取り込まない
    assert (record.start, record.end) == ("08:29", "18:38")


def test_fails_when_subject_date_differs_from_target() -> None:
    subject, body = case("other_day")
    with pytest.raises(ParseError, match="一致しません"):
        parse_attendance(subject, body, TARGET)


def test_fails_when_body_date_differs_from_target() -> None:
    _, body = case("other_day")
    with pytest.raises(ParseError, match="一致しません"):
        parse_attendance("勤怠情報のお知らせ", body, TARGET)


def test_normalizes_fullwidth_characters() -> None:
    subject, body = case("fullwidth")
    assert parse_attendance(subject, None, TARGET) == AttendanceRecord(TARGET, "08:29", "18:38")
    assert parse_body(body) == AttendanceRecord(TARGET, "08:29", "18:38")


def test_fails_when_neither_subject_nor_body_parses() -> None:
    subject, body = case("unparseable")
    with pytest.raises(ParseError):
        parse_attendance(subject, body, TARGET)


def test_fails_without_body_when_subject_does_not_match() -> None:
    with pytest.raises(ParseError):
        parse_attendance("勤怠情報のお知らせ", None, TARGET)


def test_invalid_time_in_subject_falls_back_to_body() -> None:
    _, body = case("subject_changed")
    subject = "[勤怠情報]2026/10/09:開始08:29/終了18:99"
    assert parse_subject(subject) is None
    assert parse_attendance(subject, body, TARGET).end == "18:38"


def test_accepts_times_after_midnight() -> None:
    record = parse_attendance("[勤怠情報]2026/10/09:開始9:00/終了25:15", None, TARGET)
    assert (record.start, record.end) == ("09:00", "25:15")
    assert record.end_at() == datetime(2026, 10, 10, 1, 15, tzinfo=JST)


def test_rules_can_be_overridden() -> None:
    rules = ParserRules.from_mapping(
        {"subject_pattern": r"Attendance (?P<date>\d{4}/\d{2}/\d{2}) (?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})"}
    )
    record = parse_attendance("Attendance 2026/10/09 09:00-18:00", None, TARGET, rules)
    assert (record.start, record.end) == ("09:00", "18:00")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[勤怠情報]2026/10/09:開始08:29/終了18:38", True),
        ("[勤怠情報]2026/10/9", True),
        ("［勤怠情報］２０２６／１０／０９", True),
        ("[勤怠情報]2026/10/08:開始08:29/終了18:38", False),
        ("勤怠情報", False),
    ],
)
def test_mentions_date(text: str, expected: bool) -> None:
    assert mentions_date(text, TARGET) is expected


# 実メール（宛名の氏名を除いたもの）。件名と本文のどちらからも同じ値が取れること
REAL_MAILS = sorted((FIXTURES / "hr_mail").glob("*.txt"))


@pytest.mark.parametrize("path", REAL_MAILS, ids=[path.name for path in REAL_MAILS])
def test_real_mails_parse_with_default_rules(path: Path) -> None:
    subject, body = load_mail(path)
    from_subject = parse_subject(subject)
    assert from_subject is not None
    from_body = parse_body(body)
    assert from_subject == from_body
    assert parse_attendance(subject, body, from_subject.work_date) == from_subject
