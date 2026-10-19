from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from laborman_agent.config import DEFAULT_PARSER_PATTERNS

APP_TIMEZONE = ZoneInfo("Asia/Tokyo")
# 勤務日基準の時刻は 00:00〜29:59（24:00 以降は翌日）
MAX_WORK_HOURS = 30
DATE_IN_TEXT = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")


class ParseError(Exception):
    """人事メールから対象日の出退勤を抽出できない。メッセージにメール本文を含めないこと。"""


@dataclass(frozen=True)
class ParserRules:
    subject_pattern: str
    body_date_pattern: str
    body_start_pattern: str
    body_end_pattern: str

    @classmethod
    def from_mapping(cls, patterns: dict[str, str]) -> ParserRules:
        merged = {**DEFAULT_PARSER_PATTERNS, **patterns}
        return cls(
            subject_pattern=merged["subject_pattern"],
            body_date_pattern=merged["body_date_pattern"],
            body_start_pattern=merged["body_start_pattern"],
            body_end_pattern=merged["body_end_pattern"],
        )


DEFAULT_RULES = ParserRules.from_mapping({})


@dataclass(frozen=True)
class AttendanceRecord:
    work_date: date
    start: str  # 勤務日基準の HH:MM
    end: str

    def start_at(self) -> datetime:
        return work_time_to_datetime(self.work_date, self.start)

    def end_at(self) -> datetime:
        return work_time_to_datetime(self.work_date, self.end)


def normalize(text: str) -> str:
    """全角数字・コロン・スラッシュなどを半角にそろえる。"""
    return unicodedata.normalize("NFKC", text)


def parse_mail_date(value: str) -> date:
    match = DATE_IN_TEXT.fullmatch(value.strip())
    if not match:
        raise ParseError(f"日付の形式が不正です: {value}")
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ParseError(f"日付が不正です: {value}") from exc


def parse_work_time(value: str) -> str:
    """HH:MM（24:00〜29:59 は翌日）を検証して 2 桁にそろえる。"""
    hours_text, _, minutes_text = value.strip().partition(":")
    if not (hours_text.isdigit() and minutes_text.isdigit()):
        raise ParseError(f"時刻の形式が不正です: {value}")
    hours, minutes = int(hours_text), int(minutes_text)
    if hours >= MAX_WORK_HOURS or minutes >= 60:
        raise ParseError(f"時刻が範囲外です: {value}")
    return f"{hours:02d}:{minutes:02d}"


def work_time_to_datetime(work_date: date, value: str) -> datetime:
    hours, minutes = (int(part) for part in value.split(":"))
    base = datetime.combine(work_date, time(0, 0), tzinfo=APP_TIMEZONE)
    return base + timedelta(hours=hours, minutes=minutes)


def mentions_date(text: str, target: date) -> bool:
    """文字列（件名など）に対象日（YYYY/MM/DD、ゼロ埋めなしも可）が含まれるか。"""
    for match in DATE_IN_TEXT.finditer(normalize(text)):
        year, month, day = (int(part) for part in match.groups())
        if (year, month, day) == (target.year, target.month, target.day):
            return True
    return False


def _record(work_date: str, start: str, end: str) -> AttendanceRecord:
    return AttendanceRecord(
        work_date=parse_mail_date(work_date),
        start=parse_work_time(start),
        end=parse_work_time(end),
    )


def parse_subject(subject: str, rules: ParserRules = DEFAULT_RULES) -> AttendanceRecord | None:
    """件名から出退勤を抽出する。書式・値が合わなければ None（本文で再試行する）。"""
    match = re.search(rules.subject_pattern, normalize(subject))
    if not match:
        return None
    try:
        return _record(match.group("date"), match.group("start"), match.group("end"))
    except ParseError:
        return None


def _body_value(pattern: str, body: str, group: str, label: str) -> str:
    match = re.search(pattern, body)
    if not match:
        raise ParseError(f"本文から{label}を抽出できません")
    return match.group(group)


def parse_body(body: str, rules: ParserRules = DEFAULT_RULES) -> AttendanceRecord:
    """本文の 対象日・開始時間・終了時間 から出退勤を抽出する（残業時間は使わない）。"""
    text = normalize(body)
    return _record(
        _body_value(rules.body_date_pattern, text, "date", "対象日"),
        _body_value(rules.body_start_pattern, text, "start", "開始時間"),
        _body_value(rules.body_end_pattern, text, "end", "終了時間"),
    )


def parse_attendance(
    subject: str,
    body: str | None,
    target: date,
    rules: ParserRules = DEFAULT_RULES,
) -> AttendanceRecord:
    """件名を先に試し、書式に合わなければ本文を試す。対象日と異なる日のメールは失敗とする。"""
    record = parse_subject(subject, rules)
    if record is None:
        if body is None:
            raise ParseError("件名が書式に合わず、本文もありません")
        record = parse_body(body, rules)
    if record.work_date != target:
        raise ParseError(
            f"メールの対象日 {record.work_date.isoformat()} が指定の対象日 {target.isoformat()} と一致しません"
        )
    return record
