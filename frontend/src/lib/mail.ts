import {
  formatDateForMail,
  formatDuration,
  formatHoursMinutes,
  formatTime,
  formatWorkTime,
  parseISODate,
  workMinutesBetween,
} from "@/lib/date";
import type {
  MailDraft,
  MailKind,
  MailSettings,
  WorkBreak,
  WorkDetails,
  WorkReport,
  WorkStyle,
  WorkTask,
} from "@/types";

export const NOTE_MAX_LENGTH = 600;

export type MailCreatedRequest = {
  kind: MailKind;
  end_mail_body?: string | null;
};

export const OUTLOOK_WEB_COMPOSE_URL = "https://outlook.office.com/mail/deeplink/compose";

export const workStyleLabels: Record<WorkStyle, string> = {
  office: "オフィス",
  remote: "リモート",
};

// 本日の曜日（0=日曜）から翌営業日の勤務区分を決める
const nextWorkStyleByWeekday: Record<number, WorkStyle> = {
  1: "remote",
  2: "office",
  3: "remote",
  4: "remote",
  5: "office",
};

export function nextWorkStyleLabel(date: Date): string {
  const workStyle = nextWorkStyleByWeekday[date.getDay()];
  return workStyle ? workStyleLabels[workStyle] : "";
}

export const statusLabels = {
  not_started: "未報告",
  start_recorded: "始業記録済み",
  start_mail_created: "始業メール作成済み",
  end_recorded: "終業記録済み",
  end_mail_created: "終業メール作成済み",
} as const;

export function parseEmailList(value: string): string[] {
  return value
    .split(/[,\n;]/)
    .map((email) => email.trim())
    .filter(Boolean);
}

export function hasRequiredRecipients(settings: Pick<MailSettings, "boss_email" | "labor_ml_email">): boolean {
  return Boolean(settings.boss_email.trim() && settings.labor_ml_email.trim());
}

function encodeRecipients(recipients: string[]): string {
  return recipients.map((email) => encodeURIComponent(email)).join(",");
}

export function getOutlookToRecipients(draft: Pick<MailDraft, "to" | "cc" | "bcc">): string[] {
  return [...draft.to, ...draft.cc, ...draft.bcc];
}

export function buildOutlookComposeUrl(draft: MailDraft): string {
  const outlookToRecipients = getOutlookToRecipients(draft);
  const query = [
    `to=${encodeRecipients(outlookToRecipients)}`,
    `subject=${encodeURIComponent(draft.subject)}`,
    `body=${encodeURIComponent(draft.body)}`,
  ];

  return `${OUTLOOK_WEB_COMPOSE_URL}?${query.join("&")}`;
}

export function renderTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/{{\s*([a-z_]+)\s*}}/g, (_, key: string) => values[key] ?? "");
}

export const EMPTY_WORK_DETAILS: WorkDetails = {
  tasks: [],
  breaks: [],
  jobs: [],
  salesItems: [],
  workKinds: [],
  zacDefaults: [],
};

type FinishedEntry<T extends WorkTask | WorkBreak> = T & { end_at: string };

// 進行中（終了時刻なし）のタスク・休憩は展開しない
function finishedByStart<T extends WorkTask | WorkBreak>(entries: T[]): FinishedEntry<T>[] {
  return entries
    .filter((entry): entry is FinishedEntry<T> => entry.end_at !== null)
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());
}

function timeRange(workDate: string, entry: { start_at: string; end_at: string }): string {
  return `${formatWorkTime(workDate, entry.start_at)} - ${formatWorkTime(workDate, entry.end_at)}`;
}

export const BREAK_LINE_LABEL = "休憩";

