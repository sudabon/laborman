# Design

## Context

- `add-work-tasks-and-breaks` により `work_tasks`・`work_breaks`（`source` 列あり）・`jobs`・`automation_settings`（既定休憩のみ）、`app_timezone`、`parseWorkTime`/`formatWorkTime` が存在する前提。
- backend は Docker コンテナ内で動き、`127.0.0.1:8888` でのみ公開される。社内の Microsoft 365 は管理者承認が得られないため Graph API・IMAP は使えず、Outlook on the web（OWA）の画面を読むしかない。
- 振る舞いは specs/、全体設計の出典は `ZAC_AUTOMATION_SPEC.md`（§3 の設計判断 D1・D2・D5、§7）。

## Goals / Non-Goals

**Goals:**

- 出退勤実績のデータモデルと API を、Phase 3 の zac ドラフト算出がそのまま使える形で確定する
- `agent/` の共通基盤（設定・API クライアント・前営業日・ロック・通知・終了コード・ログ）を、Phase 3 の `run`・`register` が再利用できる形で作る
- 人事メールの書式（2026-10-13 に実メールで確認済み）を既定の解析規則とし、書式が変わってもコード修正なしで設定から差し替えられるようにする

**Non-Goals:**

- zac の操作、`run`・`register`・`login zac`、launchd 登録（`add-zac-draft-and-registration` で扱う）
- Slack 通知（macOS 通知のみ。必要になれば Phase 3 以降で追加）
- 実在の人事メール・OWA への自動テストでの接続（テストは静的モックのみ）
- 人事メールからの休憩の取込（メールに休憩の記載がない。休憩は laborman の手入力のみ）
- 休暇の自動判定（休暇の日はメールが届かない。休暇は UI で手入力する）
- 休日出勤・半休の特別扱い（休日出勤は対象外、半休はメールの出退勤をそのまま使う）
- 直行・直帰の移動時間（zac の画面確認後に Phase 3 で扱う）

## Decisions

### D1. `work_reports` への列追加

仕様書 §5.4 の `attendance_start_at`・`attendance_end_at`（`timestamptz NULL`）、`attendance_source`（`varchar(16) NULL`, `CHECK in ('hr_mail','manual')`）、`attendance_kind`（`varchar(16) NOT NULL DEFAULT 'work'`, `CHECK in ('work','leave')`）、`attendance_imported_at`（`timestamptz NULL`）を追加する。`zac_registered_at` は Phase 3 で追加する。

人事メールに休憩の記載がないため、休憩分数の列（旧案の `attendance_break_minutes`）は持たない。区分 `leave` は人事メールからは来ず、UI の手入力（`source=manual`）でのみ登録される。

### D2. `PUT /api/work-reports/{date}/attendance`

- 本文：`{ start_at, end_at, source: "hr_mail"|"manual", kind: "work"|"leave" }`。報告がなければ get-or-create。`source=hr_mail` かつ `kind=leave` は `422`（人事メールから休暇は来ないため）。
- 検証：`kind=work` は `start_at`・`end_at` 必須かつ `end_at > start_at`、時刻は勤務日 00:00〜翌 06:00（Phase 1 と同じ範囲）。`kind=leave` は時刻を空にできる。違反は `422`。
- `source=hr_mail` かつ既存の `attendance_source=manual` の場合は `409`（`detail.message` のみ、値は変えない）。`source=hr_mail` のとき `attendance_imported_at = now`、`manual` のときは変更しない。
- 応答は更新後の `WorkReportRead`。`WorkReportRead` に `attendance_*` を追加する（既存クライアントは未知の項目を無視するため互換）。

**代替案**：`PATCH /work-reports/{date}` に相乗りする案は、`manual` 保護の 409 と通常の更新の区別が曖昧になるため採らない。

### D3. 人事メールの書式と休暇の扱い

2026-10-13 受信の実メールで次を確認した。

