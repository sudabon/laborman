# ARCHITECTURE

laborman は **SPA フロントエンド + REST API バックエンド + PostgreSQL** の 3 層構成です。メール送信機能はサーバー側に持たず、フロントエンドがテンプレートから Outlook on the web の compose deep link を生成し、新しいブラウザタブの作成画面へ委譲します。

## システム構成図

```mermaid
flowchart LR
    subgraph Client["ブラウザ"]
        SPA["React 19 SPA<br/>(Vite / Tailwind)"]
        OWA["Outlook on the web<br/>(新しい作成タブ)"]
        LS["localStorage<br/>(送信済み自己申告)"]
    end

    subgraph Server["バックエンド (FastAPI)"]
        API["REST API<br/>/api/*"]
        Repo["repositories<br/>(ドメインロジック)"]
        ORM["SQLAlchemy ORM"]
    end

    DB[("PostgreSQL 17")]

    SPA -->|"fetch (JSON)"| API
    SPA -.->|"compose deep link<br/>noopener / noreferrer"| OWA
    SPA <-->|"送信済み自己申告"| LS
    API --> Repo --> ORM --> DB

    Nginx["Nginx<br/>(静的配信)"] -.->|"本番ビルド配信"| SPA
```

## リクエストフロー（始業/終業メール作成）

```mermaid
sequenceDiagram
    participant U as ユーザー
    participant FE as React SPA
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OWA as Outlook on the web

    U->>FE: 「始業を記録」
    FE->>API: POST /api/work-reports/{date}/record-start
    API->>DB: start_time を記録 (UTC)
    API-->>FE: WorkReport (status=start_recorded)
    U->>FE: 「Outlook on the webでメール作成」
    FE->>FE: buildMailDraft() でテンプレート展開
    FE->>FE: To・CC・BCCをToへ統合
    FE->>FE: buildOutlookComposeUrl() でURL生成
    U->>FE: 確認画面で作成を確定
    FE->>OWA: window.open(_blank, noopener/noreferrer)
    Note over FE,OWA: ユーザー操作内でAPI処理より先に新しいタブを開く
    FE->>API: POST /api/work-reports/{date}/mail-created
    API->>DB: start_mail_created_at を記録
    API-->>FE: WorkReport (status=start_mail_created)
    U->>OWA: Fromと内容を確認して送信
    U->>FE: 元のタブへ戻り送信済みを自己申告
    FE->>FE: localStorageへ自己申告を保存
```

## レイヤー構成

### バックエンド（`backend/app/`）

| モジュール | 役割 |
|-----------|------|
| `main.py` | FastAPI アプリ生成、CORS ミドルウェア、ルーター登録 |
| `routes.py` | プレゼンテーション層。`/api` 配下のエンドポイント定義と DTO シリアライズ |
| `repositories.py` | アプリケーション／ドメイン層。get-or-create、ステータス導出、勤務時間計算などのロジック |
| `models.py` | インフラ層。SQLAlchemy ORM モデル（`MailSettings` / `WorkReport`） |
| `schemas.py` | Pydantic スキーマ（リクエスト／レスポンス DTO）とテンプレート初期値 |
| `database.py` | エンジン・セッションファクトリ・`get_db` 依存性 |
| `config.py` | `pydantic-settings` による環境変数読み込み（`lru_cache` でシングルトン化） |
| `alembic/` | マイグレーション（モデルとは独立した DDL を保持） |

設計上のポイント:

- **ステータスは保存せず導出する** — `WorkReport` のタイムスタンプ列（`start_time`, `start_mail_created_at`, `end_time`, `end_mail_created_at`）から `derive_status()` が `ReportStatus` を算出します。状態の二重管理を避ける設計です。
- **get-or-create パターン** — 日付指定の参照・更新は対象行が無ければ自動生成（`get_or_create_report`）。フロントは「その日の報告が存在するか」を意識しなくてよい。
- **勤務時間は計算プロパティ** — `work_duration_minutes` はレスポンス時に `end_time - start_time` から算出（保存しない）。
- **時刻は UTC で保存** — 打刻は `datetime.now(UTC)` で記録し、表示整形はフロント側（`date-fns`）が担当。

