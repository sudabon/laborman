# Spec Delta

## Purpose

laborman が算出したドラフトを、ホストのエージェントが zac の業務報告画面へ安全に入力・保存し、その結果を記録・通知するための機能。誤登録を防ぐ段階的な実行モードと安全ガードを含む。

## ADDED Requirements

### Requirement: 一連の実行

エージェントは、`laborman-agent run [--date D] [--mode M] [--headed] [--force]` で、対象日（既定は前営業日）について次の順に処理しなければならない（SHALL）：zac 保存成功日時の確認（設定済みなら終了コード `0` でスキップ。`--force` で無視）→ zac への到達性の確認 → 出退勤実績が未登録なら人事メールの取込 → ドラフトの取得と検証 → zac への入力 → モードに応じた保存 → 結果の記録と通知。`laborman-agent register` は人事メールの取込を行わずに zac 以降の処理だけを行わなければならない（SHALL）。

#### Scenario: 登録済みの日

- **WHEN** 対象日の zac 保存成功日時が設定済みの状態で `run` を実行する
- **THEN** エージェントは zac を開かず、終了コード `0` で終了する

#### Scenario: VPN 未接続

- **WHEN** zac の到達性確認用 URL に 5 秒以内に接続できない
- **THEN** エージェントは状態 `vpn_unreachable` を記録し、終了コード `2` で終了する

### Requirement: 実行モード

エージェントは、実行モード `dry_run`・`assist`・`auto` を持たなければならない（SHALL）。モードの既定値は laborman の設定から取得し、`--mode` で上書きできなければならない（SHALL）。

- `dry_run`：zac の画面に入力してスクリーンショットを保存し、保存せずに状態 `dry_run_done` を記録する
- `assist`：入力した画面を表示したまま、利用者の保存操作を最大 15 分待つ。保存完了の表示を確認できたら `succeeded`、時間切れなら `awaiting_user` を記録する
- `auto`：保存操作を行い、保存完了の表示を確認する

#### Scenario: dry_run

- **WHEN** 実行モード `dry_run` で、検証結果に error がない日に `run` を実行する
- **THEN** エージェントは zac の画面に出退勤・休憩・入力行を入力し、スクリーンショットを保存し、保存操作を行わずに `dry_run_done` を記録する

#### Scenario: assist で利用者が保存する

- **WHEN** 実行モード `assist` で入力後、利用者が zac の画面で保存する
- **THEN** エージェントは保存完了の表示を確認して `succeeded` を記録し、対象日の zac 保存成功日時を設定する

### Requirement: 検証結果による制御

エージェントは、ドラフトに `error` がある場合、どのモードでも zac の保存操作を行ってはならず（MUST NOT）、状態 `validation_failed` を記録して通知し、終了コード `3` で終了しなければならない（MUST）。`warning` がある場合、`auto` は `dry_run` として動作し、その旨を通知しなければならない（MUST）。

#### Scenario: error のある日

- **WHEN** 対象日のドラフトに `UNCOVERED_TIME`（error）がある状態で、実行モード `auto` で `run` を実行する
- **THEN** エージェントは zac を操作せず、`validation_failed` を記録・通知して終了コード `3` で終了する

#### Scenario: warning のある日の auto

- **WHEN** 対象日のドラフトに `TASK_OUTSIDE_ATTENDANCE`（warning）がある状態で、実行モード `auto` で `run` を実行する
- **THEN** エージェントは保存操作を行わずに `dry_run` として入力とスクリーンショットまでを行い、`auto` から降格したことを通知する

### Requirement: 既存入力の非上書き

エージェントは、zac の対象日に既存の入力がある場合、入力・保存を行ってはならない（MUST NOT）。状態 `already_registered_in_zac` を記録して通知し、終了コード `3` で終了しなければならない（MUST）。

#### Scenario: zac で手入力済みの日

- **WHEN** 対象日の zac 業務報告画面にすでに明細が入力されている
- **THEN** エージェントは何も入力せず、`already_registered_in_zac` を記録・通知して終了コード `3` で終了する

### Requirement: 操作範囲の制限

エージェントは、zac の「申請」「承認依頼」その他保存以外の確定操作を行ってはならない（MUST NOT）。自動化の上限は「保存」とする。

