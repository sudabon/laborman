from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from laborman_agent.config import DEFAULT_OWA_SELECTORS, DEFAULT_SEARCH_QUERY
from laborman_agent.owa.fetch import (
    MailNotFoundError,
    NeedsLoginError,
    OwaMailbox,
    OwaPageError,
    build_search_query,
)
from laborman_agent.owa.parser import DEFAULT_RULES

FIXTURES = Path(__file__).parent / "fixtures" / "owa"
TARGET = date(2026, 10, 9)
KEYWORD = "[勤怠情報]"
TIMEOUT_MS = 2000
BODY = "対象日\n2026/10/09\n\n開始時間\n08:29\n\n終了時間\n18:38\n\n残業時間\n12:44:49"


def mail(subject: str, body: str = BODY, **extra: Any) -> dict[str, Any]:
    return {"from": "人事担当", "subject": subject, "body": body, **extra}


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def open_mailbox(browser: Browser) -> Iterator[Any]:
    pages: list[Page] = []

    def opener(
        mails: list[dict[str, Any]],
        inbox: list[dict[str, Any]] | None = None,
        selectors: dict[str, str] | None = None,
        page_name: str = "mailbox.html",
        flags: tuple[str, ...] = (),
    ) -> OwaMailbox:
        page = browser.new_page()
        pages.append(page)
        flag_script = "".join(f"window.{flag} = true;" for flag in flags)
        page.add_init_script(
            f"window.__MAILS__ = {json.dumps(mails)}; window.__INBOX__ = {json.dumps(inbox or [])};{flag_script}"
        )
        mailbox = OwaMailbox(page, {**DEFAULT_OWA_SELECTORS, **(selectors or {})}, TIMEOUT_MS, search_retry_ms=700)
        mailbox.open((FIXTURES / page_name).as_uri())
        return mailbox

    yield opener
    for page in pages:
        page.close()


def search(mailbox: OwaMailbox) -> None:
    mailbox.search(build_search_query(DEFAULT_SEARCH_QUERY, KEYWORD, TARGET))


def test_build_search_query_without_sender() -> None:
    assert build_search_query(DEFAULT_SEARCH_QUERY, KEYWORD, TARGET) == 'subject:"[勤怠情報]2026/10/09"'


def test_build_search_query_with_sender() -> None:
    assert (
        build_search_query(DEFAULT_SEARCH_QUERY, KEYWORD, TARGET, "hr@example.com")
        == 'from:"hr@example.com" subject:"[勤怠情報]2026/10/09"'
    )


def test_reads_attendance_from_subject_without_opening(open_mailbox: Any) -> None:
    mailbox = open_mailbox(
        [
            # OWA が記号を無視して別の日のメールも返した場合でも、件名の日付で照合する
            mail("[勤怠情報]2026/10/08:開始09:01/終了18:12", loose=True),
            mail("[勤怠情報]2026/10/09:開始08:29/終了18:38"),
        ]
    )
    search(mailbox)

    found = mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)

    assert found.body is None
    assert "[勤怠情報]2026/10/09:開始08:29/終了18:38" in found.subject
    assert mailbox.page.evaluate("window.__LAST_QUERY__") == 'subject:"[勤怠情報]2026/10/09"'
    assert mailbox.page.locator("[aria-label='メッセージ本文']").count() == 0


def test_opens_mail_for_body_when_subject_does_not_parse(open_mailbox: Any) -> None:
    mailbox = open_mailbox([mail("[勤怠情報]2026/10/09 のお知らせ")])
    search(mailbox)

    found = mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)

    assert found.body is not None
    assert "開始時間" in found.body
    assert "08:29" in found.body


def test_uses_subject_selector_when_configured(open_mailbox: Any) -> None:
    mailbox = open_mailbox(
        [mail("[勤怠情報]2026/10/09:開始08:29/終了18:38", preview="[勤怠情報]2026/10/08:開始09:01/終了18:12")],
        selectors={"result_subject": ".subject"},
    )
    search(mailbox)

    assert mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES).subject == "[勤怠情報]2026/10/09:開始08:29/終了18:38"


def test_not_found_when_no_mail_for_target(open_mailbox: Any) -> None:
    mailbox = open_mailbox(
        [mail("[勤怠情報]2026/10/08:開始09:01/終了18:12", loose=True)],
        inbox=[mail("[勤怠情報]2026/10/07:開始09:00/終了18:00")],
    )
    search(mailbox)

    with pytest.raises(MailNotFoundError):
        mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)


def test_ignores_unrelated_mail_mentioning_target_date(open_mailbox: Any) -> None:
    mailbox = open_mailbox([mail("2026/10/09 の定例について", loose=True)])
    search(mailbox)

    with pytest.raises(MailNotFoundError):
        mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)
    assert mailbox.page.locator("[aria-label='メッセージ本文']").count() == 0


def test_detects_sign_in_page(open_mailbox: Any) -> None:
    with pytest.raises(NeedsLoginError):
        open_mailbox([], page_name="signin.html")


def test_unrecognized_page_is_reported(open_mailbox: Any) -> None:
    with pytest.raises(OwaPageError):
        open_mailbox([], page_name="unknown.html")


INBOX_WITHOUT_TARGET = [mail("クリッピング通信（2026/10/13）"), mail("[PB]マスター管理関連の情報共有")]


@pytest.mark.parametrize("flag", ["__CLEAR_FIRST_SEARCH__", "__IGNORE_FIRST_ENTER__"])
def test_retries_search_when_owa_drops_the_first_search(open_mailbox: Any, flag: str) -> None:
    # 初期化中の OWA が最初の検索を捨てても、受信トレイの一覧を検索結果と取り違えずに検索し直す
    mailbox = open_mailbox(
        [mail("[勤怠情報]2026/10/09:開始08:29/終了18:38")],
        inbox=INBOX_WITHOUT_TARGET,
        flags=(flag,),
    )
    search(mailbox)

    found = mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)

    assert "[勤怠情報]2026/10/09:開始08:29/終了18:38" in found.subject


def test_handles_list_replaced_while_reading(open_mailbox: Any) -> None:
    # 一覧を読んでいる途中で検索結果に置き換わっても、消えた行を待ち続けない
    mailbox = open_mailbox(
        [mail("[勤怠情報]2026/10/09:開始08:29/終了18:38")],
        inbox=[mail(f"お知らせ {index}") for index in range(5)],
        flags=("__REPLACE_ON_READ__",),
    )
    mailbox.page.set_default_timeout(5000)
    started = time.monotonic()

    found = mailbox.find_mail(TARGET, KEYWORD, DEFAULT_RULES)

    assert "[勤怠情報]2026/10/09" in found.subject
    assert time.monotonic() - started < TIMEOUT_MS / 1000
