# Proposal

## Why

zac に登録する出勤・退勤は人事の出退勤実績であり、laborman の打刻（ボタン押下時刻）とは別物である。現在は毎朝、人事から届く出退勤の履歴メール（Outlook on the web）を人が開いて確認している。この実績を laborman に自動で取り込み、zac 登録（`add-zac-draft-and-registration`）の入力にする。入力元仕様は `ZAC_AUTOMATION_SPEC.md` §4.5・§5.4・§7（Phase 2）。前提として `add-work-tasks-and-breaks` が実装済みであること。

## What Changes

- 勤務日ごとに出退勤実績（出勤・退勤・登録元 `hr_mail`/`manual`・区分 `work`/`leave`・取込日時）を、既存の打刻とは別の項目として保持する。休暇の日は人事メールが届かないため、区分 `leave` は UI の手入力でのみ登録する
- 出退勤実績の登録 API（`PUT /api/work-reports/{date}/attendance`）を追加する。手入力（`manual`）の値を人事メール（`hr_mail`）で上書きしようとした場合は `409`
- 「本日の報告」に出退勤（人事メール）の表示（未取込・取込日時）と手入力・上書きの UI を追加する
- 人事メールの検索条件（件名キーワード、任意の差出人）を設定に追加する。人事メールは 1 通 = 1 勤務日で、件名 `[勤怠情報]YYYY/MM/DD:開始HH:MM/終了HH:MM` から出退勤を取り込む（本文は予備。2026-10-13 に実メールで確認）
- 人事メールに休憩の記載がないため、休憩の取込は行わない（休憩は laborman の手入力のみ）
- テンプレート変数 `{{attendance_start}}`・`{{attendance_end}}` を追加する（未取込なら「未取込」）
- ホスト（macOS）上で動く CLI `laborman-agent` を新設する（`agent/`、uv workspace member）
  - `login owa`：画面付きブラウザで手動サインインし、プロファイルにセッションを保存
  - `fetch-attendance [--date D]`：OWA で対象日の人事メールを検索し、件名（だめなら本文）を解析して laborman API に登録
  - `doctor`：API・プロファイル・Playwright ブラウザ・設定の診断
  - 共通基盤：設定ファイル、API クライアント、前営業日の算出（祝日対応）、多重起動ロック、macOS 通知、終了コード、ログの期限削除

## Capabilities

### New Capabilities

- `attendance-import`: 出退勤実績の保持・手入力・人事メールからの取込（休暇日の手入力・`manual` 保護・メール未着/解析失敗の扱い）
- `laborman-agent`: ホスト側 CLI の共通動作（コマンド体系・終了コード・設定・前営業日・多重起動防止・通知・サインイン・診断・ローカルデータの扱い）

### Modified Capabilities

- `outlook-mail-compose`: 「メール件名・本文生成」に `{{attendance_start}}`・`{{attendance_end}}` を追加
- `report-calendar`: 「本日の報告画面」に出退勤（人事メール）の表示と手入力を追加
- `work-report-logging`: 「保存情報の範囲」に出退勤実績を追加し、メール本文・認証情報を保存しないことを明確化

## Impact

- **DB**：`work_reports` に `attendance_start_at`・`attendance_end_at`・`attendance_source`・`attendance_kind`・`attendance_imported_at` を追加。`automation_settings` に `hr_mail_from`・`hr_mail_subject_keyword` を追加
- **API**：`PUT /api/work-reports/{date}/attendance` を追加。`WorkReportRead`・`/api/automation-settings` を拡張
- **Frontend**：`TodayReport.tsx`（出退勤表示・手入力）、`SettingsPanel.tsx`（人事メール条件）、`lib/mail.ts`、`types.ts`・`lib/api.ts`
- **新規**：`agent/`（Python 3.12、`playwright`・`httpx`・`jpholiday`）。ルート `pyproject.toml` の workspace members に追加
- **ホスト環境**：`~/.config/laborman-agent/config.toml`、`~/Library/Application Support/laborman-agent/profiles/`、`~/Library/Logs/laborman-agent/`
- **前提（運用）**：OWA へのサインイン可否（§13-6）。人事メールの書式（§13-1）は確認済み
- **対象外**：休日出勤、半休の特別扱い、直行・直帰の移動時間（zac の画面確認後に Phase 3 で扱う）
- **Docs**：`docs/` 4 文書、`agent/README.md`
