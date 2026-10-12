# Tasks

## 1. backend：出退勤実績

- [ ] 1.1 `WorkReport` に `attendance_start_at`・`attendance_end_at`・`attendance_source`・`attendance_kind`・`attendance_imported_at`・`attendance_break_minutes`（CHECK 制約付き）を、`AutomationSettings` に `hr_mail_from`・`hr_mail_subject_keyword` を追加し、Alembic マイグレーションを作成する。Docker の PostgreSQL で `upgrade` → `downgrade -1` → `upgrade` が成功し、既存行の `attendance_kind` が `work` になることを確認する
- [ ] 1.2 `WorkReportRead` と `GET/PUT /api/automation-settings` を新しい項目に対応させ、既存の pytest が通ることを確認する
- [ ] 1.3 `PUT /api/work-reports/{date}/attendance` を実装する（`kind=work` の必須・順序・範囲検証、`leave` の空時刻、`hr_mail` での `attendance_imported_at` 設定、`manual` 保護の `409`）。pytest で各分岐と、打刻 API が実績を変えないことを検証する
- [ ] 1.4 休憩追加 API に任意項目 `source`（`manual`/`hr_mail`、既定 `manual`）を追加し、pytest で `hr_mail` の登録と重なり `409` を検証する

## 2. フロントエンド

- [ ] 2.1 `types.ts`・`lib/api.ts` に出退勤実績と人事メール条件を追加し、`pnpm run build` の型チェックが通ることを確認する
- [ ] 2.2 `lib/mail.ts` に `{{attendance_start}}`・`{{attendance_end}}`（未登録は「未取込」）を追加し、`mail.test.ts` に登録済み・未取込のケースを追加して通す
- [ ] 2.3 `TodayReport.tsx` に出退勤（人事メール）行（時刻・登録元・取込日時・未取込・休暇の表示）と「手入力」ダイアログ（`HH:MM`・区分）を追加する。Testing Library で未取込表示と手入力の保存（`source=manual`）を検証する
- [ ] 2.4 `SettingsPanel.tsx` に人事メールの差出人・件名キーワードを追加し、画面で保存・再読込できることを確認する

## 3. agent：共通基盤

- [ ] 3.1 `agent/`（`pyproject.toml`・`laborman_agent/`・`tests/`）を作成し、ルート `pyproject.toml` の workspace members に追加する。`uv sync` 後に `uv run laborman-agent --help` が表示されることを確認する
- [ ] 3.2 `config.py`：`~/.config/laborman-agent/config.toml` の読み込み、セレクタ・解析規則の既定値と上書き、権限 `600` 以外での警告を実装し、pytest で既定値・上書き・権限警告を検証する
- [ ] 3.3 `business_days.py`：前営業日の算出（土日・`jpholiday`）と `--date` の解釈を実装し、pytest で月曜・祝日明け・連休明けを検証する
- [ ] 3.4 `lock.py`（`flock`）・`notify.py`（`osascript`、本文を含めない）・`logs.py`（ディレクトリ `700`・ファイル `600`・期限削除）を実装し、pytest で二重取得の失敗・期限削除・権限を検証する（通知はコマンド生成のみを検証）
- [ ] 3.5 `api_client.py`（httpx）で health・報告取得・`PUT attendance`・休憩一覧/追加・自動化設定取得を実装し、接続失敗を終了コード 1 にする。`httpx.MockTransport` で pytest を書いて通す

## 4. agent：人事メールの取込

- [ ] 4.1 `owa/parser.py` を実装する（NFKC 正規化、`line_pattern`、休憩の時間帯/分数、`leave_keywords`、対象日なしは失敗）。仕様書 §7.3 の想定書式で合成フィクスチャを作り、勤務・休暇・休憩の時間帯/分数・全角数字・複数日・対象日なしを pytest で検証する
- [ ] 4.2 `owa/fetch.py` の Page Object（サインイン画面検知・検索・実行日受信の先頭を開く・本文取得、セレクタは設定から）を実装する。`tests/fixtures/owa/*.html` の静的モックに対し Playwright で、本文取得・メールなし・サインイン画面検知を pytest で検証する
- [ ] 4.3 `cli.py` に `login owa`（`headless=False`・プロファイル `700`）、`fetch-attendance [--date]`（design D7 の流れと終了コード）、`doctor` を実装する。API と OWA をモックした pytest で、取込成功 0・未着 2・解析失敗 3（本文がログに保存され DB 不変）・`manual` スキップ 0・ロック中 0 を検証する

## 5. ドキュメント

- [ ] 5.1 `docs/API_REFERENCE.md`・`DATABASE_SCHEMA.md`・`ARCHITECTURE.md`（エージェントの配置図）・`SETUP_GUIDE.md`（agent の導入・`config.toml`・`login owa`・`doctor`・FileVault 前提）と `agent/README.md` を更新する

## 6. 検証

- [ ] 6.1 `uv run pytest`（backend・agent）、`ruff`・`mypy`、`cd frontend && pnpm test && pnpm run build` がすべて成功することを確認する
- [ ] 6.2 人事メールの匿名化サンプル（仕様書 §13-1）を 5 件以上 `agent/tests/fixtures/hr_mail/` に追加し、既定の解析規則を確定してパーサのテストが通ることを確認する
- [ ] 6.3 実環境で `laborman-agent login owa` → `doctor` が成功し、`fetch-attendance` で前営業日の出退勤が laborman の画面に表示されることを確認する
- [ ] 6.4 実環境で、メール未着時に終了コード 2 になり、手入力済みの日に `fetch-attendance` を実行しても値が変わらないことを確認する
- [ ] 6.5 `openspec validate add-attendance-import --strict --no-interactive` が成功することを確認する
