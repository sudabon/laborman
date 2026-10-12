# Tasks

## 1. データモデルとマイグレーション

- [ ] 1.1 `models.py` に `Job`・`WorkTask`・`WorkBreak`・`AutomationSettings` を追加する（FK・CHECK・部分一意インデックス `uq_work_tasks_running`/`uq_work_breaks_running` を `postgresql_where`/`sqlite_where` 付きで定義、`WorkReport` に `cascade="all, delete-orphan"` の relationship）。`uv run pytest` の既存テストが通ることで確認する
- [ ] 1.2 Alembic マイグレーション `20261012_0001_add_work_tasks_breaks_jobs.py` を追加する。Docker の PostgreSQL に対し `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` が成功し、既存の `work_reports`・`mail_settings` の行が変わらないことを確認する
- [ ] 1.3 `config.py` の `Settings` に `app_timezone: str = "Asia/Tokyo"` を追加し、`uv run mypy .` が通ることを確認する

## 2. ジョブマスタ API

- [ ] 2.1 `GET/POST /api/jobs`・`PATCH /api/jobs/{code}` を実装する（`active`・`q` フィルタ、`last_used_at DESC NULLS LAST` 順、重複 `409`）。pytest で追加・重複・検索・並び順・無効化の除外を検証する

## 3. タスク・休憩 API

- [ ] 3.1 タスク・休憩共通の検証（勤務日 00:00〜翌 06:00 の範囲、`end > start`、内容 200 文字、ジョブの存在）と重なり検査（半開区間、進行中は現在時刻まで、`409` の `detail.conflicts`）をリポジトリ層に実装する。pytest で隣接 OK・タスク同士・タスクと休憩・範囲外 `422` を検証する
- [ ] 3.2 タスクの一覧・追加・更新・削除（`/api/work-reports/{date}/tasks`・`/api/tasks/{id}`）を実装し、作成時に `jobs.last_used_at` を更新する。pytest で CRUD・開始順・`25:15` 相当（翌日 01:15 JST）の保存・進行中 2 件目の `409` を検証する
- [ ] 3.3 `POST /api/work-reports/{date}/tasks/start` と `POST /api/tasks/{id}/stop` を実装する（進行中タスク・休憩の終了と新規作成を同一トランザクション）。pytest で切り替え時に前タスクが同時刻で終了することを検証する
- [ ] 3.4 休憩の一覧・追加・更新・削除・`breaks/start`・`breaks/{id}/stop` を実装する（`start` は進行中タスクを終了）。pytest で休憩開始によるタスク終了・進行中 1 件制約・重なり `409` を検証する
- [ ] 3.5 `GET/PUT /api/automation-settings`（既定休憩のみ、`HH:MM` 形式検証）を実装し、pytest で初期値 12:00–13:00 と更新を検証する

## 4. フロントエンド基盤

- [ ] 4.1 `types.ts`・`lib/api.ts` にジョブ・タスク・休憩・自動化設定の型と API 関数を追加し、`pnpm run build` の型チェックが通ることを確認する
- [ ] 4.2 `lib/date.ts` に `parseWorkTime(workDate, "HH:MM")`・`formatWorkTime(workDate, iso)` を追加する。Vitest で `09:00`・`24:00`・`25:15`・`29:59`・`30:00`（エラー）・不正形式を検証する
- [ ] 4.3 `lib/mail.ts` に `{{tasks}}`・`{{tasks_by_job}}`・`{{breaks}}`・`{{task_total}}` の展開を追加する（進行中は除外、0 件は空文字）。`mail.test.ts` に展開例（spec のシナリオ）と既存変数の回帰テストを追加して通す

## 5. 画面

- [ ] 5.1 `TodayReport.tsx` に業務明細パネルを追加する（ジョブコンボボックス・内容入力・タスク開始／休憩開始／停止／休憩終了／再開／既定の休憩を追加／行を追加、開始順の一覧と編集・削除、作業・休憩の合計、`409` 時の相手時間帯表示）。Testing Library でタスク開始→休憩→再開と重なりエラー表示を検証する
- [ ] 5.2 ジョブコンボボックスに最近使った順の候補・インクリメンタル検索・未登録 ID のその場登録を実装し、Testing Library で候補順とその場登録を検証する
- [ ] 5.3 「業務報告」テキストエリアを削除し、メール作成パネルに `{{tasks}}` の読み取り専用プレビューとコピーボタンを追加する。終業メール作成時の `end_mail_body` が `buildEndBodyCore()` の結果になることを `MailComposeDialog.test.tsx` などで検証する
- [ ] 5.4 「終業を記録」時に進行中のタスク・休憩があれば確認ダイアログを出し、承認時のみ停止→終業記録する。Testing Library で承認・取消の両方を検証する
- [ ] 5.5 `SettingsPanel.tsx` にジョブマスタ管理（追加・編集・無効化）と既定休憩の設定、終業テンプレートの `{{tasks}}` 案内を追加し、画面で保存・再読込できることを確認する

## 6. 既定テンプレート・インフラ

- [ ] 6.1 `DEFAULT_END_BODY_TEMPLATE` に `業務明細:` と `{{tasks}}` を追加する（既存の `mail_settings` 行は更新しない）。pytest で新規作成時の既定値に `{{tasks}}` が含まれることを検証する
- [ ] 6.2 `docker-compose.yml` の backend ポートを `"127.0.0.1:8888:8888"` に変更し、`task start` 後に `curl http://127.0.0.1:8888/api/health` が成功することを確認する

## 7. ドキュメント・仕様

- [ ] 7.1 `docs/API_REFERENCE.md`・`DATABASE_SCHEMA.md`・`ARCHITECTURE.md`・`SETUP_GUIDE.md` を新しいテーブル・API・ポート・テンプレート変数に合わせて更新する

## 8. 検証

- [ ] 8.1 `cd backend && uv run pytest && uv run ruff check . && uv run mypy .`、`cd frontend && pnpm test && pnpm run build` がすべて成功することを確認する
- [ ] 8.2 `task build && task start` 後の実画面で、当日に「タスク開始」「休憩開始」「休憩終了」「再開」「停止」で 1 日分を記録でき、重なる行が保存されないことを確認する
- [ ] 8.3 実画面で過去日のタスクを手入力・編集・削除でき（`25:15` を含む）、`{{tasks}}` を含むテンプレートで終業メール本文に業務明細が展開されることを確認する
- [ ] 8.4 `openspec validate add-work-tasks-and-breaks --strict --no-interactive` が成功することを確認する
