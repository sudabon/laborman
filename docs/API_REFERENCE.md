# API REFERENCE

- **ベース URL**: `http://localhost:8888`（Docker Compose・フロントエンド既定。ローカル開発で `--port 8000` 起動時は `http://localhost:8000`）
- **API プレフィックス**: `/api`
- **コンテンツタイプ**: `application/json`
- **認証**: なし（個人利用想定）
- **対話的ドキュメント**: Swagger UI `/docs` ・ ReDoc `/redoc` ・ OpenAPI `/openapi.json`

実装: `backend/app/routes.py`（ハンドラ） / `backend/app/schemas.py`（DTO）。

## エンドポイント一覧

| メソッド | パス | 説明 | ハンドラ |
|---------|------|------|----------|
| GET | `/` | サービス名を返すルート | `main.root` |
| GET | `/api/health` | ヘルスチェック | `routes.health` |
| GET | `/api/mail-settings` | メール設定の取得（無ければ既定値を生成） | `routes.read_mail_settings` |
| PUT | `/api/mail-settings` | メール設定の保存（upsert） | `routes.save_mail_settings` |
| GET | `/api/work-reports` | 指定年月の報告一覧 | `routes.read_month_reports` |
| GET | `/api/work-reports/{work_date}` | 指定日の報告取得（無ければ生成） | `routes.read_work_report` |
| PATCH | `/api/work-reports/{work_date}` | メモ・勤務区分の更新 | `routes.patch_work_report` |
| POST | `/api/work-reports/{work_date}/record-start` | 始業打刻 | `routes.post_record_start` |
| POST | `/api/work-reports/{work_date}/record-end` | 終業打刻 | `routes.post_record_end` |
| POST | `/api/work-reports/{work_date}/mail-created` | メール作成済みフラグ記録 | `routes.post_mail_created` |
| PUT | `/api/work-reports/{work_date}/attendance` | 出退勤実績の登録（人事メール取込・手入力） | `routes.put_attendance` |
| GET / POST / PATCH | `/api/zac-work-kinds`・`/api/zac-work-kinds/{name}` | zac の作業内容の一覧・追加・更新（無効化） | `routes.read_work_kinds` ほか |
| GET | `/api/zac-sales-items?job_code=&active=` | zac の売上項目の一覧 | `routes.read_sales_items` |
| POST | `/api/jobs/{code}/sales-items` | 売上項目の追加（対象年月は名前から読み取る） | `routes.post_sales_item` |
| PATCH | `/api/zac-sales-items/{item_id}` | 売上項目の更新（無効化・売上計上済み） | `routes.patch_sales_item` |
| POST | `/api/zac-masters/import` | zac の選択肢の一括取込（追加・更新のみ） | `routes.post_zac_masters_import` |
| GET | `/api/zac-task-defaults` | ジョブごとに直近のタスクの作業内容・売上項目（業務明細の初期値） | `routes.read_zac_task_defaults` |
| GET | `/api/work-reports/{work_date}/zac-draft` | zac 登録ドラフトと検証結果（DB を変更しない） | `routes.read_zac_draft` |
| GET | `/api/zac-sync-runs` | zac 連携の実行履歴（`work_date`・`status`・`order`・`limit` で絞り込み） | `routes.read_zac_runs` |
| POST | `/api/zac-sync-runs` | 実行開始の記録（`status=running`） | `routes.post_zac_run` |
| PATCH | `/api/zac-sync-runs/{run_id}` | 実行結果の記録（`succeeded` で `zac_registered_at` を設定） | `routes.patch_zac_run` |
| POST | `/api/zac-sync-runs/requests` | 画面からの実行依頼（`status=requested`） | `routes.post_zac_run_request` |
| POST | `/api/zac-sync-runs/{run_id}/claim` | 依頼の取得（`requested` → `running`） | `routes.post_zac_run_claim` |
| POST | `/api/zac-sync-runs/{run_id}/cancel` | 依頼の取り消し（`requested` → `cancelled`） | `routes.post_zac_run_cancel` |
| GET | `/api/jobs` | ジョブマスタ一覧 | `routes.read_jobs` |
| POST | `/api/jobs` | ジョブの登録 | `routes.post_job` |
| PATCH | `/api/jobs/{code}` | ジョブの更新・無効化 | `routes.patch_job` |
| POST | `/api/jobs/{code}/change-code` | ジョブ ID の変更（新 ID で作成し、元のジョブを無効化） | `routes.post_job_change_code` |
| GET | `/api/work-reports/{work_date}/tasks` | 指定日のタスク一覧 | `routes.read_tasks` |
| POST | `/api/work-reports/{work_date}/tasks` | タスクの手入力追加 | `routes.post_task` |
| POST | `/api/work-reports/{work_date}/tasks/start` | タスク開始（進行中を終了してから開始） | `routes.post_task_start` |
| PATCH | `/api/tasks/{task_id}` | タスクの更新 | `routes.patch_task` |
| DELETE | `/api/tasks/{task_id}` | タスクの削除 | `routes.remove_task` |
| POST | `/api/tasks/{task_id}/stop` | 進行中タスクの停止 | `routes.post_task_stop` |
| GET | `/api/work-reports/{work_date}/breaks` | 指定日の休憩一覧 | `routes.read_breaks` |
| POST | `/api/work-reports/{work_date}/breaks` | 休憩の手入力追加 | `routes.post_break` |
| POST | `/api/work-reports/{work_date}/breaks/start` | 休憩開始（進行中を終了してから開始） | `routes.post_break_start` |
| PATCH | `/api/breaks/{break_id}` | 休憩の更新 | `routes.patch_break` |
| DELETE | `/api/breaks/{break_id}` | 休憩の削除 | `routes.remove_break` |
| POST | `/api/breaks/{break_id}/stop` | 進行中休憩の終了 | `routes.post_break_stop` |
| GET | `/api/automation-settings` | 自動化設定の取得（無ければ既定値を生成） | `routes.read_automation_settings` |
| PUT | `/api/automation-settings` | 自動化設定の保存（upsert） | `routes.save_automation_settings` |

