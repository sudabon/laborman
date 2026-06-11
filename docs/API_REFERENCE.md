# API REFERENCE

- **ベース URL**: `http://localhost:8000`（既定）
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

`{work_date}` は ISO 形式の日付（`YYYY-MM-DD`）。

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

### MailSettings

```jsonc
{
  "id": "default",
  "boss_email": "",
  "labor_ml_email": "",
  "cc_emails": "",
  "bcc_emails": "",
  "start_subject_template": "【始業報告】{{date}}",
  "start_body_template": "...",
  "end_subject_template": "【終業報告】{{date}}",
  "end_header_template": "...",
  "end_body_template": "...",
  "end_footer_template": "...",
  "created_at": "2026-06-08T00:00:00Z",
  "updated_at": "2026-06-08T00:00:00Z"
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
  "cc_emails": "cc1@example.com, cc2@example.com",
  "bcc_emails": "",
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
  "work_style": "remote"        // "office" | "remote"
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
- `kind="end"`: `end_mail_created_at` を記録し、`end_mail_body` を保存。

## エラー

- バリデーション失敗時は FastAPI 既定の **422 Unprocessable Entity**（`detail` 配列）。
- フロントエンド（`lib/api.ts`）は非 2xx 応答のレスポンス本文をそのままエラーメッセージとして表示する。
