import { formatDateForMail, formatDuration, formatTime, parseISODate } from "@/lib/date";
import type { MailDraft, MailKind, MailSettings, WorkReport, WorkStyle } from "@/types";

export const NOTE_MAX_LENGTH = 600;

export type MailCreatedRequest = {
  kind: MailKind;
  end_mail_body?: string | null;
};

export type MailtoParams = {
  to: string[];
  cc?: string[];
  bcc?: string[];
  subject: string;
  body: string;
};

export const workStyleLabels: Record<WorkStyle, string> = {
  office: "オフィス",
  remote: "リモート",
};

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

export function buildMailtoUrl(params: MailtoParams): string {
  const to = params.to.map((email) => encodeURIComponent(email)).join(",");
  const query: string[] = [];

  if (params.cc && params.cc.length > 0) {
    query.push(`cc=${params.cc.map((email) => encodeURIComponent(email)).join(",")}`);
  }

  if (params.bcc && params.bcc.length > 0) {
    query.push(`bcc=${params.bcc.map((email) => encodeURIComponent(email)).join(",")}`);
  }

  query.push(`subject=${encodeURIComponent(params.subject)}`);
  query.push(`body=${encodeURIComponent(params.body)}`);

  return `mailto:${to}?${query.join("&")}`;
}

export function renderTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/{{\s*([a-z_]+)\s*}}/g, (_, key: string) => values[key] ?? "");
}

function templateValues(report: WorkReport): Record<string, string> {
  const workDate = parseISODate(report.work_date);
  return {
    date: formatDateForMail(workDate),
    start_time: formatTime(report.start_time),
    end_time: formatTime(report.end_time),
    work_duration: formatDuration(report.work_duration_minutes),
    work_style: workStyleLabels[report.work_style],
    note: report.note || "",
  };
}

function joinMailSections(...sections: string[]): string {
  return sections
    .map((section) => section.trim())
    .filter(Boolean)
    .join("\n\n");
}

export function buildEndBodyCore(settings: MailSettings, report: WorkReport): string {
  return renderTemplate(settings.end_body_template, templateValues(report));
}

export function buildMailDraft(
  kind: MailKind,
  settings: MailSettings,
  report: WorkReport,
  endBodyCoreOverride?: string | null,
): MailDraft {
  const values = templateValues(report);
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
  const endBodyCore = endBodyCoreOverride ?? buildEndBodyCore(settings, report);
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
