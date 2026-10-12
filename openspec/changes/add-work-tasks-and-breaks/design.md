# Design

## Context

- 構成は FastAPI（`backend/app/`：`models.py`・`schemas.py`・`repositories.py`・`routes.py`）＋ PostgreSQL 17 ＋ React SPA（ビルド成果物を `backend/public/` から配信）。テストは backend が pytest（SQLite インメモリ、`backend/tests/test_api.py`）、frontend が Vitest。
- `work_reports` は `work_date` で 1 日 1 行、存在しない日は get-or-create。時刻は `timestamptz`（UTC 保存）。
- 「本日の報告」（`TodayReport.tsx`）の「業務報告」テキストエリアは、`buildEndBodyCore()` で終業本文テンプレートを展開した値を初期値とする**編集可能な終業本文**で、メール作成時に `end_mail_body` として保存される。
- テンプレート変数の展開はフロントエンド（`frontend/src/lib/mail.ts` の `templateValues()`）で行い、既定テンプレートは `backend/app/schemas.py` の `DEFAULT_*` 定数。
- 背景・動機は proposal.md、振る舞いは specs/ を参照。全体設計の出典は `ZAC_AUTOMATION_SPEC.md`。

## Goals / Non-Goals

**Goals:**

- 後続 change（出退勤取込・zac ドラフト算出）がそのまま使えるデータモデルと API を確定する
- 重なり・進行中 1 件などの整合性を backend で保証し、UI・後続のエージェントのどちらから書いても同じ規則が効くようにする
- 既存のテストと既存データ（`work_reports`・`mail_settings`）を壊さない

**Non-Goals:**

- 出退勤実績（`attendance_*`）と `{{attendance_start}}`/`{{attendance_end}}`（`add-attendance-import` で扱う）
- zac ドラフト算出・既定休憩の「提案」表示（`BREAK_SUGGESTED`）・カレンダーの zac 状態（`add-zac-draft-and-registration` で扱う）
- 自由記述 `end_mail_body` からの移行スクリプト（仕様書 §10。書き方のサンプル入手後に別 change とする）

## Decisions

### D1. テーブル構成

仕様書 §5.1〜5.3 のとおり `work_tasks`・`work_breaks`・`jobs` を追加する。

- `work_tasks.work_report_id` → `work_reports.id`（ON DELETE CASCADE）、`work_tasks.job_code` → `jobs.code`（ON UPDATE CASCADE）。SQLite テストで CASCADE が効かないため ORM の relationship に `cascade="all, delete-orphan"` も付ける。
- `CHECK (end_at IS NULL OR end_at > start_at)`。
- 進行中 1 件は部分一意インデックス `uq_work_tasks_running` / `uq_work_breaks_running`（`(work_report_id) WHERE end_at IS NULL`）で DB に強制する。`postgresql_where` と `sqlite_where` を両方指定し、テストでも制約が効くようにする。
- `work_breaks.source` は `varchar(16) NOT NULL DEFAULT 'manual'`、`CHECK (source in ('manual','hr_mail'))`。Phase 1 では `manual` のみ書き込む。

**代替案**：PostgreSQL の排他制約（`EXCLUDE USING gist`）で重なりを防ぐ案は、SQLite のテストで再現できないため採らない（D3）。

### D2. `automation_settings` を Phase 1 で作り、既定休憩だけを持たせる

既定休憩（REQ-B4）の保存先として、`mail_settings` と同じ `CHECK (id = 'default')` の単一行テーブル `automation_settings` を作成し、Phase 1 では `default_break_start` / `default_break_end`（`varchar(5)`、既定 `'12:00'`/`'13:00'`）のみを持たせる。API は `GET/PUT /api/automation-settings`。後続 change が人事メール条件・zac 設定の列を追加する。

**代替案**：`mail_settings` に列を足す案は、メールと無関係な設定が混ざり、後続の zac 設定も同居させることになるため採らない。

### D3. 重なり検査・進行中の自動終了はリポジトリ層で 1 トランザクション

- 重なり検査は `repositories.py` で、同一 `work_report_id` のタスクと休憩（自分自身を除く）に対し半開区間 `[start, end)` で判定する。進行中（`end_at IS NULL`）の相手は終了を「現在時刻」とみなして判定する。重なれば `409` で `detail = {"message": ..., "conflicts": [{"kind": "task"|"break", "id": ..., "start_at": ..., "end_at": ...}]}` を返す。
- `POST .../tasks/start` と `POST .../breaks/start` は、進行中のタスク・休憩を `now` で終了→新規作成を同一トランザクションで行う。`now` は backend の現在時刻（クライアント時刻は使わない）。
- タスクの作成・開始時に `jobs.last_used_at` を更新する。

