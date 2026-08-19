import { describe, expect, it } from "vitest";

import {
  buildEndBodyCore,
  buildMailDraft,
  buildOutlookComposeUrl,
  getOutlookToRecipients,
  hasRequiredRecipients,
  OUTLOOK_WEB_COMPOSE_URL,
  renderTemplate,
} from "./mail";
import type { MailDraft, MailSettings, WorkReport } from "@/types";

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

  it("uses an override for end mail body core when provided", () => {
    const override = "本日の業務: 設計レビュー対応";
    const draft = buildMailDraft("end", settings, report, override);

    expect(draft.endBodyCore).toBe(override);
    expect(draft.body).toContain(override);
    expect(draft.body).toContain("お疲れ様です。本日、終業しました。");
    expect(draft.body).toContain("よろしくお願いいたします。");
    expect(draft.body).not.toContain("勤務時間: 9時間30分");
  });

  it("detects missing required recipients", () => {
    expect(hasRequiredRecipients(settings)).toBe(true);
    expect(hasRequiredRecipients({ boss_email: "", labor_ml_email: "labor@example.com" })).toBe(false);
  });
});
