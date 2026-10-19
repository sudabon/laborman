export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatDateForDisplay(date: Date): string {
  return new Intl.DateTimeFormat("ja-JP", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

export function formatDateForMail(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}/${month}/${day}`;
}

export function parseISODate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function formatTime(value: string | null): string {
  if (!value) return "未記録";
  return new Intl.DateTimeFormat("ja-JP", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDuration(minutes: number | null): string {
  if (minutes === null) return "不明";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours}時間${String(rest).padStart(2, "0")}分`;
}

export function isSameDate(a: Date, b: Date): boolean {
  return toISODate(a) === toISODate(b);
}

const calendarWeekdayHeaderLabels = ["", "月", "火", "水", "木", "金", ""] as const;

export function formatCalendarWeekdayHeader(weekday: Date): string {
  return calendarWeekdayHeaderLabels[weekday.getDay()] ?? "";
}

export function isReportingWeekday(date: Date): boolean {
  const day = date.getDay();
  return day >= 1 && day <= 5;
}

export function isPastWeekday(date: Date, today = new Date()): boolean {
  if (!isReportingWeekday(date)) return false;
  const candidate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const current = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  return candidate < current;
}

// 勤務日の境界（00:00〜翌 06:00）を判定するタイムゾーン。backend の app_timezone と同じ値
export const APP_TIME_ZONE = "Asia/Tokyo";
// 24:00〜29:59 を勤務日の翌日の時刻として受け付ける
const WORK_TIME_MAX_HOURS = 30;
const WORK_TIME_PATTERN = /^(\d{1,2}):([0-5]\d)$/;
const MINUTE_MS = 60_000;
const DAY_MS = 24 * 60 * MINUTE_MS;

type ZonedParts = { year: number; month: number; day: number; hour: number; minute: number };

function zonedParts(epochMs: number, timeZone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(new Date(epochMs));
  const value = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
  return { year: value("year"), month: value("month"), day: value("day"), hour: value("hour"), minute: value("minute") };
}

function timeZoneOffsetMs(epochMs: number, timeZone: string): number {
  const { year, month, day, hour, minute } = zonedParts(epochMs, timeZone);
  const truncated = Math.floor(epochMs / MINUTE_MS) * MINUTE_MS;
  return Date.UTC(year, month - 1, day, hour, minute) - truncated;
}

/** 勤務日基準の "HH:MM"（24:00〜29:59 は翌日）を ISO 8601（UTC）に変換する。不正な値は例外。 */
export function parseWorkTime(workDate: string, value: string, timeZone = APP_TIME_ZONE): string {
  const match = WORK_TIME_PATTERN.exec(value.trim());
  if (!match) {
    throw new Error("時刻は HH:MM 形式で入力してください");
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours >= WORK_TIME_MAX_HOURS) {
    throw new Error("時刻は 29:59 までで入力してください");
  }
  const [year, month, day] = workDate.split("-").map(Number);
  const wallClockMs = Date.UTC(year, month - 1, day, hours, minutes);
  let epochMs = wallClockMs - timeZoneOffsetMs(wallClockMs, timeZone);
  // 夏時間の切り替えをまたぐ場合に備えて、求めた時刻のオフセットで補正する
  epochMs = wallClockMs - timeZoneOffsetMs(epochMs, timeZone);
  return new Date(epochMs).toISOString();
}

/** ISO 8601 の時刻を勤務日基準の "HH:MM" で表す（翌日は 24:00〜）。 */
export function formatWorkTime(workDate: string, iso: string, timeZone = APP_TIME_ZONE): string {
  const { year, month, day, hour, minute } = zonedParts(new Date(iso).getTime(), timeZone);
  const [workYear, workMonth, workDay] = workDate.split("-").map(Number);
  const dayOffset = Math.round((Date.UTC(year, month - 1, day) - Date.UTC(workYear, workMonth - 1, workDay)) / DAY_MS);
  const hours = hour + dayOffset * 24;
  return `${String(hours).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** 表示上の HH:MM と一致するよう、秒を切り捨てた分単位の差を返す。 */
export function workMinutesBetween(startIso: string, endIso: string): number {
  const start = Math.floor(new Date(startIso).getTime() / MINUTE_MS);
  const end = Math.floor(new Date(endIso).getTime() / MINUTE_MS);
  return Math.max(0, end - start);
}

/** 分を "H:MM" で表す。 */
export function formatHoursMinutes(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

/** 日時を「M/D HH:MM」（APP_TIME_ZONE）で表す。 */
export function formatShortDateTime(iso: string): string {
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: APP_TIME_ZONE,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

