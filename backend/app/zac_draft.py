"""zac 登録ドラフトの算出（純粋関数。DB にはアクセスしない）。

手順（ZAC_AUTOMATION_SPEC.md §4.6）：出退勤 → 範囲内の休憩 → タスクのクリップ → 実働 → 空き時間
→ 入力行 → 検証。検証の順序に依存しないよう、検証結果をすべて集めてから登録可否を導出する。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas import (
    EntryStyle,
    IssueSeverity,
    ZacDraftAttendance,
    ZacDraftBreak,
    ZacDraftEntry,
    ZacDraftIssue,
    ZacDraftRead,
)

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class AttendanceInput:
    start_at: datetime | None
    end_at: datetime | None
    source: str | None
    kind: str


@dataclass(frozen=True)
class TaskInput:
    id: str
    job_code: str
    description: str
    start_at: datetime
    end_at: datetime | None
    work_kind: str | None = None
    sales_item_id: str | None = None


@dataclass(frozen=True)
class BreakInput:
    id: str
    start_at: datetime
    end_at: datetime | None


@dataclass(frozen=True)
class JobInfo:
    code: str
    zac_search_text: str
    name: str = ""
    # 月ごとの案件の対象年月（YYYY-MM）
    valid_month: str | None = None


@dataclass(frozen=True)
class SalesItemInfo:
    id: str
    job_code: str
    name: str
    valid_month: str | None = None


@dataclass(frozen=True)
class DraftSettings:
    entry_style: EntryStyle = "duration"
    clip_tolerance_minutes: int = 15
    gap_policy: str = "block"
    default_job_code: str | None = None
    default_work_kind: str | None = None
    default_sales_item_id: str | None = None
    description_max_length: int = 100


# 入力行のまとまり：（作業内容, ジョブ ID, 売上項目 ID）
RowKey = tuple[str, str, str]


@dataclass(frozen=True)
class ClippedTask:
    task: TaskInput
    start: datetime
    end: datetime


def floor_minute(value: datetime) -> datetime:
    """秒以下を切り捨て、UTC にそろえる（画面の HH:MM 表示と分数を一致させる）。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def minutes_between(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() // 60))


def overlaps(a: Interval, b: Interval) -> bool:
    """半開区間 [start, end) の重なり。隣接は重なりとみなさない。"""
    return a[0] < b[1] and b[0] < a[1]


def union(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(item for item in intervals if item[1] > item[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(base: Interval, covered: Sequence[Interval]) -> list[Interval]:
    """base から covered（union 済み）を差し引いた区間。"""
    gaps: list[Interval] = []
    cursor = base[0]
    for start, end in covered:
        if end <= cursor or start >= base[1]:
            continue
        if start > cursor:
            gaps.append((cursor, min(start, base[1])))
        cursor = max(cursor, end)
    if cursor < base[1]:
        gaps.append((cursor, base[1]))
    return gaps


class WorkTimeFormatter:
    """勤務日基準の HH:MM（翌日は 24:00〜）。"""

    def __init__(self, work_date: date, tz: ZoneInfo) -> None:
        self.work_date = work_date
        self.tz = tz

    def __call__(self, value: datetime) -> str:
        local = value.astimezone(self.tz)
        hours = local.hour + (local.date() - self.work_date).days * 24
        return f"{hours:02d}:{local.minute:02d}"

    def range(self, interval: Interval) -> str:
        return f"{self(interval[0])}–{self(interval[1])}"


def join_descriptions(descriptions: Iterable[str], max_length: int) -> str:
    """zac の備考の形式（「- 内容」の改行区切り。重複は除く）。"""
    unique: list[str] = []
    for text in descriptions:
        text = text.strip()
        if text and text not in unique:
            unique.append(text)
    return "\n".join(f"- {text}" for text in unique)[:max_length]


def build_zac_draft(
    *,
    work_date: date,
    attendance: AttendanceInput,
    tasks: Sequence[TaskInput],
    breaks: Sequence[BreakInput],
    jobs: dict[str, JobInfo],
    settings: DraftSettings,
    sales_items: dict[str, SalesItemInfo] | None = None,
    tz: ZoneInfo,
    zac_registered_at: datetime | None = None,
) -> ZacDraftRead:
    fmt = WorkTimeFormatter(work_date, tz)
    month = work_date.strftime("%Y-%m")
    items = sales_items or {}
    issues: list[ZacDraftIssue] = []

    def issue(code: str, severity: IssueSeverity, message: str, ref_id: str | None = None) -> None:
        issues.append(ZacDraftIssue(code=code, severity=severity, message=message, ref_id=ref_id))

    def finish(
        attendance_out: ZacDraftAttendance | None = None,
        breaks_out: list[ZacDraftBreak] | None = None,
        working_minutes: int | None = None,
        entries: list[ZacDraftEntry] | None = None,
    ) -> ZacDraftRead:
        if zac_registered_at is not None:
            issue("ALREADY_REGISTERED", "info", "zac に登録済みです")
        severities = {item.severity for item in issues}
        return ZacDraftRead(
            work_date=work_date,
            attendance=attendance_out,
            breaks=breaks_out or [],
            working_minutes=working_minutes,
            entry_style=settings.entry_style,
            entries=entries or [],
            issues=issues,
            registrable="error" not in severities,
            auto_allowed=not severities & {"error", "warning"},
            zac_registered_at=zac_registered_at,
        )

    # 1. 出退勤（打刻ではなく出退勤実績を使う）。休暇・未登録の日は以降を行わない
    if attendance.kind == "leave":
        issue("ON_LEAVE", "error", "休暇の日は zac に登録しません")
        return finish()
    if attendance.start_at is None or attendance.end_at is None:
        issue("ATTENDANCE_MISSING", "error", "出退勤（人事メール）が未取込です")
        return finish()
    att: Interval = (floor_minute(attendance.start_at), floor_minute(attendance.end_at))
    attendance_out = ZacDraftAttendance(start=fmt(att[0]), end=fmt(att[1]), source=attendance.source)

    finished_tasks: list[tuple[TaskInput, Interval]] = []
    for task in sorted(tasks, key=lambda item: item.start_at):
        if task.end_at is None:
            issue("TASK_RUNNING", "error", f"{fmt(floor_minute(task.start_at))}開始のタスクが終了していません", task.id)
            continue
        finished_tasks.append((task, (floor_minute(task.start_at), floor_minute(task.end_at))))
    finished_breaks: list[tuple[BreakInput, Interval]] = []
    for item in sorted(breaks, key=lambda entry: entry.start_at):
        if item.end_at is None:
            issue("TASK_RUNNING", "error", f"{fmt(floor_minute(item.start_at))}開始の休憩が終了していません", item.id)
            continue
        finished_breaks.append((item, (floor_minute(item.start_at), floor_minute(item.end_at))))

    if not tasks:
        issue("NO_TASKS", "error", "タスクが記録されていません")

    # 2. 出退勤の範囲内の休憩（はみ出した部分は切り詰める）。既定の休憩で補わない
    clipped_breaks = [
        (max(interval[0], att[0]), min(interval[1], att[1]))
        for _, interval in finished_breaks
        if overlaps(interval, att)
    ]
    break_union = union(clipped_breaks)
    if not break_union:
        issue("BREAK_MISSING", "error", "休憩が記録されていません。業務明細に休憩を記録してください")

    # 重なり（保存時には拒否しないため、ここで検出して登録を止める）
    for index, (task, interval) in enumerate(finished_tasks):
        for other, other_interval in finished_tasks[index + 1 :]:
            if overlaps(interval, other_interval):
                issue(
                    "TASK_OVERLAP",
                    "error",
                    f"{fmt.range(interval)} のタスクと {fmt.range(other_interval)} のタスクが重なっています",
                    task.id,
                )
        for _, break_interval in finished_breaks:
            if overlaps(interval, break_interval):
                issue(
                    "TASK_OVERLAP",
                    "error",
                    f"{fmt.range(interval)} のタスクと {fmt.range(break_interval)} の休憩が重なっています",
                    task.id,
                )

    for task, interval in finished_tasks:
        label = f"{fmt.range(interval)} のタスク"
        job = jobs.get(task.job_code)
        if job is None:
            issue("JOB_UNKNOWN", "error", f"ジョブ ID {task.job_code} はジョブマスタにありません", task.id)
        elif job.valid_month and job.valid_month != month:
            issue(
                "JOB_MONTH_MISMATCH",
                "error",
                f"{label}のジョブ {task.job_code} は {job.valid_month} の案件です（勤務日は {month}）",
                task.id,
            )
        if not task.work_kind:
            issue("WORK_KIND_MISSING", "error", f"{label}に作業内容が設定されていません", task.id)
        sales_item = items.get(task.sales_item_id or "")
        if sales_item is None:
            issue("SALES_ITEM_MISSING", "error", f"{label}に売上項目が設定されていません", task.id)
        elif sales_item.valid_month and sales_item.valid_month != month:
            issue(
                "SALES_ITEM_MONTH_MISMATCH",
                "warning",
                f"{label}の売上項目「{sales_item.name}」は {sales_item.valid_month} の項目です（勤務日は {month}）",
                task.id,
            )

    # 3. タスクのクリップ
    tolerance = timedelta(minutes=settings.clip_tolerance_minutes)
    clipped: list[ClippedTask] = []
    for task, (start, end) in finished_tasks:
        before = att[0] - start
        after = end - att[1]
        if before > tolerance:
            issue(
                "TASK_OUTSIDE_ATTENDANCE",
                "error",
                f"{fmt(start)}開始のタスクが出勤時刻{fmt(att[0])}より{minutes_between(start, att[0])}分前です",
                task.id,
            )
        elif before > timedelta(0):
            issue(
                "TASK_OUTSIDE_ATTENDANCE",
                "warning",
                f"{fmt(start)}開始のタスクを出勤時刻{fmt(att[0])}に切り詰めました",
                task.id,
            )
        if after > tolerance:
            issue(
                "TASK_OUTSIDE_ATTENDANCE",
                "error",
                f"{fmt(end)}終了のタスクが退勤時刻{fmt(att[1])}より{minutes_between(att[1], end)}分後です",
                task.id,
            )
        elif after > timedelta(0):
            issue(
                "TASK_OUTSIDE_ATTENDANCE",
                "warning",
                f"{fmt(end)}終了のタスクを退勤時刻{fmt(att[1])}に切り詰めました",
                task.id,
            )
        clipped_start, clipped_end = max(start, att[0]), min(end, att[1])
        if clipped_end > clipped_start:
            clipped.append(ClippedTask(task, clipped_start, clipped_end))

    # 4. 実働 = 退勤 − 出勤 − 範囲内の休憩
    break_minutes = sum(minutes_between(start, end) for start, end in break_union)
    working_minutes = minutes_between(*att) - break_minutes

    # 5. 空き時間（どのタスクにも休憩にも含まれない時間）
    gaps = subtract(att, union([*((item.start, item.end) for item in clipped), *break_union]))
    gaps = [gap for gap in gaps if minutes_between(*gap) >= 1]
    gap_assign: list[Interval] = []
    if gaps:
        ranges = "・".join(fmt.range(gap) for gap in gaps)
        if settings.gap_policy == "assign_default_job":
            default_job = settings.default_job_code or ""
            if default_job not in jobs:
                issue("JOB_UNKNOWN", "error", f"既定ジョブ {default_job or '(未設定)'} はジョブマスタにありません")
            if not settings.default_work_kind:
                issue("WORK_KIND_MISSING", "error", "空き時間を割り当てる既定の作業内容が設定されていません")
            if (settings.default_sales_item_id or "") not in items:
                issue("SALES_ITEM_MISSING", "error", "空き時間を割り当てる既定の売上項目が設定されていません")
            issue(
                "UNCOVERED_TIME",
                "warning",
                f"{ranges} を既定ジョブ {default_job} に割り当てました",
            )
            gap_assign = gaps
        else:
            issue("UNCOVERED_TIME", "error", f"{ranges} がどのタスクにも休憩にも含まれていません")

    # 6. 入力行（作業内容・ジョブ・売上項目の組み合わせごと）
    def row_key(task: TaskInput) -> RowKey:
        return (task.work_kind or "", task.job_code, task.sales_item_id or "")

    gap_key: RowKey = (
        settings.default_work_kind or "",
        settings.default_job_code or "",
        settings.default_sales_item_id or "",
    )

    def entry_fields(key: RowKey) -> dict[str, str]:
        work_kind, code, item_id = key
        job = jobs.get(code)
        item = items.get(item_id)
        return {
            "job_code": code,
            "zac_search_text": (job.zac_search_text if job and job.zac_search_text else code),
            "project_name": job.name if job else "",
            "work_kind": work_kind,
            "sales_item": item.name if item else "",
        }

    entries: list[ZacDraftEntry] = []
    if settings.entry_style == "time_range":
        rows: list[tuple[RowKey, str, datetime, datetime]] = [
            (row_key(piece.task), piece.task.description.strip(), piece.start, piece.end) for piece in clipped
        ]
        rows += [(gap_key, "", start, end) for start, end in gap_assign]
        rows.sort(key=lambda row: row[2])
        merged: list[tuple[RowKey, str, datetime, datetime]] = []
        for row in rows:
            if merged and merged[-1][0] == row[0] and merged[-1][1] == row[1] and merged[-1][3] == row[2]:
                merged[-1] = (row[0], row[1], merged[-1][2], row[3])
            else:
                merged.append(row)
        entries = [
            ZacDraftEntry(
                **entry_fields(key),
                minutes=minutes_between(start, end),
                description=join_descriptions([description], settings.description_max_length),
                start=fmt(start),
                end=fmt(end),
            )
            for key, description, start, end in merged
        ]
    else:
        minutes_by_row: dict[RowKey, int] = {}
        descriptions: dict[RowKey, list[str]] = {}
        for piece in clipped:
            key = row_key(piece.task)
            minutes_by_row[key] = minutes_by_row.get(key, 0) + minutes_between(piece.start, piece.end)
            descriptions.setdefault(key, []).append(piece.task.description)
        if gap_assign:
            minutes_by_row[gap_key] = minutes_by_row.get(gap_key, 0) + sum(
                minutes_between(*gap) for gap in gap_assign
            )
            descriptions.setdefault(gap_key, [])
        # 丸めずに合算する。空き時間・重なりなどのエラーがあると合計が実働と合わないが、その場合は参考値
        has_error = any(entry.severity == "error" for entry in issues)
        if sum(minutes_by_row.values()) != working_minutes and not has_error:
            issue("TOTAL_MISMATCH", "error", f"入力行の合計が実働 {working_minutes} 分と一致しません")
        entries = [
            ZacDraftEntry(
                **entry_fields(key),
                minutes=minutes,
                description=join_descriptions(descriptions[key], settings.description_max_length),
            )
            for key, minutes in minutes_by_row.items()
            if minutes > 0
        ]

    return finish(
        attendance_out=attendance_out,
        breaks_out=[ZacDraftBreak(start=fmt(start), end=fmt(end)) for start, end in break_union],
        working_minutes=working_minutes,
        entries=entries,
    )
