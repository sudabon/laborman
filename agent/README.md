# laborman-agent

laborman のホスト側 CLI です。Outlook on the web（OWA）で人事の出退勤メールを検索し、件名（だめなら本文）から出退勤を読み取って laborman API に登録します。利用者の Mac で動かし、laborman のデータには HTTP API 経由でのみアクセスします。

導入手順・設定ファイル・終了コードは [docs/SETUP_GUIDE.md](../docs/SETUP_GUIDE.md#laborman-agent人事メールから出退勤を取り込む) を参照してください。

## コマンド

| コマンド | 説明 |
|---------|------|
| `laborman-agent login owa\|zac` | 画面付きブラウザで手動サインインし、専用プロファイル（`700`）にセッションを保存 |
| `laborman-agent fetch-attendance [--date YYYY-MM-DD]` | 対象日（既定は前営業日）の人事メールを取り込む |
| `laborman-agent run [--date D] [--mode M] [--headed] [--force]` | 人事メールの取込（未取込のときだけ）から zac への入力・保存まで |
| `laborman-agent register [--date D] [--mode M] [--headed] [--force]` | 人事メールを取り込まずに zac への入力・保存だけ |
| `laborman-agent process-requests` | 画面の「この日を zac に登録」の依頼を古い順に実行（launchd から 60 秒ごと） |
| `laborman-agent sync-zac [--date D]` | zac の作業登録から作業内容・案件・売上項目の選択肢を読み、laborman のマスタに追加・更新（zac には保存しない。読み取りに使う日は未確定の日） |
| `laborman-agent doctor` | 設定ファイル・API・人事メールの条件・プロファイル・ブラウザ・zac への到達性を診断（失敗があれば終了コード 3） |

共通オプション：`--config PATH`（既定 `~/.config/laborman-agent/config.toml`）。

## `fetch-attendance` の流れ

1. ロックを取得（実行中なら何もせず 0）、ログの期限削除、対象日の決定
2. `GET /api/work-reports/{date}`。登録元が `manual`（休暇を含む）なら OWA を開かずに 0
3. `GET /api/automation-settings` の件名キーワード・差出人で OWA を検索（`subject:"[勤怠情報]2026/10/09"`）。受信日では絞り込まず、件名の日付で照合する
4. 件名を解析。書式に合わなければそのメールを開いて本文を解析（`残業時間` は使わない）
5. `PUT /api/work-reports/{date}/attendance`（`source=hr_mail`）。`409`（手入力済み）は 0

メールが見つからなければ 2（休暇の日なら UI で休暇として登録するよう案内）。サインイン切れ・解析失敗・画面を認識できない場合は 3 で、macOS 通知を出します（通知に本文は含めません）。

## `run` の流れと記録する状態

1. zac 登録済みの日は何もせず 0（`--force` で無視）
2. 実行履歴を `running` で記録（画面からの依頼は取得済みの行を使う）
3. zac に到達できなければ `vpn_unreachable`（2）。出退勤が未取込なら人事メールを取り込み、未着は `hr_mail_not_found`（2）
4. ドラフトに error があれば `validation_failed`（3）。warning があれば `auto` を `dry_run` に降格して通知
5. zac を開き、サインイン画面なら `needs_login`（3）、既存の入力があれば `already_registered_in_zac`（3。上書きしない）
6. 工数明細を入力したあとで出退勤を入力し（zac は明細の追加ごとに勤怠欄を入れ直す）、休憩は休憩専用のフォームに入力してスクリーンショット（`600`）。入力後に勤怠欄の値を読み返し、入らなければ `failed`
7. `dry_run` は保存せず `dry_run_done`（0）。ただし zac は工数明細を自動保存するので、明細は zac に残る（やり直すときは zac で明細を削除する）。`assist` は人の保存を最大 15 分待ち、保存完了を確認できれば `succeeded`、時間切れは `awaiting_user`（3）。`auto` は保存して完了表示を確認できれば `succeeded`、できなければ `failed`（3）

「申請」「承認依頼」は操作しません。VPN 未接続・メール未着の通知は `[schedule] notify_retry_after`（既定 13:00）以降の起動と、画面からの依頼のときだけ出します。


## zac の画面とサインイン

- 業務報告画面は `{base_url}/b/daily_report/{YYYY-MM-DD}`。入力欄は Angular の `formcontrolname` で特定する（既定のセレクタは `config.py` の `DEFAULT_ZAC_SELECTORS`。画面が変わったら `[zac.selectors]` で上書き）。
- 勤怠欄：出社・退社時刻に出退勤実績、休憩は**時間数**で「休憩」「休憩（22〜24時）」「休憩（24〜29時）」に分けて入れる。
- 工数：入力行ごとに「作業登録」を開き、作業内容 → 案件（JOB 番号で検索）→ 売上項目を**表示名の完全一致**で選び、所要時間（H:MM）と備考（「- 内容」の改行区切り）を入れて「登録」。一致する選択肢がなければ入力を中止して `failed`（保存しない）。
- 「保存」だけを押す。「確定」「確定解除」「月報確定」は押さない（確定は利用者が zac で行う）。zac は保存しても画面にメッセージを出さないので、保存完了は保存の通信（`POST …/daily_reports/{date}/save`）の成功（2xx）か「日報確定済」の表示で判定する（4xx・5xx は失敗）。`assist` で利用者が押した「保存」も同じ方法で検知する。
- **zac は同じアカウントで同時に 1 か所しかログインできない。** エージェントがサインインすると、利用者のブラウザで開いている zac は「ログアウトされました」になる（逆も同様）。エージェントの実行中は zac の画面を操作しない。
- サインイン：zac は独自 ID/パスワードで翌日にセッションが切れる。サインイン画面が出たら、`[zac] login_id` とキーチェーン（`keychain_service`）のパスワードでサインインする。パスワードはログ・実行履歴・通知に出さない。未登録なら `needs_login`。

## 期替わり・月替わりで JOB 番号が変わったとき

- **月ごとの案件**（例：`bizoceanAPPs開発(26/10)` → `2602063 bizoceanAPPs開発(26/11)`）：zac に翌月の案件ができたら `sync-zac` を実行する。案件名の年月からシリーズにまとまり、業務明細では勤務日の年月の案件が自動で選ばれる。
- **期替わり**（例：第26期 → 第27期で 2600901・2600902 の JOB 番号が変わる）：新しい ID が払い出されたら、
  1. `uv run --directory agent laborman-agent sync-zac` で取り込む（新しい案件・売上項目が追加される。取込結果の「候補に現れなかったジョブ」に旧期の ID が出る）
  2. laborman の設定画面で取り込んだ案件・売上項目を確認し、旧期のジョブを無効化する。必要なら「既定の作業内容」や空き時間の既定ジョブを新しい ID に変える

## 段階運用（ランブック）

| 段階 | 実行モード | 期間の目安 | 次に進む条件 |
|------|-----------|-----------|-------------|
| 1 | `dry_run` | 2 週間 | 毎日のスクリーンショットと、zac に手で入力した結果が一致する |
| 2 | `assist` | 2 週間 | 入力内容を人が直さずに保存できた日が 10 営業日続く |
| 3 | `auto` | — | 社内規程の確認が取れていること。以降も warning のある日は自動で `dry_run` に降格する |

実行モードは laborman の **設定 → zac 連携** で切り替えます（`--mode` で 1 回だけ上書きできます）。

## 設定で上書きできる既定値

画面のセレクタと解析規則は `config.toml` の `[owa.selectors]`・`[owa.parser]` で上書きできます（コードの変更は不要）。

```toml
[owa.selectors]
search_box = "#topSearchInput"
search_result = "[role=option]"          # 検索結果の 1 件
result_subject = ""                      # 結果の中の件名。空なら行全体のテキスト
message_body = "[aria-label='メッセージ本文'], [aria-label='Message body']"
login_form = "input[name='loginfmt']"  # 見えたらサインインが必要（URL が login.microsoftonline.com 等でも判定）

[owa.parser]                             # NFKC 正規化（全角→半角）後の文字列に適用
subject_pattern = '\[勤怠情報\](?P<date>\d{4}/\d{1,2}/\d{1,2}):開始(?P<start>\d{1,2}:\d{2})/終了(?P<end>\d{1,2}:\d{2})'
body_date_pattern = '対象日\s*(?P<date>\d{4}/\d{1,2}/\d{1,2})'
body_start_pattern = '開始時間\s*(?P<start>\d{1,2}:\d{2})'
body_end_pattern = '終了時間\s*(?P<end>\d{1,2}:\d{2})'
```

その他の項目：`[browser]` の `profile_dir`・`channel`（`chrome` 既定、`msedge`、空文字で同梱 Chromium）・`headless`・`timeout_seconds`（既定 30）、`[notify] macos`、`[logs]` の `dir`・`retention_days`（既定 14）、`[laborman]` の `api_base_url`・`state_dir`（ロックファイルの置き場所）。

## ローカルデータ

| パス | 内容 | 権限 |
|------|------|------|
| `~/.config/laborman-agent/config.toml` | 設定（秘密情報は書かない） | `600`（緩いと警告） |
| `~/Library/Application Support/laborman-agent/profiles/owa` | OWA のブラウザプロファイル（セッション Cookie を含む。FileVault 前提） | `700` |
| `~/Library/Application Support/laborman-agent/agent.lock` | 多重起動防止のロック | `600` |
| `~/Library/Logs/laborman-agent/agent.log` | 実行ログ（メール本文は出さない） | `600` |
| `~/Library/Logs/laborman-agent/hr_mail/*.txt` | 解析に失敗したメール（調査用。保持期間で削除） | `600` |

## 開発

```bash
cd agent
uv run pytest          # OWA のテストは tests/fixtures/owa/*.html の静的モックのみ（実システムには接続しない）
uv run ruff check .
uv run mypy laborman_agent tests
```

`tests/fixtures/hr_mail/` には実際の人事メール（宛名の氏名を除いたもの）を置きます。ここのファイルはすべて、既定の解析規則で件名と本文の両方から同じ値が取れることをテストします。書式の境界値は `tests/fixtures/hr_mail_cases/` に置きます。