### フロントエンド（`frontend/src/`）

| パス | 役割 |
|------|------|
| `App.tsx` | 画面状態管理（`today` / `calendar` / `settings` の 3 ビュー切替）と API オーケストレーション |
| `components/TodayReport.tsx` | 本日の打刻・メモ入力・メール作成ボタン |
| `components/ReportCalendar.tsx` | 月次カレンダー（react-day-picker） |
| `components/SettingsPanel.tsx` | メール設定フォーム |
| `components/MailComposeDialog.tsx` | メール下書きプレビュー、M365／From確認案内、Outlook on the web の新規タブ起動、項目別コピー |
| `components/ui/` | shadcn-ui 系の共通 UI 部品 |
| `lib/api.ts` | `fetch` ラッパー。全 API 呼び出しを集約 |
| `lib/mail.ts` | テンプレート展開（`renderTemplate`）と Outlook compose deep link 構築（`buildOutlookComposeUrl`） |
| `lib/date.ts` | 日付・時刻・勤務時間の整形 |
| `types.ts` | バックエンド DTO に対応する TypeScript 型 |

設計上のポイント:

- **メール送信は行わない** — `lib/mail.ts` が Outlook on the web の compose deep link を組み立て、宛先・件名・本文は `encodeURIComponent` でエスケープ、複数宛先はリテラルのカンマで連結します。送信操作はユーザーに委譲します。
- **宛先区分をToへ統合する** — compose deep linkでCCが反映されない実機結果に合わせ、`getOutlookToRecipients()` が登録上のTo・CC・BCCをこの順で統合し、`to` パラメータだけを生成します。自動入力と引き換えにCC/BCCの区分は維持されず、BCCを含む全宛先が受信者全員に表示されるため、設定画面と確認画面で警告します。
- **新しいタブを先に開く** — 確認クリックの同期処理内で `window.open` を呼び、`noopener,noreferrer` で元タブへの参照を渡しません。その後にメール作成済み API を実行するため、ポップアップブロックを避けながら元の laborman タブと記録フローを維持します。
- **外部タブの結果を推測しない** — Outlook on the web の読込状態、From、送信完了はクロスオリジンのため検知しません。「メール作成済み」は API、送信済みの自己申告は localStorage と責務を分けます。
- **テンプレート変数** — `{{date}}` `{{start_time}}` `{{end_time}}` `{{work_duration}}` `{{work_style}}` `{{note}}` を `renderTemplate` が置換。
- **送信確認は localStorage** — 「送信済み」のチェック状態はサーバーに持たず、`laborman.sentConfirmations` キーでブラウザに保持。

## 技術選定の理由（概要）

- **FastAPI + Pydantic**: 型安全な DTO とスキーマ駆動の OpenAPI 自動生成。
- **SQLAlchemy 2.0 + Alembic**: 型付き ORM とマイグレーションの分離。
- **Outlook on the web compose deep link**: OS の既定メールクライアントに依存せず、Microsoft Graph のアプリ登録・権限同意・トークン管理や SMTP 認証情報を追加せずに会社のブラウザメール運用へ組み込めるため。CC/BCCはdeep linkで安定して反映されないため、全宛先をToへ統合するトレードオフを採用しています。
- **Docker Compose**: db / backend / frontend を 1 コマンドで再現。

## デプロイ構成

`docker-compose.yml` に 3 サービス: `db`（PostgreSQL、ヘルスチェック付き）、`backend`（マイグレーション後に uvicorn 起動）、`frontend`（Nginx で静的配信、`VITE_API_BASE_URL` をビルド時引数で注入）。詳細は [SETUP_GUIDE.md](./SETUP_GUIDE.md) を参照。
