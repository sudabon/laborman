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
  const query = new URLSearchParams();

  if (params.cc && params.cc.length > 0) {
    query.set("cc", params.cc.join(","));
  }

  if (params.bcc && params.bcc.length > 0) {
    query.set("bcc", params.bcc.join(","));
  }

  query.set("subject", params.subject);
  query.set("body", params.body);

  return `mailto:${to}?${query.toString()}`;
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

export function buildMailDraft(kind: MailKind, settings: MailSettings, report: WorkReport): MailDraft {
  const values = templateValues(report);
  const to = parseEmailList(`${settings.boss_email},${settings.labor_ml_email}`);
  const cc = parseEmailList(settings.cc_emails);
  const bcc = parseEmailList(settings.bcc_emails);

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
  const endBodyCore = renderTemplate(settings.end_body_template, values);
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