### D4. 時刻の受け渡しと勤務日の範囲

- API は ISO 8601（タイムゾーン付き）でやり取りする。`HH:MM`（`24:00`〜`29:59` を含む）との相互変換はフロントエンド `lib/date.ts` の `parseWorkTime(workDate, "25:15")` / `formatWorkTime(workDate, iso)` で行う。
- backend の `Settings` に `app_timezone: str = "Asia/Tokyo"` を追加する。保存時に「勤務日 00:00 ≤ 時刻 < 勤務日翌日 06:00（`app_timezone`）」を検証し、範囲外は `422`。フロントエンドでも同じ範囲を事前検証する（`30:00` 以上は入力エラー）。

**代替案**：API で `HH:MM` 文字列を受ける案は、後続のエージェントや zac ドラフト算出で再変換が必要になるため採らない。

### D5. ジョブ API とその場登録

- `GET /api/jobs?active=true&q=` は `last_used_at DESC NULLS LAST, code` 順。`q` はジョブ ID・表示名の部分一致。`POST /api/jobs`（重複は `409`）、`PATCH /api/jobs/{code}`（表示名・zac 情報・`is_active`）。削除 API は設けない。
- UI のジョブ選択はコンボボックス。候補に一致しない入力では「`<ID>` を登録」を出し、表示名を入力して `POST /api/jobs` → そのままタスク作成に進む。

### D6. 終業本文とテンプレート変数

- `{{tasks}}`・`{{tasks_by_job}}`・`{{breaks}}`・`{{task_total}}` は `lib/mail.ts` で、当日のタスク・休憩・ジョブ一覧を引数に追加して展開する（既存の展開方式に合わせ、backend には持たない）。進行中のタスク・休憩は展開対象外。
- 「業務報告」テキストエリアは削除する。メール作成パネルに `{{tasks}}` の展開結果を読み取り専用で表示しコピーボタンを付ける。終業メール作成時の `end_mail_body` は `buildEndBodyCore()`（ヘッダ・フッタを除く本文テンプレートの展開結果）をそのままスナップショットとして保存する。`PATCH .../work-reports/{date}` の `end_mail_body` は互換のため残す。
- `DEFAULT_END_BODY_TEMPLATE` に `業務明細:\n{{tasks}}` を追加する。マイグレーションでは `mail_settings` の既存行を更新しない。

### D7. 終業記録時の進行中レコード

「終業を記録」押下時、フロントエンドが進行中のタスク・休憩の有無を確認し、あれば確認ダイアログを出す。承認時は `POST /api/tasks/{id}/stop`（または `breaks/{id}/stop`）→ `record-end` の順に呼ぶ。取消時は何も呼ばない。backend の `record-end` は変更しない。

### D8. ポートの公開範囲

`docker-compose.yml` の backend を `"127.0.0.1:8888:8888"` に変更する。後続 change で出退勤実績を書き換える API が増えるため、LAN からの到達を先に断つ。

## Risks / Trade-offs

- [業務報告欄の廃止で、終業本文を自由に編集できなくなる] → 補足は「メモ」に書く運用とし、proposal で **BREAKING（UI）** と明示する。`{{tasks}}` を含まない既存テンプレートの利用者には設定画面で案内する
- [既存テンプレートに `{{tasks}}` がないと、タスクが終業メールに出ない] → 自動書き換えはしない方針（既存設定の尊重）を優先し、案内表示で補う
- [重なり検査がアプリ層のみのため、同時書き込みで競合しうる] → 単一ユーザー・ローカル利用前提で許容。進行中 1 件は DB の部分一意インデックスで強制する
- [端末の時刻と backend の時刻がずれると、開始/停止の時刻が画面の時計と異なる] → 同一 Mac 上の Docker のため実害は小さい。開始/停止の時刻は常に backend 基準とする
- [DB の `5432` は引き続きホスト全体に公開される] → 本 change では仕様書どおり backend のみ対象とし、DB の公開範囲は別途検討する

## Migration Plan

1. Alembic マイグレーション `20261012_0001_add_work_tasks_breaks_jobs.py` で `jobs`・`work_tasks`・`work_breaks`・`automation_settings` を作成する（既存テーブルは変更しない）
2. `task build` でフロントエンドを `backend/public/` に反映し、`task start` で再起動する
3. ロールバックは `alembic downgrade -1`（新規テーブルを削除）。既存データは変更していないため、以前のイメージに戻せばそのまま動く