#### Scenario: 保存後の申請ボタン

- **WHEN** `auto` で保存が完了し、画面に「申請」ボタンが表示される
- **THEN** エージェントは「申請」ボタンを操作せずに処理を終える

### Requirement: 保存結果の確認

エージェントは、保存完了の表示を確認できた場合にのみ状態 `succeeded` を記録しなければならない（MUST）。確認できない場合、またはエラー表示を検知した場合は `failed` とし、スクリーンショットのパスを記録しなければならない（MUST）。

#### Scenario: 保存完了を確認できない

- **WHEN** `auto` で保存操作をした後、保存完了の表示が一定時間内に現れない
- **THEN** エージェントは `failed` とスクリーンショットのパスを記録し、通知して終了コード `3` で終了する

### Requirement: 実行履歴

システムは、エージェントのすべての実行結果を、対象日・モード・状態・入力した内容のスナップショット・メッセージ・スクリーンショットのパス・エージェントのバージョン・開始/終了日時とともに記録しなければならない（SHALL）。状態は `running`・`succeeded`・`dry_run_done`・`awaiting_user`・`validation_failed`・`needs_login`・`vpn_unreachable`・`hr_mail_not_found`・`already_registered_in_zac`・`failed` のいずれかとする。状態 `succeeded` が記録された場合、システムは対象日の zac 保存成功日時を設定しなければならない（MUST）。実行履歴は勤務日で絞り込んで取得できなければならない（SHALL）。

#### Scenario: 成功を記録する

- **WHEN** エージェントが実行開始を `running` で記録し、その後 `succeeded` に更新する
- **THEN** システムは実行履歴を更新し、対象日の zac 保存成功日時を設定する

#### Scenario: メール未着を記録する

- **WHEN** `run` で出退勤実績が未登録のため人事メールを探したが見つからない
- **THEN** エージェントは `hr_mail_not_found` を記録し、終了コード `2` で終了する

### Requirement: zac のサインイン

エージェントは、zac のサインイン画面を検知した場合、状態 `needs_login` を記録して通知し、終了コード `3` で終了しなければならない（MUST）。`laborman-agent login zac` で画面付きブラウザを開き、利用者が手動でサインインしたセッションを専用のプロファイルに保存できなければならない（SHALL）。エージェントはパスワードを入力・保存してはならない（MUST NOT）。zac が独自の ID/パスワード方式で資格情報が必要な場合は、利用者が macOS キーチェーンに登録したものだけを読み出さなければならず（MUST）、設定ファイル・DB・ログに書き出してはならない（MUST NOT）。

#### Scenario: zac のセッション切れ

- **WHEN** `run` の実行中に zac のサインイン画面が表示される
- **THEN** エージェントは `needs_login` を記録し、`laborman-agent login zac` を案内する通知を出して終了コード `3` で終了する

### Requirement: VPN と zac の診断

エージェントは、`laborman-agent doctor` に zac の到達性（VPN 接続）と zac のプロファイルの確認を含めなければならない（SHALL）。

#### Scenario: VPN 未接続で診断する

- **WHEN** VPN に接続していない状態で `doctor` を実行する
- **THEN** エージェントは zac に到達できない旨を表示し、終了コード `3` で終了する

### Requirement: 定時実行

システムは、平日の朝に `laborman-agent run` を複数回（例：9:20・10:20・11:20・13:20）起動する launchd の設定例と導入手順を提供しなければならない（SHALL）。完了済みの日は即座にスキップされるため、複数回の起動で重複登録が起きてはならない（MUST NOT）。VPN 未接続などの再試行状態は、その日の最終回の起動でのみ通知しなければならない（SHALL）。

#### Scenario: 2 回目以降の起動

- **WHEN** 9:20 の起動で `succeeded` になった日に、10:20 に再度起動される
- **THEN** エージェントは zac を開かずに終了コード `0` で終了する

#### Scenario: 最終回まで VPN 未接続

- **WHEN** 9:20・10:20・11:20 は VPN 未接続で、13:20 の起動でも VPN 未接続
- **THEN** エージェントは 13:20 の起動でのみ VPN 未接続を通知する
