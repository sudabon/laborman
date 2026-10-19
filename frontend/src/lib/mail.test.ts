import { describe, expect, it } from "vitest";

import {
  buildEndBodyCore,
  buildMailDraft,
  buildOutlookComposeUrl,
  getOutlookToRecipients,
  hasRequiredRecipients,
  nextWorkStyleLabel,
  OUTLOOK_WEB_COMPOSE_URL,
  renderTemplate,
} from "./mail";
import type { Job, MailDraft, MailSettings, WorkBreak, WorkDetails, WorkReport, WorkTask } from "@/types";

const settings: MailSettings = {
  id: "default",
  boss_email: "boss@example.com",
  labor_ml_email: "labor@example.com",
  start_subject_template: "【始業報告】{{date}}",
  start_body_template: "始業 {{start_time}} {{work_style}} {{note}}",
  end_subject_template: "【終業報告】{{date}}",
  end_header_template: "お疲れ様です。本日、終業しました。",
  end_body_template: "勤務時間: {{work_duration}}\n勤務区分: {{work_style}}\nメモ: {{note}}",
  end_footer_template: "よろしくお願いいたします。",
  created_at: null,
  updated_at: null,
};

const report: WorkReport = {
  id: "report-1",
  work_date: "2026-06-06",
  start_time: "2026-06-06T00:00:00Z",
  end_time: "2026-06-06T09:30:00Z",
  start_mail_created_at: null,
  end_mail_created_at: null,
  note: "レビュー対応",
  work_style: "remote",
  end_mail_body: null,
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
  work_duration_minutes: 570,
};

describe("mail utilities", () => {
  it("merges multiple to, cc, and bcc recipients into the Outlook to parameter", () => {
    const draft: MailDraft = {
      kind: "start",
      to: ["boss@example.com", "manager@example.com"],
      cc: ["team-one@example.com", "team-two@example.com"],
      bcc: ["audit-one@example.com", "audit-two@example.com"],
      subject: "Daily report",
      body: "Done",
    };
    const url = buildOutlookComposeUrl(draft);

    expect(url).toBe(
      `${OUTLOOK_WEB_COMPOSE_URL}?to=boss%40example.com,manager%40example.com` +
        ",team-one%40example.com,team-two%40example.com" +
        ",audit-one%40example.com,audit-two%40example.com" +
        "&subject=Daily%20report&body=Done",
    );
    expect(getOutlookToRecipients(draft)).toEqual([
      "boss@example.com",
      "manager@example.com",
      "team-one@example.com",
      "team-two@example.com",
      "audit-one@example.com",
      "audit-two@example.com",
    ]);
    expect(url).not.toContain("%2C");
    expect(url).not.toContain("&cc=");
    expect(url).not.toContain("&bcc=");
  });

  it("preserves empty subject and body parameters without adding cc or bcc parameters", () => {
    const url = buildOutlookComposeUrl({
      kind: "start",
      to: ["boss@example.com"],
      cc: [],
      bcc: [],
      subject: "",
      body: "",
    });

    expect(url).toBe(`${OUTLOOK_WEB_COMPOSE_URL}?to=boss%40example.com&subject=&body=`);
    expect(url).not.toContain("&cc=");
    expect(url).not.toContain("&bcc=");
  });

  it("percent-encodes Japanese, newlines, spaces, and literal plus signs without using +", () => {
    const url = buildOutlookComposeUrl({
      kind: "end",
      to: ["boss@example.com"],
      cc: [],
      bcc: [],
      subject: "終業 報告 + 確認",
      body: "勤務時間: 9時間30分\n勤務区分: リモート",
    });

    expect(url).toContain(
      "subject=%E7%B5%82%E6%A5%AD%20%E5%A0%B1%E5%91%8A%20%2B%20%E7%A2%BA%E8%AA%8D",
    );
    expect(url).toContain("%E5%8B%A4%E5%8B%99%E6%99%82%E9%96%93%3A%209%E6%99%82%E9%96%9330%E5%88%86");
    expect(url).toContain("%0A");
    expect(url).toContain("%2B");
    expect(url).not.toContain("+");
  });

  it("replaces template variables and expands work style labels", () => {
    expect(renderTemplate("{{date}} {{work_style}}", { date: "2026/06/06", work_style: "リモート" })).toBe(
      "2026/06/06 リモート",
    );

    const draft = buildMailDraft("start", settings, report);
    expect(draft.subject).toBe("【始業報告】2026/06/06");
    expect(draft.body).toContain("リモート");
  });

  it("maps boss to to and labor ml to cc", () => {
    const draft = buildMailDraft("start", settings, report);

    expect(draft.to).toEqual(["boss@example.com"]);
    expect(draft.cc).toEqual(["labor@example.com"]);
    expect(draft.bcc).toEqual([]);
  });

  it("builds end body core from the end body template", () => {
    expect(buildEndBodyCore(settings, report)).toBe(
      "勤務時間: 9時間30分\n勤務区分: リモート\nメモ: レビュー対応",
    );
  });

  it("builds end mail from header, body core, and footer while exposing body core for persistence", () => {
    const draft = buildMailDraft("end", settings, report);

    expect(draft.body).toContain("お疲れ様です。本日、終業しました。");
    expect(draft.body).toContain("勤務区分: リモート");
    expect(draft.body).toContain("よろしくお願いいたします。");
    expect(draft.endBodyCore).toBe("勤務時間: 9時間30分\n勤務区分: リモート\nメモ: レビュー対応");
  });


  it("picks next work style from the weekday of the report date", () => {
    // 2026-10-05 は月曜日
    expect(nextWorkStyleLabel(new Date(2026, 9, 5))).toBe("リモート");
    expect(nextWorkStyleLabel(new Date(2026, 9, 6))).toBe("オフィス");
    expect(nextWorkStyleLabel(new Date(2026, 9, 7))).toBe("リモート");
    expect(nextWorkStyleLabel(new Date(2026, 9, 8))).toBe("リモート");
    expect(nextWorkStyleLabel(new Date(2026, 9, 9))).toBe("オフィス");
    expect(nextWorkStyleLabel(new Date(2026, 9, 10))).toBe("");
  });

  it("expands next_work_style in end mail templates", () => {
    const tuesdayReport = { ...report, work_date: "2026-10-06" };
    const draft = buildMailDraft(
      "end",
      { ...settings, end_footer_template: "翌営業日は{{next_work_style}}にて作業予定です。" },
      tuesdayReport,
    );

    expect(draft.body).toContain("翌営業日はオフィスにて作業予定です。");
  });

  it("detects missing required recipients", () => {
    expect(hasRequiredRecipients(settings)).toBe(true);
    expect(hasRequiredRecipients({ boss_email: "", labor_ml_email: "labor@example.com" })).toBe(false);
  });
});

