export type WorkStyle = "office" | "remote";
export type ReportStatus =
  | "not_started"
  | "start_recorded"
  | "start_mail_created"
  | "end_recorded"
  | "end_mail_created";
export type MailKind = "start" | "end";

export type MailSettings = {
  id: string;
  boss_email: string;
  labor_ml_email: string;
  cc_emails: string;
  bcc_emails: string;
  start_subject_template: string;
  start_body_template: string;
  end_subject_template: string;
  end_header_template: string;
  end_body_template: string;
  end_footer_template: string;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkReport = {
  id: string;
  work_date: string;
  start_time: string | null;
  end_time: string | null;
  start_mail_created_at: string | null;
  end_mail_created_at: string | null;
  note: string;
  work_style: WorkStyle;
  end_mail_body: string | null;
  created_at: string | null;
  updated_at: string | null;
  status: ReportStatus;
  work_duration_minutes: number | null;
};

export type WorkReportUpdate = {
  note?: string;
  work_style?: WorkStyle;
};

export type MailDraft = {
  kind: MailKind;
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body: string;
  endBodyCore?: string;
};