`{work_date}` は ISO 形式の日付（`YYYY-MM-DD`）。

タスク・休憩の時刻（`start_at` / `end_at`）はタイムゾーン付きの ISO 8601 文字列で送受信します（タイムゾーンなしは 422）。レスポンスは UTC です。

## レスポンスモデル

### WorkReport

```jsonc
{
  "id": "uuid",
  "work_date": "2026-06-08",
  "start_time": "2026-06-08T00:00:00Z",      // null 可
  "end_time": null,                            // null 可
  "start_mail_created_at": null,               // null 可
  "end_mail_created_at": null,                 // null 可
  "note": "",
  "work_style": "office",                      // "office" | "remote"
  "end_mail_body": null,                       // null 可
  "attendance_start_at": null,                 // 出退勤実績の出勤（打刻とは別）。null 可
  "attendance_end_at": null,                   // 出退勤実績の退勤。null 可
  "attendance_source": null,                   // "hr_mail" | "manual" | null（未登録）
  "attendance_kind": "work",                   // "work" | "leave"（未登録は "work"）
  "attendance_imported_at": null,              // 人事メールから取り込んだ日時。null 可
  "zac_registered_at": null,                   // zac への保存成功日時。null 可
  "zac_status": null,                          // 導出値: "registered" | "needs_action" | null（下記）
  "created_at": "2026-06-08T00:00:00Z",
  "updated_at": "2026-06-08T00:00:00Z",
  "status": "start_recorded",                  // 導出値（下記参照）
  "work_duration_minutes": null               // 導出値（start/end から算出）
}
```

`status` の導出ルール（`repositories.derive_status`、上から順に評価）:

| 条件 | status |
|------|--------|
| `end_mail_created_at` あり | `end_mail_created` |
| `end_time` あり | `end_recorded` |
| `start_mail_created_at` あり | `start_mail_created` |
| `start_time` あり | `start_recorded` |
| いずれも無し | `not_started` |

`zac_status` の導出（`repositories.derive_zac_status`）: `zac_registered_at` があれば `registered`。なければ、その日の最新の実行履歴（取り消した依頼を除く）の状態が `validation_failed`・`needs_login`・`failed`・`already_registered_in_zac` なら `needs_action`、それ以外は `null`。月一覧では日ごとの最新の実行履歴を 1 クエリでまとめて取得する。

### MailSettings

