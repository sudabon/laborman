export type WorkStyle = "office" | "remote";
export type ReportStatus =
  | "not_started"
  | "start_recorded"
  | "start_mail_created"
  | "end_recorded"
  | "end_mail_created";
export type MailKind = "start" | "end";
export type AttendanceSource = "hr_mail" | "manual";
export type ZacStatus = "registered" | "needs_action";
export type ZacSubmitMode = "dry_run" | "assist" | "auto";
export type EntryStyle = "duration" | "time_range";
export type GapPolicy = "block" | "assign_default_job";
export type ZacRunStatus =
  | "requested"
  | "cancelled"
  | "running"
  | "succeeded"
  | "dry_run_done"
  | "awaiting_user"
  | "validation_failed"
  | "needs_login"
  | "vpn_unreachable"
  | "hr_mail_not_found"
  | "already_registered_in_zac"
  | "failed";
export type AttendanceKind = "work" | "leave";

export type MailSettings = {
  id: string;
  boss_email: string;
  labor_ml_email: string;
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
  attendance_start_at: string | null;
  attendance_end_at: string | null;
  attendance_source: AttendanceSource | null;
  attendance_kind: AttendanceKind;
  attendance_imported_at: string | null;
  zac_registered_at: string | null;
  zac_status: ZacStatus | null;
  created_at: string | null;
  updated_at: string | null;
  status: ReportStatus;
  work_duration_minutes: number | null;
};

export type AttendanceInput = {
  start_at: string | null;
  end_at: string | null;
  source: AttendanceSource;
  kind: AttendanceKind;
};

export type WorkReportUpdate = {
  note?: string;
  work_style?: WorkStyle;
  end_mail_body?: string | null;
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

export type Job = {
  code: string;
  name: string;
  zac_search_text: string;
  // zac の作業登録で使う既定の作業内容
  zac_work_category: string;
  // 月ごとに JOB 番号が変わる案件のシリーズ名と対象年月（YYYY-MM）
  series_name: string | null;
  valid_month: string | null;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type JobCreate = {
  code: string;
  name: string;
  zac_search_text?: string;
  zac_work_category?: string;
};

export type JobCodeChange = {
  code: string;
  name?: string;
  zac_search_text?: string;
  zac_work_category?: string;
};

export type JobUpdate = {
  name?: string;
  zac_search_text?: string;
  zac_work_category?: string;
  series_name?: string | null;
  valid_month?: string | null;
  is_active?: boolean;
};

export type WorkTask = {
  id: string;
  work_report_id: string;
  job_code: string;
  description: string;
  work_kind: string | null;
  sales_item_id: string | null;
  start_at: string;
  end_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkTaskInput = {
  job_code: string;
  description: string;
  work_kind?: string | null;
  sales_item_id?: string | null;
  start_at: string;
  end_at: string | null;
};

export type BreakSource = "manual" | "hr_mail";

export type WorkBreak = {
  id: string;
  work_report_id: string;
  start_at: string;
  end_at: string | null;
  source: BreakSource;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkBreakInput = {
  start_at: string;
  end_at: string | null;
};

export type AutomationSettings = {
  id: string;
  default_break_start: string;
  default_break_end: string;
  hr_mail_from: string;
  hr_mail_subject_keyword: string;
  zac_submit_mode: ZacSubmitMode;
  entry_style: EntryStyle;
  time_unit_minutes: number;
  clip_tolerance_minutes: number;
  gap_policy: GapPolicy;
  default_job_code: string | null;
  default_work_kind: string | null;
  default_sales_item_id: string | null;
  description_max_length: number;
  created_at: string | null;
  updated_at: string | null;
};

export type AutomationSettingsInput = Omit<AutomationSettings, "id" | "created_at" | "updated_at">;

export type EntryConflict = {
  kind: "task" | "break";
  id: string;
  start_at: string;
  end_at: string | null;
};

// 終業メールの業務明細変数（{{tasks}} など）の展開に使う当日のデータ
export type ZacWorkKind = {
  name: string;
  is_active: boolean;
  sort_order: number;
};

export type ZacSalesItem = {
  id: string;
  job_code: string;
  name: string;
  valid_month: string | null;
  is_closed: boolean;
  is_active: boolean;
  sort_order: number;
};

// ジョブごとに直近のタスクで使った作業内容・売上項目
export type ZacTaskDefault = {
  job_code: string;
  work_kind: string | null;
  sales_item_id: string | null;
};

export type WorkDetails = {
  tasks: WorkTask[];
  breaks: WorkBreak[];
  jobs: Job[];
  salesItems: ZacSalesItem[];
  workKinds: ZacWorkKind[];
  zacDefaults: ZacTaskDefault[];
};

export type ZacDraftIssue = {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  ref_id: string | null;
};

export type ZacDraftEntry = {
  job_code: string;
  zac_search_text: string;
  project_name: string;
  work_kind: string;
  sales_item: string;
  minutes: number;
  description: string;
  start: string | null;
  end: string | null;
};

// GET /api/work-reports/{date}/zac-draft（時刻は勤務日基準の HH:MM）
export type ZacDraft = {
  work_date: string;
  attendance: { start: string; end: string; source: string | null } | null;
  breaks: { start: string; end: string }[];
  working_minutes: number | null;
  entry_style: EntryStyle;
  entries: ZacDraftEntry[];
  issues: ZacDraftIssue[];
  registrable: boolean;
  auto_allowed: boolean;
  zac_registered_at: string | null;
};

export type ZacSyncRun = {
  id: string;
  work_date: string;
  mode: ZacSubmitMode;
  status: ZacRunStatus;
  entries: unknown;
  message: string | null;
  screenshot_path: string | null;
  agent_version: string | null;
  started_at: string;
  finished_at: string | null;
};