- 件名 `[勤怠情報]2026/10/09:開始08:29/終了18:38`。1 通 = 1 勤務日で、件名に年付きの対象日・開始・終了がそろっている。
- 本文は `対象日`・`開始時間`・`終了時間`・`残業時間` のラベルと値が別の行。`残業時間` は月の累計の目安のため使わない。休憩の記載はない。
- 対象日の翌営業日に届き、土日祝は届かない。休暇の日（事前申請済み）は届かない。
- 差出人は人事担当者の個人アドレス。担当交代で変わり得るため、検索の主条件は件名キーワードとし、差出人は任意の追加条件にする。

このため、休憩 API への `source=hr_mail` の追加（旧案）は行わない。休暇は「メールが来ない」ことでしか表れず未着と区別できないので、ユーザーが UI で区分「休暇」を手入力し、エージェントは `manual` の日を取込対象外とする（D7 の手順 2）。

### D4. `agent/` のパッケージ構成と依存

仕様書 §7.1 の構成に従い、Phase 2 では `cli.py`・`config.py`・`api_client.py`・`business_days.py`・`lock.py`・`notify.py`・`logs.py`・`owa/fetch.py`・`owa/parser.py` を作る。

- Python 3.12、`uv` の workspace member としてルート `pyproject.toml` の `members` に `agent` を追加。エントリポイント `laborman-agent = "laborman_agent.cli:main"`。
- 依存：`playwright`（ブラウザ操作）、`httpx`（API）、`jpholiday`（祝日）。設定は標準ライブラリ `tomllib`、CLI は `argparse`。
- backend の依存・イメージには一切追加しない（仕様書 D1：ブラウザ自動化はホストのみ）。

### D5. OWA の取得（`owa/fetch.py`）

- Playwright の `launch_persistent_context(profile_dir/owa, channel=config.browser.channel, headless=...)` で専用プロファイルを使う。条件付きアクセスで同梱 Chromium が弾かれる場合に備え、`channel`（`chrome`/`msedge`）を設定で切り替える。
- 手順：OWA を開く → サインイン画面（URL が `login.microsoftonline.com` 等、または設定のセレクタ）を検知したら `needs_login`（終了コード 3）→ 検索ボックスに `search_query`（件名キーワード＋対象日 `YYYY/MM/DD`、差出人は設定時のみ）を入力 → 結果の件名を読み、対象日の件名に一致する先頭の結果を採る。受信日では絞り込まない。件名で解析できればメールを開かずに済ませ、できなければそのメールを開いて本文の `inner_text` を取得する。一致する結果がなければ終了コード 2。
- OWA の検索が `[` `]` 等の記号を無視して余分な結果を返しても、件名の解析で対象日を照合するため誤取込にはならない。
- セレクタは既定値をコードに持ち、`[owa.selectors]` で上書きする（OWA の画面変更にコード修正なしで追従するため）。
- `login owa` は同じプロファイルを `headless=False` で開き、利用者がブラウザを閉じるまで待つ。プロファイルディレクトリは `700` で作成する。

### D6. 本文の解析（`owa/parser.py`）

- 入力は件名・本文テキスト（本文は任意）と対象日、出力は `AttendanceRecord(start, end)` または解析失敗。I/O を持たない純粋関数とし、フィクスチャで単体テストする。
- 前処理で `unicodedata.normalize("NFKC")` により全角数字・コロン・スラッシュを半角化する。
- 規則は設定 `[owa.parser]` で与え、既定値は仕様書 §7.3 のとおり：件名は `subject_pattern`（名前付きグループ `date`・`start`・`end`）、本文は `body_date_pattern`・`body_start_pattern`・`body_end_pattern`（ラベルの後の空白・改行を `\s*` で許容）。件名を先に試し、だめなら本文を試す。
- 抽出した `date` が対象日と一致しなければ失敗とする（別の日のメールを誤って取り込まないため）。開始・終了は勤務日基準の時刻として扱う。
- フィクスチャは実メールから氏名（宛名）を除いた匿名化サンプルを使う（5 件以上）。

### D7. `fetch-attendance` の流れと終了コード