```jsonc
{
  "id": "default",
  "boss_email": "",
  "labor_ml_email": "",
  "start_subject_template": "【始業報告】{{date}}",
  "start_body_template": "...",
  "end_subject_template": "【終業報告】{{date}}",
  "end_header_template": "...",
  "end_body_template": "...",           // 既定値の末尾は "業務明細:\n{{tasks}}"
  "end_footer_template": "...",
  "created_at": "2026-06-08T00:00:00Z",
  "updated_at": "2026-06-08T00:00:00Z"
}
```

### Job

```jsonc
{
  "code": "J-2026-001",                        // ジョブ ID（zac の案件コード、主キー）
  "name": "社内システム保守",
  "zac_search_text": "",
  "zac_work_category": "",
  "is_active": true,
  "last_used_at": "2026-10-12T01:00:00Z",      // null 可（タスクで使うたびに更新）
  "created_at": "2026-10-12T00:00:00Z",
  "updated_at": "2026-10-12T00:00:00Z"
}
```

### WorkTask

```jsonc
{
  "id": "uuid",
  "work_report_id": "uuid",
  "job_code": "J-2026-001",
  "description": "障害調査",                   // 最大 200 文字
  "start_at": "2026-10-12T00:00:00Z",
  "end_at": null,                              // null = 進行中
  "created_at": "2026-10-12T00:00:00Z",
  "updated_at": "2026-10-12T00:00:00Z"
}
```

### WorkBreak

```jsonc
{
  "id": "uuid",
  "work_report_id": "uuid",
  "start_at": "2026-10-12T03:00:00Z",
  "end_at": "2026-10-12T04:00:00Z",            // null = 進行中
  "source": "manual",                          // "manual" | "hr_mail"
  "created_at": "2026-10-12T03:00:00Z",
  "updated_at": "2026-10-12T04:00:00Z"
}
```

### AutomationSettings

```jsonc
{
  "id": "default",
  "default_break_start": "12:00",              // 勤務日基準の HH:MM（00:00〜29:59）
  "default_break_end": "13:00",                // default_break_start より後
  "hr_mail_from": "",                          // 人事メールの差出人（任意。空なら差出人で絞り込まない）
  "hr_mail_subject_keyword": "[勤怠情報]",      // 人事メールの件名キーワード（空なら取り込まない。既定 ""）
  "zac_submit_mode": "dry_run",                // "dry_run" | "assist" | "auto"（laborman-agent の実行モード）
  "entry_style": "duration",                   // "duration"（ジョブごとの時間）| "time_range"（時刻順）
  "clip_tolerance_minutes": 15,                // 出退勤からのはみ出しの許容値（0〜120）
  "gap_policy": "block",                       // 空き時間: "block"（エラー）| "assign_default_job"
  "default_job_code": null,                    // 既定ジョブ（assign_default_job では必須。ジョブマスタに存在すること）
  "description_max_length": 100,               // zac の内容欄の最大長（1〜1000）
  "created_at": "2026-10-12T00:00:00Z",
  "updated_at": "2026-10-12T00:00:00Z"
}
```

## エンドポイント詳細

### GET `/api/health`

ヘルスチェック。`{"status": "ok"}` を返す。

### GET `/api/mail-settings`

メール設定（単一行）を返す。レコードが存在しない場合は既定テンプレートで初期化して返す。

### PUT `/api/mail-settings`

メール設定を保存。リクエストボディは `MailSettingsBase`（全フィールド任意、未指定は既定値・`null` は空文字に正規化、文字列は trim される）。

```jsonc
// Request body 例
{
  "boss_email": "boss@example.com",
  "labor_ml_email": "labor-ml@example.com",
  "start_subject_template": "【始業報告】{{date}}",
  "start_body_template": "...",
  "end_subject_template": "【終業報告】{{date}}",
  "end_header_template": "...",
  "end_body_template": "...",
  "end_footer_template": "..."
}
```

### GET `/api/work-reports`

クエリパラメータで指定した年月（その月の 1 日〜翌月 1 日未満）の報告を `work_date` 昇順で返す。

| パラメータ | 型 | 必須 | 制約 |
|-----------|----|----|------|
| `year` | int | ✓ | 2000〜2100 |
| `month` | int | ✓ | 1〜12 |

