"""zac（業務報告画面）の操作。

画面の操作は Page Object（`ZacReportPage`）の操作だけに限定し、「申請」「承認依頼」などを扱う
操作は持たない（design D6）。具体的な実装（`report_page.py`）は zac の画面仕様を確認してから作る。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

import logging

import httpx

from laborman_agent.browser import manual_login
from laborman_agent.config import AgentConfig
from laborman_agent.zac.credentials import registration_hint

REACHABILITY_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger("laborman_agent")


class ZacNotImplementedError(Exception):
    """zac の画面操作がまだ実装されていない。"""


class ZacReportPage(Protocol):
    """zac の業務報告画面の Page Object が提供する操作（design D6）。"""

    def open(self, work_date: date) -> None: ...

    def is_login_page(self) -> bool: ...

    def login(self, login_id: str, password: str) -> None:
        """サインイン画面にログイン ID とパスワードを入れて送信する。パスワードを記録しないこと。"""

    def has_existing_entries(self) -> bool: ...

    def fill(self, draft: dict[str, Any]) -> None:
        """出退勤と工数明細（ドラフトの入力行）を入力する。休憩は入れない。"""

    def fill_breaks(self, breaks: list[dict[str, str]]) -> None:
        """休憩を休憩専用のフォームに入力する（工数明細の行にはしない）。"""

    def screenshot(self, path: Path) -> None: ...

    def click_save(self) -> None:
        """設定の save_button だけを押す（申請・承認依頼は押さない）。"""

    def wait_saved(self, timeout_seconds: float) -> bool: ...

    def has_error(self) -> bool: ...


ZacSessionFactory = Callable[[AgentConfig, bool], AbstractContextManager[ZacReportPage]]


@contextmanager
def open_zac_session(config: AgentConfig, headed: bool) -> Iterator[ZacReportPage]:
    """専用プロファイルのブラウザで zac の業務報告画面の Page Object を開く。"""
    from laborman_agent.zac.report_page import PlaywrightZacReportPage, zac_browser_page

    with zac_browser_page(config, headed) as page:
        yield PlaywrightZacReportPage(page, config)


def zac_profile_dir(config: AgentConfig) -> Path:
    return config.browser.profile_dir / "zac"


def login_zac(config: AgentConfig) -> Path:
    """画面付きのブラウザで zac を開き、利用者が手動でサインインしてブラウザを閉じるまで待つ。"""
    return manual_login(config, zac_profile_dir(config), config.zac.base_url)


def check_zac_reachable(url: str, timeout: float = REACHABILITY_TIMEOUT_SECONDS) -> bool:
    """zac（VPN 内）に到達できるか。HTTP の応答があれば到達とみなす（状態コードは問わない）。"""
    try:
        httpx.get(url, timeout=timeout, follow_redirects=False)
    except httpx.TransportError:
        return False
    return True


class SignInResult(Enum):
    SIGNED_IN = "signed_in"
    NO_PASSWORD = "no_password"  # キーチェーンから読めない
    REJECTED = "rejected"  # 読めたがサインインできない（パスワード違い・サインイン画面の変更）


def sign_in_with_keychain(
    page: ZacReportPage,
    config: AgentConfig,
    work_date: date,
    password_reader: Callable[[str, str], str | None],
) -> SignInResult:
    """キーチェーンのパスワードでサインインし、業務報告画面を開き直す。

    パスワードはログ・例外に出さない（Page Object の例外は連鎖させず、種類だけをログに出す）。
    """
    zac = config.zac
    password = password_reader(zac.keychain_service, zac.login_id)
    if password is None:
        return SignInResult.NO_PASSWORD
    try:
        page.login(zac.login_id, password)
    except Exception as exc:  # noqa: BLE001
        logger.warning("zac のサインイン画面を操作できませんでした（%s）", type(exc).__name__)
        return SignInResult.REJECTED
    finally:
        del password
    page.open(work_date)
    return SignInResult.REJECTED if page.is_login_page() else SignInResult.SIGNED_IN


def sign_in_failure_message(config: AgentConfig, result: SignInResult) -> str:
    zac = config.zac
    if result == SignInResult.NO_PASSWORD:
        return (
            "zac にサインインできません。キーチェーンにパスワードを登録してください"
            f"（{registration_hint(zac.keychain_service, zac.login_id)}）"
        )
    return (
        "zac にサインインできません。キーチェーンのパスワードは読めましたが、サインインに失敗しました。"
        "zac のパスワードが変わっていれば登録し直してください"
        f"（{registration_hint(zac.keychain_service, zac.login_id)} -U）。"
        "変わっていなければサインイン画面の変更が考えられます（ログを確認してください）"
    )

