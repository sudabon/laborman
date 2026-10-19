# Tasks

## 1. backend：データモデル

- [x] 1.1 `automation_settings` に zac 連携の列（CHECK 制約・`default_job_code` の FK 付き）、`work_reports.zac_registered_at`、`zac_sync_runs` を追加し、Alembic マイグレーションを作成する。Docker の PostgreSQL で `upgrade` → `downgrade -1` → `upgrade` が成功することを確認する
- [x] 1.2 `GET/PUT /api/automation-settings` を新しい項目に対応させる（`assign_default_job` で既定ジョブ必須、丸め単位の制約）。pytest で初期値と `422` を検証する

## 2. backend：ドラフト算出

- [x] 2.1 `zac_draft.py` に出退勤・範囲内の休憩・クリップ・実働・空き時間の算出を実装する。pytest で許容値以内／超過のクリップ、休憩のはみ出し、`block`／`assign_default_job`、`24:xx` を含む日を検証する
- [x] 2.2 `duration`（最大剰余法・内容の連結と切り詰め）と `time_range`（連続する同一行の結合）の入力行生成を実装する。pytest で仕様書の計算例（519 分 → JOB-A 300・JOB-B 210）、同値の剰余、合計一致を検証する
- [x] 2.3 検証コード一式（`ATTENDANCE_MISSING`〜`ALREADY_REGISTERED`）と `registrable`・`auto_allowed`、休憩の記録漏れ（`BREAK_MISSING`）を実装する。pytest で各コードの発生条件と、休憩 0 件の日が登録不可になり休憩レコードが作られないことを検証する
- [x] 2.4 `GET /api/work-reports/{date}/zac-draft` を実装し、pytest で応答の形（仕様書 §4.6 のレスポンス例）と DB が変わらないことを検証する

## 3. backend：実行履歴と zac 状態

- [x] 3.1 `GET/POST /api/zac-sync-runs`・`PATCH /api/zac-sync-runs/{id}` を実装し、`succeeded` で `zac_registered_at` を設定する。pytest で状態遷移と `zac_registered_at` の設定を検証する
- [x] 3.2 `WorkReportRead` と月一覧に `zac_registered_at`・`zac_status` を追加し、最新 run を 1 クエリで取得する。pytest で `registered`・`needs_action`・`null` の導出と、月一覧のクエリ数が日数に比例しないことを検証する
- [x] 3.3 実行依頼の API（`POST /api/zac-sync-runs/requests`・`/{id}/claim`・`/{id}/cancel`、状態 `requested`・`cancelled` の追加）を実装する。pytest で依頼の作成、同日の重複依頼の `409`、`claim` の二重取得の `409`、取り消し（`requested` 以外は `409`）を検証する

## 4. フロントエンド

- [x] 4.1 `types.ts`・`lib/api.ts` にドラフト・実行履歴・zac 設定を追加し、`pnpm run build` の型チェックが通ることを確認する
- [x] 4.2 `TodayReport.tsx` に zac 登録パネル（入力行・実働・検証結果（`BREAK_MISSING` 等の error を目立たせる）・最新の実行結果）を追加し、業務明細・出退勤の変更後に再取得する。Testing Library で API 応答どおりに表示されることを検証する
- [x] 4.3 `ReportCalendar.tsx` に「zac済」「要対応」と zac 未登録の過去平日の強調を追加し、Testing Library で各表示を検証する
- [x] 4.4 `SettingsPanel.tsx` に「業務明細・zac」セクション（モード・入力形式・丸め単位・許容値・空き時間の扱い・既定ジョブ・内容の最大長）を追加し、画面で保存・再読込できることを確認する
- [x] 4.5 zac 登録パネルに「この日を zac に登録」ボタン（zac 登録済みの日は無効）、依頼中・実行中の表示と取り消し、10 秒ごとの状態更新を追加する。Testing Library で依頼の送信、`409` の表示、取り消し、結果の反映を検証する

## 5. agent：zac の操作