```
GET /api/work-reports?year=2026&month=6
```

レスポンス: `WorkReport[]`

### GET `/api/work-reports/{work_date}`

指定日の報告を返す。存在しない場合は当日の空レコードを生成して返す（get-or-create）。

### PATCH `/api/work-reports/{work_date}`

メモ・勤務区分のみを部分更新。

```jsonc
// Request body (WorkReportUpdate) — いずれも任意
{
  "note": "リモート勤務",        // 最大 600 文字
  "work_style": "remote",       // "office" | "remote"
  "end_mail_body": null         // 互換のため残置（空文字は null に正規化）
}
```

### POST `/api/work-reports/{work_date}/record-start`

始業を打刻（`start_time` を現在 UTC で記録）。ボディで同時に `note` / `work_style` も更新可能（`RecordEventRequest` = `WorkReportUpdate` と同形）。

### POST `/api/work-reports/{work_date}/record-end`

終業を打刻（`end_time` を現在 UTC で記録）。ボディは `record-start` と同形。

### POST `/api/work-reports/{work_date}/mail-created`

メール作成済みフラグを記録。

```jsonc
// Request body (MailCreatedRequest)
{
  "kind": "start",            // "start" | "end"（必須）
  "end_mail_body": null       // kind="end" のとき本文コアを保存（任意）
}
```

- `kind="start"`: `start_mail_created_at` を現在 UTC で記録。
- `kind="end"`: `end_mail_created_at` を記録し、`end_mail_body` を保存。フロントエンドは `buildEndBodyCore()` で展開した終業本文コア（ヘッダー・フッターを除く、`{{tasks}}` 等の展開済み）のスナップショットを送る。

### PUT `/api/work-reports/{work_date}/attendance`

出退勤実績（人事の出勤・退勤）を登録する。打刻（`start_time` / `end_time`）とは別の項目で、打刻 API はこの値を変えない。報告がなければ生成する（get-or-create）。応答は更新後の `WorkReport`。

`kind="work"` で出勤・退勤の両方があるときは、最初のタスクの開始を出勤に、最後のタスクの終了を退勤に合わせる（ずれが 30 分以内の場合だけ。zac 登録済みの日・端に休憩がある場合・進行中のタスクの終了・タスクが空になる変更は対象外。`repositories.align_tasks_to_attendance`）。

```jsonc
// Request body (AttendanceUpdate)
{
  "start_at": "2026-10-09T08:29:00+09:00",  // タイムゾーン付き ISO 8601。kind="leave" では null 可
  "end_at": "2026-10-09T18:38:00+09:00",
  "source": "hr_mail",                      // "hr_mail"（laborman-agent）| "manual"（UI の手入力）
  "kind": "work"                            // "work" | "leave"（既定 "work"）
}
```

| ルール | 違反時 |
|--------|--------|
| `kind="work"` は `start_at`・`end_at` の両方が必須で、`end_at` > `start_at` | 422 |
| 時刻は勤務日の 00:00 ≤ 時刻 < 翌日 06:00（タスク・休憩と同じ範囲） | 422 |
| `source="hr_mail"` と `kind="leave"` の組み合わせ（人事メールから休暇は来ない） | 422 |
| 既存の `attendance_source` が `manual` の日に `source="hr_mail"` で登録（手入力を保護。値は変えない） | 409 |

- `source="hr_mail"` のときは `attendance_imported_at` を現在時刻にする。`manual` のときは変更しない。
- `manual` は `hr_mail` の値をいつでも上書きできる（UI の「手入力」）。

### GET `/api/jobs`

ジョブマスタを `last_used_at` 降順（未使用は末尾）→ `code` 昇順で返す。

| パラメータ | 型 | 必須 | 制約 |
|-----------|----|----|------|
| `active` | bool | | 指定時は `is_active` で絞り込み（未指定は無効化分も含む） |
| `q` | string | | `code` / `name` の部分一致（大文字小文字を区別しない） |

レスポンス: `Job[]`

### POST `/api/jobs`

ジョブを登録（201）。同じ `code` が既にあれば **409**。

