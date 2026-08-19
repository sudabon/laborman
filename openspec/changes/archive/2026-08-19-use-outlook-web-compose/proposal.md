## Why

現在の `mailto:` 方式は OS の既定メールクライアント設定に依存し、デスクトップ版 Outlook を起動する。会社の Microsoft 365 をブラウザで利用する運用に合わせ、Outlook on the web のメール作成画面を直接開けるようにする。

## What Changes

- **BREAKING**: メール作成確定時の遷移先を、OS の `mailto:` ハンドラから Microsoft 365 の Outlook on the web に変更する。
- **BREAKING**: Outlook on the web の compose deep link で CC/BCC が反映されない制約に対応するため、登録上の To・CC・BCC をすべて宛先（To）へ統合する。BCC の宛先も受信者全員に表示される。
- 統合後の宛先・件名・本文を URL エンコードし、Outlook on the web の新規メール作成画面へ引き渡す。`cc` / `bcc` クエリパラメータは使用しない。
- Outlook on the web は新しいブラウザタブで開き、laborman の画面を元のタブに残す。
- 作成前プレビュー、送信元確認の注意、項目別コピーのフォールバック、メール作成済み記録、送信済み自己申告を維持する。
- UI とドキュメントの表現を、デスクトップ版 Outlook／`mailto:` 前提から Outlook on the web 前提へ更新する。
- 自動送信、Microsoft Graph API、M365 認証情報の保持、送信完了の自動検知は導入しない。

## Capabilities

### New Capabilities

なし。

### Modified Capabilities

- `outlook-mail-compose`: `mailto:` でMacのデスクトップ版 Outlookを開く要件を、Outlook on the web の新規メール作成画面をブラウザで開く要件へ変更する。

## Impact

- フロントエンドのメール作成URL生成、メール作成ダイアログ、ボタン／案内文、およびユニットテストを変更する。
- `outlook-mail-compose` の正本仕様と、README・アーキテクチャ・セットアップガイドを更新する。
- バックエンドAPI、データベーススキーマ、保存データ、外部依存パッケージには変更を加えない。
- Microsoft Graph のアプリ登録や管理者同意は不要だが、利用者が会社のM365アカウントで Outlook on the web を利用でき、ブラウザでサインイン済みであることを運用上の前提とする。
- CC/BCC の区分は Outlook の作成画面へ維持されず、すべて To として受信者に表示されるため、確認画面と利用手順で明示する。