1. ロック取得（取れなければ終了コード 0）→ ログの期限削除 → 対象日の決定
2. `GET /api/work-reports/{date}`。`attendance_source=manual` なら「手入力済みのためスキップ」で終了コード 0（OWA を開かない）
3. OWA から本文取得（未着 2、サインイン切れ 3）→ 解析（失敗は本文をログに保存して 3）
4. `PUT attendance`（`409` は手入力済みとして 0）→ 結果を出力・必要なら通知

手順 2 の `manual` には区分「休暇」の手入力も含むため、休暇の日は OWA を開かずに終わる。未着（終了コード 2）の出力と通知には「休暇の日なら UI で休暇として登録してください」と添える。

想定外の例外は終了コード 1 とし、スタックトレースはログに出すがメール本文は出さない。

### D8. ロック・通知・ログ

- ロック：`~/Library/Application Support/laborman-agent/agent.lock` を `fcntl.flock(LOCK_EX | LOCK_NB)` で取得。プロセス終了で自動解放されるため、異常終了時の残留ロックが起きない。
- 通知：`osascript -e 'display notification ...'`。対象日と結果の要約のみを載せる。
- ログ：`~/Library/Logs/laborman-agent/`（`700`）。解析失敗時の本文は `hr_mail/<日時>.txt`（`600`）。起動ごとに `retention_days`（既定 14）より古いファイルを削除する。

### D9. 人事メールの検索条件

`automation_settings` に `hr_mail_from`・`hr_mail_subject_keyword`（`text NOT NULL DEFAULT ''`）を追加し、設定画面で編集する。実運用の件名キーワードは `[勤怠情報]`。エージェントは `GET /api/automation-settings` から読み、設定ファイルの `search_query` テンプレート（`{from_clause}`・`{hr_mail_subject_keyword}`・`{target_date}`）に埋め込む。差出人は任意で、空なら `from_clause` を空にする。件名キーワードが空の場合は検索せず、終了コード 3（設定不足）とする。

## Risks / Trade-offs

- [条件付きアクセスで自動操作のブラウザからサインインできない（§13-6）] → `channel` を Chrome / Edge に切り替えられるようにする。それでも不可なら Phase 2 のエージェント部分は保留し、UI の手入力のみで運用する（backend・UI は単独で価値がある）
- [人事メールの書式が将来変わる] → 解析規則を設定で差し替え可能にし、解析失敗は終了コード 3 と通知で早期に気付けるようにする
- [休暇の手入力を忘れた日に、未着（終了コード 2）が繰り返される] → 未着の出力・通知で休暇登録を案内する。データは壊れない
- [OWA の画面変更でセレクタが壊れる] → セレクタを設定で上書き可能にし、`doctor` と解析失敗の通知で早期に気付けるようにする
- [ブラウザプロファイルにセッション Cookie が残る] → 権限 `700`、FileVault 前提を `SETUP_GUIDE.md` に明記する
- [手入力済みの日に誤った人事メールの値が来ても気付けない] → 手入力を優先する仕様どおりとし、スキップした旨を出力に残す

## Migration Plan

1. Alembic マイグレーションで `work_reports` に列を追加（既存行は NULL、`attendance_kind='work'`）し、`automation_settings` に列を追加する
2. `task build && task start` で backend・SPA を更新する
3. ホストで `uv sync`（workspace）→ `uv run --directory agent playwright install chromium`（または Chrome を使う設定）→ `config.toml` を作成（`600`）→ `laborman-agent login owa` → `laborman-agent doctor`
4. ロールバック：`alembic downgrade -1` で列を削除。エージェントは使わなければ影響しない

## Open Questions

- 人事メールが届く時刻（仕様書 §13-1）：Phase 3 の定時実行の時刻（9:20 ほか）が妥当かの確認に使う
- OWA へのサインイン方式と、自動操作のブラウザが条件付きアクセスを通るか（§13-6）：`browser.channel` の既定値に影響する
- OWA の検索で `subject:"[勤怠情報]2026/10/09"` が意図どおり絞り込めるか：実環境で確認し、必要なら `search_query` を調整する（照合は件名の解析で行うため安全側）
- 日をまたぐ勤務の表記（§13-7）：`終了時間` が `24:xx` 以上で来るか、翌日の時刻で来るか