```jsonc
// Request body (JobCreate)
{
  "code": "J-2026-001",          // 必須・1〜64 文字（trim される）
  "name": "社内システム保守",     // 必須（trim される）
  "zac_search_text": "",         // 任意
  "zac_work_category": ""        // 任意
}
```

### PATCH `/api/jobs/{code}`

`name` / `zac_search_text` / `zac_work_category` / `is_active` を部分更新（未指定・`null` は変更しない）。存在しなければ **404**。削除 API は無く、使わなくなったジョブは `is_active: false` で無効化する（過去のタスクは参照を保つ）。

### GET `/api/work-reports/{work_date}/zac-draft`

その日の zac 登録ドラフト（zac に入力する内容）と検証結果を返す。算出は `app/zac_draft.py` の純粋関数で、報告や設定がなくても作成しない（DB を変更しない）。画面とエージェントは同じ結果を使う。時刻は勤務日基準の `HH:MM`（翌日は 24:00〜）。

```jsonc
{
  "work_date": "2026-10-09",
  "attendance": { "start": "09:02", "end": "18:41", "source": "hr_mail" },  // 未取込・休暇は null
  "breaks": [{ "start": "12:00", "end": "13:00" }],                           // 出退勤の範囲内（はみ出しは切り詰め）
  "working_minutes": 519,                                                      // 退勤 − 出勤 − 範囲内の休憩
  "entry_style": "duration",
  "entries": [
    { "job_code": "2602028", "zac_search_text": "2602028", "project_name": "エンジンファーム様…",
      "work_kind": "プロジェクト作業", "sales_item": "プロジェクトサポート（2026／10）",
      "minutes": 300, "description": "- 設計レビュー\n- 障害調査", "start": null, "end": null }
  ],
  "issues": [
    { "code": "TASK_OUTSIDE_ATTENDANCE", "severity": "warning",
      "message": "09:00開始のタスクを出勤時刻09:02に切り詰めました", "ref_id": "…" }
  ],
  "registrable": true,       // error が 0 件
  "auto_allowed": false,     // error・warning が 0 件
  "zac_registered_at": null
}
```

- `duration`：「作業内容 × ジョブ × 売上項目」ごとの分数を丸めずに合算する（合計は実働と一致する）。備考は行のタスクの内容を開始順に「- 内容」の改行区切り（重複は除く）にし、最大長で切り詰める。`zac_search_text` が未設定ならジョブ ID。
- `time_range`：タスクを時刻順に 1 行ずつ。連続する同じジョブ・同じ内容は結合する。
- 検証コード：`ATTENDANCE_MISSING`・`ON_LEAVE`・`NO_TASKS`・`TASK_RUNNING`・`TASK_OVERLAP`・`JOB_UNKNOWN`・`JOB_MONTH_MISMATCH`・`WORK_KIND_MISSING`・`SALES_ITEM_MISSING`・`TOTAL_MISMATCH`・`BREAK_MISSING`（error）、`TASK_OUTSIDE_ATTENDANCE`・`UNCOVERED_TIME`（error または warning）、`SALES_ITEM_MONTH_MISMATCH`（warning）、`ALREADY_REGISTERED`（info）。出退勤が未取込・休暇の日は該当 error だけを返し、入力行は空。

### zac の作業内容・売上項目と取込

- タスク（`WorkTask`）は `work_kind`（作業内容の名前）と `sales_item_id`（売上項目の ID）を持つ（どちらも null 可。zac のドラフトでは未設定を error）。売上項目がタスクのジョブのものでなければ 422。ジョブを変えて売上項目を送らなかった場合は売上項目を外す。
- `Job` は `series_name`・`valid_month`（`YYYY-MM`）を持つ。作成時に省略すると案件名の年月表記から導出する（例：`bizoceanAPPs開発(26/10)` → シリーズ `bizoceanAPPs開発`・`2026-10`。期間表記は対象年月なし）。`PATCH` で空文字・null を送ると解除する。
- `POST /api/zac-masters/import`：