// タスクと休憩を開始時刻順に混ぜて 1 行ずつ並べる（終業メールの {{tasks}} と業務明細プレビュー）
export function buildTasksText(workDate: string, tasks: WorkTask[], breaks: WorkBreak[] = []): string {
  const lines: { startAt: string; text: string }[] = [
    ...finishedByStart(tasks).map((task) => ({
      startAt: task.start_at,
      text: `${timeRange(workDate, task)} ${task.job_code} ${task.description}`.trimEnd(),
    })),
    ...finishedByStart(breaks).map((item) => ({
      startAt: item.start_at,
      text: `${timeRange(workDate, item)} ${BREAK_LINE_LABEL}`,
    })),
  ];
  return lines
    .sort((a, b) => new Date(a.startAt).getTime() - new Date(b.startAt).getTime())
    .map((line) => line.text)
    .join("\n");
}

function buildTasksByJobText(details: WorkDetails): string {
  const minutesByJob = new Map<string, number>();
  for (const task of finishedByStart(details.tasks)) {
    const minutes = workMinutesBetween(task.start_at, task.end_at);
    minutesByJob.set(task.job_code, (minutesByJob.get(task.job_code) ?? 0) + minutes);
  }
  const names = new Map(details.jobs.map((job) => [job.code, job.name]));
  return [...minutesByJob.entries()]
    .map(([code, minutes]) => [code, names.get(code), formatHoursMinutes(minutes)].filter(Boolean).join(" "))
    .join("\n");
}

function buildBreaksText(workDate: string, breaks: WorkBreak[]): string {
  return finishedByStart(breaks)
    .map((item) => timeRange(workDate, item))
    .join("\n");
}

function buildTaskTotalText(tasks: WorkTask[]): string {
  const finished = finishedByStart(tasks);
  if (finished.length === 0) return "";
  const total = finished.reduce((sum, task) => sum + workMinutesBetween(task.start_at, task.end_at), 0);
  return formatDuration(total);
}

export const ATTENDANCE_NOT_IMPORTED = "未取込";

function attendanceTime(workDate: string, value: string | null): string {
  return value ? formatWorkTime(workDate, value) : ATTENDANCE_NOT_IMPORTED;
}

function templateValues(report: WorkReport, details: WorkDetails): Record<string, string> {
  const workDate = parseISODate(report.work_date);
  return {
    date: formatDateForMail(workDate),
    start_time: formatTime(report.start_time),
    end_time: formatTime(report.end_time),
    work_duration: formatDuration(report.work_duration_minutes),
    work_style: workStyleLabels[report.work_style],
    next_work_style: nextWorkStyleLabel(workDate),
    note: report.note || "",
    tasks: buildTasksText(report.work_date, details.tasks, details.breaks),
    tasks_by_job: buildTasksByJobText(details),
    breaks: buildBreaksText(report.work_date, details.breaks),
    task_total: buildTaskTotalText(details.tasks),
    attendance_start: attendanceTime(report.work_date, report.attendance_start_at),
    attendance_end: attendanceTime(report.work_date, report.attendance_end_at),
  };
}

function joinMailSections(...sections: string[]): string {
  return sections
    .map((section) => section.trim())
    .filter(Boolean)
    .join("\n\n");
}

export function buildEndBodyCore(
  settings: MailSettings,
  report: WorkReport,
  details: WorkDetails = EMPTY_WORK_DETAILS,
): string {
  return renderTemplate(settings.end_body_template, templateValues(report, details));
}

export function buildMailDraft(
  kind: MailKind,
  settings: MailSettings,
  report: WorkReport,
  details: WorkDetails = EMPTY_WORK_DETAILS,
): MailDraft {
  const values = templateValues(report, details);
  const to = parseEmailList(settings.boss_email);
  const cc = parseEmailList(settings.labor_ml_email);
  const bcc: string[] = [];

  if (kind === "start") {
    return {
      kind,
      to,
      cc,
      bcc,
      subject: renderTemplate(settings.start_subject_template, values),
      body: renderTemplate(settings.start_body_template, values),
    };
  }

  const header = renderTemplate(settings.end_header_template, values);
  const endBodyCore = buildEndBodyCore(settings, report, details);
  const footer = renderTemplate(settings.end_footer_template, values);

  return {
    kind,
    to,
    cc,
    bcc,
    subject: renderTemplate(settings.end_subject_template, values),
    body: joinMailSections(header, endBodyCore, footer),
    endBodyCore,
  };
}