- [x] 5.1 `zac/report_page.py` の Page Object を design D6・D12 の対応表で実装する（業務報告画面の URL、出社・退社、休憩の時間数を時間帯で分けて入力、作業登録のダイアログで作業内容・案件（JOB 番号で検索）・売上項目・所要時間・備考を完全一致で選んで登録、既存入力（工数の行・「日報確定済」）の検知、「保存」だけを押す、保存完了・エラーの検知、サインイン画面の検知とキーチェーンのパスワードでのサインイン）。`tests/fixtures/zac/*.html` の静的モック（未入力の日・既存入力あり・確定済み・作業登録のダイアログ・保存完了・エラー・サインイン画面）に対し Playwright で、入力内容・休憩の分割・選択肢がないときの中止・「確定」を押さないこと・既存入力の検知を pytest で検証する
- [x] 5.2 `api_client.py` に zac-draft・zac-sync-runs の操作を追加し、`httpx.MockTransport` で pytest を書いて通す
- [x] 5.3 `runner.py` に design D5 のフローを実装する（人事メール取込の再利用、`auto` の降格、`assist` の待機、スクリーンショット `600`、最終回のみの再試行通知）。API・OWA・zac をモックした pytest で D5 の表の全行（状態と終了コード）を検証する
- [x] 5.4 `cli.py` に `run`・`register`・`login zac` を追加し、`doctor` に zac の到達性とプロファイルの確認を追加する。pytest で引数の解釈と、VPN 未到達時の `doctor` の終了コード 3 を検証する
- [x] 5.5 `cli.py` に `process-requests` を追加する（依頼を古い順に `claim` し、成功したものだけ D5 の流れを依頼の行に記録しながら実行、依頼なしはブラウザを起動せず 0、ロック共有）。API・OWA・zac をモックした pytest で、依頼なし・1 件実行・`claim` 競合でスキップ・ロック中を検証する

## 8. 作業内容・案件・売上項目（2026-10-14 の zac 画面確認による追加）

- [x] 8.1 `zac_sales_items`・`zac_work_kinds` を作成し、`work_tasks` に `work_kind`・`sales_item_id`、`jobs` に `series_name`・`valid_month`、`automation_settings` に既定の作業内容・既定の売上項目を追加する Alembic マイグレーションを作成する。年月表記の読み取り（`parse_valid_month`）を実装する。Docker の PostgreSQL で `upgrade` → `downgrade -1` → `upgrade` が成功し、既存のタスクが変わらないことを確認する。pytest で年月表記の各形式（範囲は対象年月なし）を検証する
- [x] 8.2 売上項目・作業内容の API（一覧・追加・更新〔無効化〕）、`POST /api/zac-masters/import`（追加・更新のみ、シリーズ名と対象年月の導出、今回現れなかった件数の応答）、タスクの作成・更新での `work_kind`・`sales_item_id`（別のジョブの売上項目は 422）を実装する。pytest で各 API、取込の冪等性、候補から消えた案件を無効化しないこと、422 を検証する
- [x] 8.3 `zac_draft.py` の入力行を「作業内容・ジョブ・売上項目」ごとにまとめ、備考を「- 内容」の改行区切りにし、`JOB_MONTH_MISMATCH`・`WORK_KIND_MISSING`・`SALES_ITEM_MISSING`（error）・`SALES_ITEM_MONTH_MISMATCH`（warning）を追加する。`assign_default_job` で既定の作業内容・既定の売上項目を使う。pytest で仕様のシナリオ（作業内容が違えば別の行、箇条書き、各コード）と既存の計算例を検証する
- [x] 8.4 業務明細の入力を「ジョブ（シリーズはまとめて表示し、勤務日の年月で解決）→ 売上項目 → 作業内容 → 内容 → 開始 → 終了」にし、design D11 の初期値を入れる。一覧・行の編集・zac パネルに作業内容・売上項目を表示する。設定画面のジョブマスタに売上項目・シリーズ名・対象年月・既定の作業内容、作業内容の一覧を追加する。Testing Library で初期値（年月一致・前回値・1 件のみ・計上済みの除外）、シリーズの解決と未登録時の保存拒否、売上項目の選択を検証する
- [x] 8.5 `[zac] login_id`・`keychain_service` を設定に追加し、`security find-generic-password` でパスワードを読み出す関数と `doctor` の登録確認（値は表示しない）を実装する。pytest（`security` はモック）で、読み出し・未登録時の `needs_login`・パスワードがログ・例外・実行履歴・通知に含まれないことを検証する
- [x] 8.6 `laborman-agent sync-zac` を実装する（読み取り専用の `ZacMasterReader` で作業内容・案件の候補・案件ごとの売上項目と「売上計上済」を読み、キャンセルで閉じてから取込 API に送る）。静的モックに対し Playwright で、読み取り結果と「登録」「保存」「確定」を一度も押さないことを pytest で検証する
- [x] 8.7 `backend/seed/zac_masters_2026-10-14.json` を取込 API で実環境の laborman に投入し、設定画面と業務明細の候補に表示されることを確認する

