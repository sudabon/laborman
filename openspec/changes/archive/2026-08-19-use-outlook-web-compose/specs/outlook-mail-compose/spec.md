## MODIFIED Requirements

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

## RENAMED Requirements

- FROM: `### Requirement: mailto URL生成とOutlook起動`
- TO: `### Requirement: Outlook on the web URL生成と起動`
