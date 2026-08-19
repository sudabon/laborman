# outlook-mail-compose Specification

## Purpose
TBD - created by archiving change add-labor-report-mailto. Update Purpose after archive.

## Requirements

### Requirement: メール件名・本文生成

システムは、保存済みテンプレートのプレースホルダを当日の報告値（日付・始業/終業時刻・勤務時間・勤務区分・メモ）で置換し、件名と本文を生成しなければならない（SHALL）。終業メールの本文は、ヘッダテンプレート＋本文テンプレート＋フッタテンプレートを連結して構成する。`{{work_style}}` は `office`→「オフィス」、`remote`→「リモート」に展開する。

#### Scenario: 始業報告メールを生成する

- **WHEN** ユーザーが始業メール作成を実行する
- **THEN** システムは始業テンプレートの `{{date}}`・`{{start_time}}`・`{{work_style}}`・`{{note}}` を当日値で置換し、件名と本文を生成する

#### Scenario: 終業報告メールを生成する

- **WHEN** ユーザーが終業メール作成を実行する
- **THEN** システムはヘッダ・本文・フッタの各テンプレートを当日の `{{date}}`・`{{start_time}}`・`{{end_time}}`・`{{work_duration}}`・`{{work_style}}`・`{{note}}` で置換し、ヘッダ＋本文＋フッタを連結した本文と件名を生成する

#### Scenario: 生成本文の保存方針

- **WHEN** 始業・終業メールが生成される
- **THEN** システムは終業メールの本文テンプレート置換結果（ヘッダ/フッタ除く）のみを保存対象とし、ヘッダ/フッタおよび始業メール本文は保存しない

### Requirement: 作成前の確認画面

システムは、Outlook on the web を開く前に統合後の宛先（To）・件名・本文を提示する確認画面を表示しなければならない（MUST）。確認画面では、会社の Microsoft 365 アカウントで Outlook on the web にサインインしていること、作成画面で From を確認すること、および登録上の CC/BCC も To として受信者全員に表示されることを案内しなければならない（MUST）。

#### Scenario: 確認画面を経由して作成する

- **WHEN** ユーザーが始業・終業メール作成を選ぶ
- **THEN** システムは「以下の内容でOutlook on the webメールを作成します」として統合後の宛先・件名・本文、宛先区分変更の警告、およびM365アカウントとFromの確認案内を表示し、ユーザーの確定後にメール作成URLを開く

### Requirement: コピー用フォールバックUI

システムは、Outlook on the web が開かない場合、サインイン後に入力内容が引き継がれない場合、またはメール作成URLが長すぎる場合に備え、元の laborman タブで統合後の宛先（To）・件名・本文をそれぞれコピーできる手段を提供しなければならない（SHALL）。

#### Scenario: 本文をコピーする

- **WHEN** ユーザーがフォールバックUIでコピー操作を行う
- **THEN** システムは統合後の宛先（To）・件名・本文を個別にクリップボードへコピーでき、Outlook on the web で手動送信できる旨を案内する

#### Scenario: Outlookを開けない場合の案内

- **WHEN** 新しいタブがブロックされた、Outlook on the web が開かない、または作成画面に入力内容が引き継がれない
- **THEN** システムは元の laborman タブにコピー用フォールバック導線を残し、再試行または手動入力して送信するよう案内する

### Requirement: 送信完了は検知せず自己申告とする

システムは、Outlook on the web の作成画面の読込状態および送信完了を検知できないため、ステータスを「送信済み」と表現してはならず（MUST NOT）、「メール作成済み」と表現しなければならない（MUST）。送信完了は任意のユーザー自己申告として扱う。

#### Scenario: メール作成後の状態表現

- **WHEN** Outlook on the web の作成画面を開く操作を実行した
- **THEN** システムは当該報告を「メール作成済み」として記録し、「送信済み」とは表示しない

#### Scenario: ユーザーによる送信済み自己申告

- **WHEN** ユーザーが Outlook on the web で送信後に元の laborman タブへ戻り「Outlook on the webで送信しました」をチェックする
- **THEN** システムはその申告を記録するが、これがアプリによる送信確認ではなくユーザー自己申告であることを前提とする

### Requirement: Outlook on the web URL生成と起動

システムは、登録上の To・CC・BCC をこの順で1つの宛先（To）へ統合し、統合後の宛先・件名・本文を URL エンコードした Outlook on the web のメール作成URLを生成しなければならない（SHALL）。`cc` および `bcc` クエリパラメータは付与してはならない（MUST NOT）。利用者の操作を起点として新しいブラウザタブで新規メール作成画面を開き、元の laborman タブは維持し、From は指定しない。

#### Scenario: mailtoリンクでOutlookを開く

- **WHEN** メール生成後にユーザーがメール作成を確定する
- **THEN** システムは `mailto:` を実行せず、`https://outlook.office.com/mail/deeplink/compose?to={to+cc+bcc}&subject={subject}&body={body}` 形式のURLを生成し、統合後の宛先・件名・本文を入力済みにした Outlook on the web の作成画面を新しいタブで開く

#### Scenario: 登録上のCC/BCCが設定されている場合

- **WHEN** 登録上の CC または BCC を含むメール作成を実行する
- **THEN** システムはそれらの宛先を To の後ろへ統合し、`cc` / `bcc` パラメータを付与せずに Outlook on the web のメール作成URLを生成する

#### Scenario: CC/BCCが空の場合

- **WHEN** 登録上の CC と BCC が未設定でメール作成を実行する
- **THEN** システムは登録上の To だけを `to` パラメータへ設定し、`cc` / `bcc` パラメータを付与せずに Outlook on the web のメール作成URLを生成する
