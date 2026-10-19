import type { AutomationSettings, Job, MailSettings, WorkBreak, WorkReport, WorkTask } from "@/types";

export const WORK_DATE = "2026-10-09";
export const jst = (hhmm: string, day = WORK_DATE) => `${day}T${hhmm}:00+09:00`;

export const mailSettings: MailSettings = {
  id: "default",
  boss_email: "boss@example.com",
  labor_ml_email: "labor@example.com",
  start_subject_template: "【始業報告】{{date}}",
  start_body_template: "始業 {{start_time}}",
  end_subject_template: "【終業報告】{{date}}",
  end_header_template: "お疲れ様です。",
  end_body_template: "勤務区分: {{work_style}}\n業務明細:\n{{tasks}}",
  end_footer_template: "よろしくお願いいたします。",
  created_at: null,
  updated_at: null,
};

export const endRecordedReport: WorkReport = {
  id: "report-1",
  work_date: WORK_DATE,
  start_time: jst("09:00"),
  end_time: jst("18:00"),
  start_mail_created_at: jst("09:05"),
  end_mail_created_at: null,
  note: "",
  work_style: "remote",
  end_mail_body: "以前の自由記述",
  attendance_start_at: null,
  attendance_end_at: null,
  attendance_source: null,
  attendance_kind: "work",
  attendance_imported_at: null,
  zac_registered_at: null,
  zac_status: null,
  created_at: null,
  updated_at: null,
  status: "end_recorded",
  work_duration_minutes: 540,
};

export function makeTask(id: string, jobCode: string, description: string, start: string, end: string | null): WorkTask {
  return {
    id,
    work_report_id: "report-1",
    job_code: jobCode,
    description,
    work_kind: null,
    sales_item_id: null,
    start_at: start,
    end_at: end,
    created_at: null,
    updated_at: null,
  };
}

export function makeBreak(id: string, start: string, end: string | null): WorkBreak {
  return { id, work_report_id: "report-1", start_at: start, end_at: end, source: "manual", created_at: null, updated_at: null };
}

export function makeJob(code: string, name: string): Job {
  return {
    code,
    name,
    zac_search_text: "",
    zac_work_category: "",
    series_name: null,
    valid_month: null,
    is_active: true,
    last_used_at: null,
    created_at: null,
    updated_at: null,
  };
}

export const automationSettings: AutomationSettings = {
  id: "default",
  default_break_start: "12:00",
  default_break_end: "13:00",
  hr_mail_from: "",
  hr_mail_subject_keyword: "",
  zac_submit_mode: "dry_run",
  entry_style: "duration",
  time_unit_minutes: 15,
  clip_tolerance_minutes: 15,
  gap_policy: "block",
  default_job_code: null,
  default_work_kind: null,
  default_sales_item_id: null,
  description_max_length: 100,
  created_at: null,
  updated_at: null,
};

