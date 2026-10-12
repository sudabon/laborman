# Proposal

## Why

業務内容（ジョブ ID・作業時間）は「業務報告」テキストエリアの自由記述でしか残っておらず、zac への登録時に毎朝人が読み解いて転記している。後続の出退勤取込（`add-attendance-import`）と zac 自動登録（`add-zac-draft-and-registration`）の土台として、タスクと休憩を 1 件ずつのレコードで記録できるようにする。入力元仕様は `ZAC_AUTOMATION_SPEC.md` §4.1〜4.4・§5.1〜5.3・§8（Phase 1）。

## What Changes

- 勤務日ごとのタスク（ジョブ ID・内容・開始・終了）を記録する。「タスク開始」で進行中タスクを自動終了してから新しいタスクを開始し、進行中は 1 日 1 件に制限する
- 勤務日ごとの休憩（開始・終了）を記録する。「休憩開始」で進行中タスクを終了し、「休憩終了」後に直前のタスクを「再開」できる
- タスク同士・タスクと休憩の時間帯の重なりを保存時に拒否する（`409`、相手のレコードを返す）
- 過去日のタスク・休憩を `HH:MM` で手入力・編集・削除できる。`24:00`〜`29:59` は翌日の時刻として扱う
- ジョブマスタ（ジョブ ID・表示名・zac 検索文字列・作業分類・有効/無効）を追加し、最近使った順＋インクリメンタル検索で選べるようにする。未登録のジョブ ID はその場で登録できる
- 既定の休憩（例：12:00–13:00）を設定に持ち、「既定の休憩を追加」で 1 クリック登録できる
- 終業メールのテンプレート変数に `{{tasks}}`・`{{tasks_by_job}}`・`{{breaks}}`・`{{task_total}}` を追加する。既定テンプレートにのみ `{{tasks}}` を加え、既存の設定行は書き換えない
- **BREAKING（UI）**：「本日の報告」の自由記述「業務報告」テキストエリアを廃止し、`{{tasks}}` のプレビュー（読み取り専用・コピー可）に置き換える。補足文は既存の「メモ」を使う
- 「終業を記録」時に進行中のタスク・休憩があれば、終業時刻で終了するか確認する
- `docker-compose.yml` の backend ポートを `127.0.0.1:8888` に限定する（LAN から到達させない）
- backend に `app_timezone`（既定 `Asia/Tokyo`）を追加し、勤務日の境界判定に使う

## Capabilities

### New Capabilities

- `work-task-logging`: 勤務日ごとのタスクの記録・開始/停止・手入力編集・重なり防止・勤務日基準の時刻入力
- `break-logging`: 勤務日ごとの休憩の記録・開始/終了・タスク再開・既定休憩の設定と追加
- `job-master`: ジョブ ID と zac 対応情報の管理、タスク入力時の候補提示・その場登録・無効化

### Modified Capabilities

- `outlook-mail-compose`: 「メール件名・本文生成」にタスク・休憩由来のテンプレート変数を追加
- `mail-settings`: 「メールテンプレート設定」の既定終業本文に `{{tasks}}` を追加し、変数の案内を表示（既存設定は書き換えない）
- `work-report-logging`: 「終業記録と勤務時間計算」に進行中タスク・休憩の確認を追加、「保存情報の範囲」にタスク・休憩・ジョブを追加
- `report-calendar`: 「本日の報告画面」に業務明細（タスク・休憩）の操作・一覧を追加し、自由記述の業務報告欄を廃止

## Impact

- **DB**：新規テーブル `work_tasks`・`work_breaks`・`jobs`・`automation_settings`（Phase 1 では既定休憩のみ）。Alembic マイグレーション追加。既存 `work_reports`・`mail_settings` の行は変更しない
- **API**：`/api/work-reports/{date}/tasks`（一覧・追加・`start`）、`/api/tasks/{id}`（更新・削除・`stop`）、`/api/work-reports/{date}/breaks`（一覧・追加・`start`）、`/api/breaks/{id}`（更新・削除・`stop`）、`/api/jobs`、`/api/automation-settings` を追加。既存 API は互換維持（`PATCH .../work-reports/{date}` の `end_mail_body` も残す）
- **Frontend**：`TodayReport.tsx`（業務明細パネル）、`SettingsPanel.tsx`（ジョブマスタ・既定休憩）、`lib/date.ts`（`parseWorkTime`/`formatWorkTime`）、`lib/mail.ts`（変数追加）、`lib/api.ts`・`types.ts`
- **Backend**：`models.py`・`schemas.py`・`repositories.py`・`routes.py`・`config.py`
- **Infra**：`docker-compose.yml` のポート公開範囲
- **Docs**：`docs/API_REFERENCE.md`・`DATABASE_SCHEMA.md`・`ARCHITECTURE.md`・`SETUP_GUIDE.md`
- **後続 change**：`add-attendance-import`・`add-zac-draft-and-registration` は本 change のテーブル・API・`automation_settings` を前提とする