function task(id: string, jobCode: string, description: string, start: string, end: string | null): WorkTask {
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

function workBreak(id: string, start: string, end: string | null): WorkBreak {
  return { id, work_report_id: "report-1", start_at: start, end_at: end, source: "manual", created_at: null, updated_at: null };
}

function job(code: string, name: string): Job {
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

const jst = (hhmm: string, day = "2026-10-09") => `${day}T${hhmm}:00+09:00`;
const detailReport: WorkReport = { ...report, work_date: "2026-10-09" };

describe("work detail template variables", () => {
  const details: WorkDetails = {
    tasks: [
      task("t2", "JOB-B", "定例MTG", jst("10:30"), jst("12:00")),
      task("t1", "JOB-A", "設計レビュー", jst("09:00"), jst("10:30")),
      task("t3", "JOB-A", "障害調査", jst("13:00"), jst("14:45")),
      task("t4", "JOB-A", "進行中の作業", jst("14:45"), null),
    ],
    breaks: [workBreak("b1", jst("12:00"), jst("13:00")), workBreak("b2", jst("15:00"), null)],
    jobs: [job("JOB-A", "A社保守"), job("JOB-B", "社内業務")],
    salesItems: [], workKinds: [], zacDefaults: [],
  };
  const withTemplate = (template: string) => ({ ...settings, end_body_template: template });

  it("expands {{tasks}} with breaks in start order and skips running entries", () => {
    expect(buildEndBodyCore(withTemplate("{{tasks}}"), detailReport, details)).toBe(
      "09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩\n13:00 - 14:45 JOB-A 障害調査",
    );
  });

  it("expands {{tasks_by_job}} and {{task_total}}", () => {
    const body = buildEndBodyCore(withTemplate("{{tasks_by_job}}\n合計 {{task_total}}"), detailReport, details);
    expect(body).toBe("JOB-A A社保守 3:15\nJOB-B 社内業務 1:30\n合計 4時間45分");
  });

  it("expands {{breaks}} and skips running breaks", () => {
    expect(buildEndBodyCore(withTemplate("{{breaks}}"), detailReport, details)).toBe("12:00 - 13:00");
  });

  it("uses work-day based times after midnight", () => {
    const lateDetails: WorkDetails = {
      tasks: [task("t1", "JOB-A", "リリース作業", jst("23:30"), jst("01:15", "2026-10-10"))],
      breaks: [],
      jobs: [],
      salesItems: [], workKinds: [], zacDefaults: [],
    };
    expect(buildEndBodyCore(withTemplate("{{tasks}}|{{tasks_by_job}}"), detailReport, lateDetails)).toBe(
      "23:30 - 25:15 JOB-A リリース作業|JOB-A 1:45",
    );
  });

  it("omits the trailing space when description is empty", () => {
    const emptyDescription: WorkDetails = {
      tasks: [task("t1", "JOB-A", "", jst("09:00"), jst("10:00"))],
      breaks: [],
      jobs: [],
      salesItems: [], workKinds: [], zacDefaults: [],
    };
    expect(buildEndBodyCore(withTemplate("{{tasks}}"), detailReport, emptyDescription)).toBe("09:00 - 10:00 JOB-A");
  });

  it("expands to empty strings when there are no tasks or breaks", () => {
    const template = "[{{tasks}}][{{tasks_by_job}}][{{breaks}}][{{task_total}}]";
    expect(buildEndBodyCore(withTemplate(template), detailReport)).toBe("[][][][]");
    expect(buildEndBodyCore(withTemplate(template), detailReport, { tasks: [], breaks: [], jobs: [], salesItems: [], workKinds: [], zacDefaults: [] })).toBe(
      "[][][][]",
    );
  });

  it("keeps existing variables working alongside work details in the end mail", () => {
    const draft = buildMailDraft(
      "end",
      withTemplate("勤務時間: {{work_duration}}\n勤務区分: {{work_style}}\nメモ: {{note}}\n業務明細:\n{{tasks}}"),
      detailReport,
      details,
    );

    expect(draft.endBodyCore).toBe(
      "勤務時間: 9時間30分\n勤務区分: リモート\nメモ: レビュー対応\n業務明細:\n" +
        "09:00 - 10:30 JOB-A 設計レビュー\n10:30 - 12:00 JOB-B 定例MTG\n12:00 - 13:00 休憩\n13:00 - 14:45 JOB-A 障害調査",
    );
    expect(draft.body).toContain("お疲れ様です。本日、終業しました。");
    expect(draft.body).toContain(draft.endBodyCore);
    expect(draft.subject).toBe("【終業報告】2026/10/09");
  });
});

describe("attendance template variables", () => {
  const template = "出勤: {{attendance_start}} / 退勤: {{attendance_end}}";
  const withTemplate = { ...settings, end_body_template: template };

  it("expands registered attendance times", () => {
    const attended: WorkReport = {
      ...detailReport,
      attendance_start_at: jst("09:02"),
      attendance_end_at: jst("18:41"),
      attendance_source: "hr_mail",
    };
    expect(buildEndBodyCore(withTemplate, attended)).toBe("出勤: 09:02 / 退勤: 18:41");
  });

  it("uses work-day based times after midnight", () => {
    const lateNight: WorkReport = {
      ...detailReport,
      attendance_start_at: jst("09:00"),
      attendance_end_at: jst("01:15", "2026-10-10"),
      attendance_source: "manual",
    };
    expect(buildEndBodyCore(withTemplate, lateNight)).toBe("出勤: 09:00 / 退勤: 25:15");
  });

  it("expands to 未取込 when attendance is not registered", () => {
    expect(buildEndBodyCore(withTemplate, detailReport)).toBe("出勤: 未取込 / 退勤: 未取込");
    const draft = buildMailDraft("start", { ...settings, start_body_template: template }, detailReport);
    expect(draft.body).toBe("出勤: 未取込 / 退勤: 未取込");
  });
});
