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

export function isPastWeekday(date: Date, today = new Date()): boolean {
  const day = date.getDay();
  const candidate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const current = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  return candidate < current && day >= 1 && day <= 5;
}