```jsonc
// Request
{
  "work_kinds": ["プロジェクト作業", "プロジェクト関連打ち合わせ"],
  "projects": [
    { "code": "2602028", "name": "エンジンファーム様プロジェクトサポート（2026／09-2026／12）",
      "sales_items": [{ "name": "プロジェクトサポート（2026／10）", "is_closed": false }] }
  ]
}
// Response
{
  "created": { "work_kinds": 2, "jobs": 1, "sales_items": 1 },
  "updated": { "work_kinds": 0, "jobs": 0, "sales_items": 0 },
  "missing_jobs": ["2602061"]   // 有効なジョブのうち今回現れなかったもの（無効化しない）
}
```

  追加・更新だけを行い、無効化はしない。同じ内容で何度送っても結果は変わらない。
- 自動化設定には `default_work_kind`・`default_sales_item_id` がある（空き時間を既定ジョブに割り当てるときに使う。`assign_default_job` では既定ジョブと合わせて必須。売上項目は既定ジョブのものであること）。

### zac 連携の実行履歴（`/api/zac-sync-runs`）

`ZacSyncRun`：`id`・`work_date`・`mode`・`status`・`entries`（入力した内容のスナップショット）・`message`・`screenshot_path`（ホスト上のパス）・`agent_version`・`started_at`・`finished_at`。

`status` は `requested`・`cancelled`・`running`・`succeeded`・`dry_run_done`・`awaiting_user`・`validation_failed`・`needs_login`・`vpn_unreachable`・`hr_mail_not_found`・`already_registered_in_zac`・`failed`。

- `POST /api/zac-sync-runs`（本文 `{ work_date, mode, agent_version? }`）：`status=running` で作成（201）。報告がなければ作る。
- `PATCH /api/zac-sync-runs/{id}`（本文 `{ status?, message?, entries?, screenshot_path?, mode?, agent_version? }`）：`requested`・`running` 以外になったら `finished_at` を設定。`succeeded` で対象日の `zac_registered_at` を現在時刻にする。`requested`・`cancelled` への変更は 422（専用の API を使う）。
- `POST /api/zac-sync-runs/requests`（本文 `{ work_date }`）：画面の「この日を zac に登録」。`status=requested`・`mode=設定の実行モード` で作成（201）。同じ日に `requested`、または 60 分以内に始まった `running` があれば 409。
- `POST /api/zac-sync-runs/{id}/claim`：`requested` → `running`（`started_at` を現在時刻に）。条件付き更新で、`requested` でなければ 409（二重実行の防止）。
- `POST /api/zac-sync-runs/{id}/cancel`：`requested` → `cancelled`。`requested` でなければ 409。
- `GET /api/zac-sync-runs?work_date=&status=&order=asc|desc&limit=`：既定は新しい順・50 件。

### POST `/api/jobs/{code}/change-code`

ジョブ ID を変更する（201）。変更後の ID で新しいジョブを有効な状態で作成し、元のジョブを無効化する（同一トランザクション）。元の ID で記録済みのタスクは変更しない（月替わりで ID が変わる業務の履歴を保つため）。新しいジョブは元のジョブの最近使った順の位置（`last_used_at`）を引き継ぐ。

```jsonc
// Request body (JobCodeChange)
{
  "code": "JOB-2611",          // 必須。前後の空白は除去。変更前と同じなら 422
  "name": "A社保守（11月）",    // 任意。省略時は元のジョブの値
  "zac_search_text": null,     // 任意。省略・null は元のジョブの値
  "zac_work_category": null    // 任意。省略・null は元のジョブの値
}
```

- 元のジョブがなければ 404、変更後の ID がすでにあれば 409（何も変更しない）。

### GET `/api/work-reports/{work_date}/tasks`

指定日のタスクを `start_at` 昇順で返す（報告が無い日は空配列。行は生成しない）。レスポンス: `WorkTask[]`

### POST `/api/work-reports/{work_date}/tasks`

過去分などの手入力用。タスクを追加（201）。`end_at` を省略・`null` にすると進行中として登録する。

```jsonc
// Request body (TaskCreate)
{
  "job_code": "J-2026-001",              // 必須・登録済みであること
  "description": "障害調査",              // 任意・最大 200 文字
  "start_at": "2026-10-12T09:00:00+09:00",
  "end_at": "2026-10-12T10:30:00+09:00"  // 任意（null = 進行中）
}
```

### POST `/api/work-reports/{work_date}/tasks/start`

> 画面（業務明細）は時刻を入力して `POST .../tasks` で登録するため、開始・停止・休憩開始・休憩終了の API は使いません。外部からの記録用に残しています。

