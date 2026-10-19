from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """コマンドの終了コード。launchd 等の呼び出し側が再試行・通知の判断に使う。"""

    OK = 0  # 完了またはスキップ
    ERROR = 1  # 想定外のエラー（API に接続できないなど）
    RETRY_LATER = 2  # 後で再試行（メール未着など）
    NEEDS_ATTENTION = 3  # 人の対応が必要（サインイン切れ・検証エラー・解析失敗など）
