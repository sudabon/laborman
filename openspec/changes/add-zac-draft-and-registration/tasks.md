# Tasks

## 1. backend：データモデル

- [ ] 1.1 `automation_settings` に zac 連携の列（CHECK 制約・`default_job_code` の FK 付き）、`work_reports.zac_registered_at`、`zac_sync_runs` を追加し、Alembic マイグレーションを作成する。Docker の PostgreSQL で `upgrade` → `downgrade -1` → `upgrade` が成功することを確認する
- [ ] 1.2 `GET/PUT /api/automation-settings` を新しい項目に対応させる（`assign_default_job` で既定ジョブ必須、丸め単位の制約）。pytest で初期値と `422` を検証する

## 2. backend：ドラフト算出

- [ ] 2.1 `zac_draft.py` に出退勤・範囲内の休憩・クリップ・実働・空き時間の算出を実装する。pytest で許容値以内／超過のクリップ、休憩のはみ出し、`block`／`assign_default_job`、`24:xx` を含む日を検証する
- [ ] 2.2 `duration`（最大剰余法・内容の連結と切り詰め）と `time_range`（連続する同一行の結合）の入力行生成を実装する。pytest で仕様書の計算例（519 分 → JOB-A 300・JOB-B 210）、同値の剰余、合計一致を検証する
- [ ] 2.3 検証コード一式（`ATTENDANCE_MISSING`〜`ALREADY_REGISTERED`）と `registrable`・`auto_allowed`、既定休憩の提案を実装する。pytest で各コードの発生条件と、提案時に休憩レコードが作られないことを検証する
- [ ] 2.4 `GET /api/work-reports/{date}/zac-draft` を実装し、pytest で応答の形（仕様書 §4.6 のレスポンス例）と DB が変わらないことを検証する

## 3. backend：実行履歴と zac 状態

- [ ] 3.1 `GET/POST /api/zac-sync-runs`・`PATCH /api/zac-sync-runs/{id}` を実装し、`succeeded` で `zac_registered_at` を設定する。pytest で状態遷移と `zac_registered_at` の設定を検証する
- [ ] 3.2 `WorkReportRead` と月一覧に `zac_registered_at`・`zac_status` を追加し、最新 run を 1 クエリで取得する。pytest で `registered`・`needs_action`・`null` の導出と、月一覧のクエリ数が日数に比例しないことを検証する

## 4. フロントエンド

- [ ] 4.1 `types.ts`・`lib/api.ts` にドラフト・実行履歴・zac 設定を追加し、`pnpm run build` の型チェックが通ることを確認する
- [ ] 4.2 `TodayReport.tsx` に zac 登録パネル（入力行・実働・検証結果・既定休憩の提案・最新の実行結果）を追加し、業務明細・出退勤の変更後に再取得する。Testing Library で API 応答どおりに表示されることを検証する
- [ ] 4.3 `ReportCalendar.tsx` に「zac済」「要対応」と zac 未登録の過去平日の強調を追加し、Testing Library で各表示を検証する
- [ ] 4.4 `SettingsPanel.tsx` に「業務明細・zac」セクション（モード・入力形式・丸め単位・許容値・空き時間の扱い・既定ジョブ・内容の最大長）を追加し、画面で保存・再読込できることを確認する

## 5. agent：zac の操作

- [ ] 5.1 `zac/report_page.py` の Page Object（design D6 の操作のみ、セレクタ・URL は設定から）を実装する。`tests/fixtures/zac/*.html` の静的モックに対し Playwright で、`duration`／`time_range` の入力、既存入力の検知、保存完了の検知、エラー表示の検知、ログイン画面の検知を pytest で検証する
- [ ] 5.2 `api_client.py` に zac-draft・zac-sync-runs の操作を追加し、`httpx.MockTransport` で pytest を書いて通す
- [ ] 5.3 `runner.py` に design D5 のフローを実装する（人事メール取込の再利用、`auto` の降格、`assist` の待機、スクリーンショット `600`、最終回のみの再試行通知）。API・OWA・zac をモックした pytest で D5 の表の全行（状態と終了コード）を検証する
- [ ] 5.4 `cli.py` に `run`・`register`・`login zac` を追加し、`doctor` に zac の到達性とプロファイルの確認を追加する。pytest で引数の解釈と、VPN 未到達時の `doctor` の終了コード 3 を検証する

## 6. 定時実行・ドキュメント

- [ ] 6.1 `agent/launchd/jp.sudabon.laborman-agent.plist.example`（平日 9:20・10:20・11:20・13:20）を追加し、`plutil -lint` が成功することを確認する
- [ ] 6.2 `docs/API_REFERENCE.md`・`DATABASE_SCHEMA.md`・`ARCHITECTURE.md`・`SETUP_GUIDE.md`（zac のセレクタ採取、`login zac`、launchd の導入・解除）と `agent/README.md`（段階運用のランブック）を更新する

## 7. 検証

- [ ] 7.1 `uv run pytest`（backend・agent）、`ruff`・`mypy`、`cd frontend && pnpm test && pnpm run build` がすべて成功することを確認する
- [ ] 7.2 実画面で、UI の zac パネルと `GET zac-draft` の応答が同じドラフト・検証結果であることを確認する
- [ ] 7.3 zac の画面仕様（仕様書 §13-2）確認後、実画面のセレクタ・URL を設定し、`run --mode dry_run --headed` で zac に入力され、保存されずにスクリーンショットが残ることを確認する
- [ ] 7.4 実画面で `assist` により人が保存すると `succeeded` が記録され、カレンダーに「zac済」が出ることを確認する
- [ ] 7.5 zac に既存入力がある日と `warning` のある日に、`auto` で保存されないことを確認する（社内規程の確認〔§13-4〕前は `auto` の実保存を行わず、既存入力・warning のガードのみ確認する）
- [ ] 7.6 launchd を導入し、平日朝に起動されること、完了済みの日がスキップされることをログで確認する
- [ ] 7.7 `openspec validate add-zac-draft-and-registration --strict --no-interactive` が成功することを確認する