サーバーの現在時刻でタスクを開始（201）。同じ勤務日の進行中タスク・休憩を同じ現在時刻で終了してから、新しいタスクを同一トランザクションで作成する。

```jsonc
// Request body (TaskStartRequest)
{
  "job_code": "J-2026-001",   // 必須
  "description": ""           // 任意・最大 200 文字
}
```

### PATCH `/api/tasks/{task_id}`

`job_code` / `description` / `start_at` / `end_at` を部分更新。`end_at: null` で進行中に戻す（`start_at: null` は 422）。存在しなければ **404**。

### DELETE `/api/tasks/{task_id}`

タスクを削除（**204**）。存在しなければ **404**。

### POST `/api/tasks/{task_id}/stop`

進行中タスクの `end_at` をサーバーの現在時刻で記録。終了済みなら **409**。

### 休憩（`/api/work-reports/{work_date}/breaks`・`/api/breaks/{break_id}`）

タスクと同じ形の API。違いは次のとおり。

- リクエストボディは `start_at` / `end_at` のみ（`BreakCreate` / `BreakUpdate`）。
- `POST .../breaks/start` はボディ不要。進行中のタスク・休憩を終了してから休憩を開始する。
- API から作成した休憩の `source` は `manual`（`hr_mail` は後続の出退勤取込用）。

### GET `/api/automation-settings`

自動化設定（単一行）を返す。レコードが存在しない場合は既定値（`12:00`〜`13:00`）で初期化して返す。

### PUT `/api/automation-settings`

既定の休憩・人事メールの検索条件・zac 連携の設定を保存（全項目を送る。省略した項目は既定値になる）。空き時間の扱いが `assign_default_job` で既定ジョブがない、既定ジョブがジョブマスタにない場合は 422。前後の空白は除去する。既定の休憩は`HH:MM`（`^[0-2][0-9]:[0-5][0-9]$`、勤務日基準の 00:00〜29:59）で、`default_break_end` は `default_break_start` より後であること（違反は 422）。

```jsonc
// Request body (AutomationSettingsBase)
{
  "default_break_start": "12:00",
  "default_break_end": "13:00",
  "hr_mail_from": "",
  "hr_mail_subject_keyword": "[勤怠情報]"
}
```

### タスク・休憩の検証ルール

`repositories.py` が保存前に検証する。

| ルール | 違反時 |
|--------|--------|
| 時刻がタイムゾーン付き ISO 8601 | 422 |
| 勤務日の 00:00 ≤ 時刻 < 翌日 06:00（`app_timezone` 基準、既定 `Asia/Tokyo`） | 422 |
| `end_at` > `start_at` | 422 |
| `description` は 200 文字以内 | 422 |
| `job_code` がジョブマスタに存在する | 422 |
| 進行中（`end_at` が `null`）のタスク・休憩はそれぞれ勤務日ごとに 1 件まで | 409 |

## エラー

- バリデーション失敗時は FastAPI 既定の **422 Unprocessable Entity**（`detail` 配列）。業務ルール違反（勤務日の範囲外・未登録ジョブなど）の 422 は `{"detail": "メッセージ"}`。
- 対象が無い場合は **404**（`{"detail": "メッセージ"}`）。
- 進行中の重複・ジョブ ID の重複・終了済みの停止・手入力済みの出退勤実績への人事メール登録・zac 登録の重複依頼・依頼の二重取得は **409 Conflict**。進行中の重複は相手のレコードを `conflicts` に返す（ジョブ重複などは空配列）。
- タスク同士・タスクと休憩の時間帯の重なりは拒否しない（利用者が後で調整する。zac 登録前のドラフト検証で検出する）。

```jsonc
// 409 レスポンス例
{
  "detail": {
    "message": "進行中のタスクがすでにあります",
    "conflicts": [
      { "kind": "task", "id": "uuid", "start_at": "2026-10-12T00:00:00+00:00", "end_at": null }
    ]
  }
}
```

- フロントエンド（`lib/api.ts`）は非 2xx 応答を `ApiError`（`status`・メッセージ・`conflicts`）に変換し、`detail` が文字列ならそのまま、オブジェクトなら `message`、配列なら各 `msg` を表示する。