## 6. 定時実行・ドキュメント

- [x] 6.1 `agent/launchd/jp.sudabon.laborman-agent.plist.example`（平日 9:20・10:20・11:20・13:20）と `jp.sudabon.laborman-agent.requests.plist.example`（`process-requests` を 60 秒間隔）を追加し、`plutil -lint` が成功することを確認する
- [x] 6.2 `docs/API_REFERENCE.md`・`DATABASE_SCHEMA.md`・`ARCHITECTURE.md`・`SETUP_GUIDE.md`（zac のセレクタ採取、`login zac`、launchd の導入・解除）と `agent/README.md`（段階運用のランブック）を更新する あわせて `sync-zac`・キーチェーンへのパスワード登録・期替わりで JOB 番号が払い出されたときの手順（zac の画面を確認 → `sync-zac` → 旧ジョブの無効化）と、`ZAC_AUTOMATION_SPEC.md` §13 の確認結果（§13-2・§13-9 の一部）を記載する

## 7. 検証

- [x] 7.9 実環境で `sync-zac` を実行し、zac に何も保存されずに laborman のマスタが更新されることと、キーチェーンのパスワードで翌日のセッション切れからサインインできることを確認する

- [x] 7.1 `uv run pytest`（backend・agent）、`ruff`・`mypy`、`cd frontend && pnpm test && pnpm run build` がすべて成功することを確認する
- [x] 7.2 実画面で、UI の zac パネルと `GET zac-draft` の応答が同じドラフト・検証結果であることを確認する
- [x] 7.3 zac の画面仕様（仕様書 §13-2）確認後、実画面のセレクタ・URL を設定し、`run --mode dry_run --headed` で zac に入力され、保存されずにスクリーンショットが残ることを確認する
- [x] 7.4 実画面で `assist` により人が保存すると `succeeded` が記録され、カレンダーに「zac済」が出ることを確認する
- [ ] 7.5 zac に既存入力がある日と `warning` のある日に、`auto` で保存されないことを確認する（社内規程の確認〔§13-4〕は 2026-10-15 に済み。既存入力のガードは 2026-10-15 に確認済み）
- [x] 7.6 launchd を導入し、起動されることをログで確認する（2026-10-15、利用者の判断で依頼の処理〔`jp.sudabon.laborman-agent.requests`、60 秒ごと〕だけを導入。平日朝の `run` は導入しない。人事メールが届いたら画面のボタンで依頼し、依頼の処理が人事メールの取込から行う）
- [x] 7.7 `openspec validate add-zac-draft-and-registration --strict --no-interactive` が成功することを確認する
- [x] 7.8 実画面で「この日を zac に登録」を押し、1 分程度で `process-requests` が依頼を実行して結果（`dry_run_done` など）がパネルに表示されることを確認する

## 9. 実環境の確認で見つかった改善（2026-10-15〜16）

- [x] 9.1 zac は作業登録のたびに勤怠欄を入れ直すため、出社・退社を工数明細のあとに入力し、入力後に値を読み返す
- [x] 9.2 選択肢が見つからないときに、スクリーンショットとそのとき出ていた選択肢をログに残す
- [x] 9.3 出退勤の登録・更新時に、最初のタスクの開始・最後のタスクの終了を出退勤に合わせる（ずれ 30 分以内）
- [x] 9.5 zac のサインインを実画面（`/b/auth/login`、action のない Angular のフォーム）に合わせ、サインイン後の移動を待ってから開き直す。パスワードが読めない場合とサインインに失敗した場合のメッセージを分ける（2026-10-19、実画面で確認済み）
- [x] 9.6 選択肢を開いた直後は空の項目だけで、あとから読み込まれる（サインイン直後に発生。10/15・10/16 の「作業内容が選択肢にない」の原因）。名前のある項目が出て件数が落ち着くまで待って読む
- [ ] 9.4 実画面で、人事メールの取込後に業務明細の最初・最後の時刻が出退勤に合うことを確認する
