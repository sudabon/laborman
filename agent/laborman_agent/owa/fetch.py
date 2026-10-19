from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from laborman_agent.browser import manual_login
from laborman_agent.config import AgentConfig
from laborman_agent.owa.parser import ParserRules, mentions_date, normalize, parse_subject

# サインイン切れのとき OWA はこれらのホストへリダイレクトする
LOGIN_HOSTS = frozenset({"login.microsoftonline.com", "login.microsoft.com", "login.live.com"})
POLL_INTERVAL_MS = 500
# 対象のメールが見つからないまま経過したら検索し直す間隔（初期化中の OWA が Enter を捨てる場合に備える）
SEARCH_RETRY_MS = 5000


class OwaError(Exception):
    pass


class NeedsLoginError(OwaError):
    """OWA のサインイン画面が表示された（セッション切れ・未サインイン）。"""


class MailNotFoundError(OwaError):
    """検索結果に対象日の人事メールがない。"""


class OwaPageError(OwaError):
    """OWA の画面を認識できない（画面変更でセレクタが合わないなど）。"""


@dataclass(frozen=True)
class HrMail:
    subject: str
    # 件名で解析できた場合はメールを開かないため None
    body: str | None


def build_search_query(template: str, keyword: str, target: date, sender: str = "") -> str:
    """件名キーワード＋対象日（YYYY/MM/DD）で検索する。差出人は設定されているときだけ条件に加える。"""
    from_clause = f'from:"{sender}" ' if sender else ""
    return template.format(
        from_clause=from_clause,
        hr_mail_subject_keyword=keyword,
        target_date=target.strftime("%Y/%m/%d"),
    )


def owa_profile_dir(config: AgentConfig) -> Path:
    return config.browser.profile_dir / "owa"


class OwaMailbox:
    """OWA のメール画面の Page Object。セレクタは設定から受け取る。"""

    def __init__(
        self,
        page: Page,
        selectors: dict[str, str],
        timeout_ms: float,
        search_retry_ms: float = SEARCH_RETRY_MS,
    ) -> None:
        self.page = page
        self.selectors = selectors
        self.timeout_ms = timeout_ms
        self.search_retry_ms = search_retry_ms
        self._query: str | None = None
        self._searched_at = 0.0

    def open(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")
        self.ensure_signed_in()

    def is_login_page(self) -> bool:
        if urlparse(self.page.url).hostname in LOGIN_HOSTS:
            return True
        login_form = self.selectors.get("login_form", "")
        return bool(login_form) and self.page.locator(login_form).first.is_visible()

    def ensure_signed_in(self) -> None:
        candidates = [self.selectors["search_box"], self.selectors.get("login_form", "")]
        try:
            self.page.wait_for_selector(
                ", ".join(selector for selector in candidates if selector),
                state="visible",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            if self.is_login_page():
                raise NeedsLoginError("Outlook on the web のサインインが必要です") from exc
            raise OwaPageError("Outlook on the web の検索ボックスが見つかりません（search_box を確認）") from exc
        if self.is_login_page():
            raise NeedsLoginError("Outlook on the web のサインインが必要です")

    def search(self, query: str) -> None:
        box = self.page.locator(self.selectors["search_box"]).first
        box.click()
        box.fill(query)
        box.press("Enter")
        self._query = query
        self._searched_at = time.monotonic()

    def _search_needs_retry(self) -> bool:
        """検索が実行されていない可能性があるか。

        OWA は検索ボックスの表示後も初期化を続け、その間の入力を消したり Enter を無視したりする。
        そのまま待つと受信トレイの一覧を検索結果と取り違えるため、検索語が消えていれば、
        または一定時間見つからなければ検索し直す。
        """
        if self._query is None:
            return False
        try:
            current = self.page.locator(self.selectors["search_box"]).first.input_value()
        except PlaywrightError:
            return True
        if current != self._query:
            return True
        return (time.monotonic() - self._searched_at) * 1000 >= self.search_retry_ms

    def _read_subjects(self, items: Locator) -> list[str]:
        """検索結果の各行の件名を 1 回の評価でまとめて読む。

        行ごとに nth(i) で読むと、読み取り中に一覧が再描画されて行数が減ったとき、
        消えた行が現れるまで Playwright の既定のタイムアウトだけ待ち続けてしまう。
        """
        subjects: list[str] = items.evaluate_all(
            """(rows, subjectSelector) => rows.map((row) => {
                const target = subjectSelector ? row.querySelector(subjectSelector) : row;
                return target ? target.innerText : "";
            })""",
            self.selectors.get("result_subject", ""),
        )
        return subjects

    def _open_body(self, item: Locator) -> str:
        item.click(timeout=self.timeout_ms)
        body = self.page.locator(self.selectors["message_body"]).first
        try:
            body.wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise OwaPageError("メール本文が見つかりません（message_body を確認）") from exc
        return body.inner_text()

    def find_mail(self, target: date, keyword: str, rules: ParserRules) -> HrMail:
        """検索結果から対象日の人事メールを探す。受信日では絞り込まず、件名の日付で照合する。

        件名で出退勤を解析できればメールを開かない。件名にキーワードと対象日があるのに
        解析できない場合だけ、メールを開いて本文を取得する。
        """
        normalized_keyword = normalize(keyword)
        deadline = time.monotonic() + self.timeout_ms / 1000
        while True:
            items = self.page.locator(self.selectors["search_result"])
            for index, subject in enumerate(self._read_subjects(items)):
                record = parse_subject(subject, rules)
                if record is not None:
                    if record.work_date == target:
                        return HrMail(subject=subject.strip(), body=None)
                    continue
                if normalized_keyword in normalize(subject) and mentions_date(subject, target):
                    return HrMail(subject=subject.strip(), body=self._open_body(items.nth(index)))
            if time.monotonic() >= deadline:
                raise MailNotFoundError(f"{target.isoformat()} の人事メールが見つかりません")
            if self._query is not None and self._search_needs_retry():
                self.search(self._query)
            self.page.wait_for_timeout(POLL_INTERVAL_MS)


def fetch_hr_mail(config: AgentConfig, target: date, keyword: str, sender: str = "") -> HrMail:
    """専用プロファイルのブラウザで OWA を開き、対象日の人事メールを取得する。"""
    profile = owa_profile_dir(config)
    if not profile.exists():
        raise NeedsLoginError("OWA のプロファイルがありません。laborman-agent login owa を実行してください")
    rules = ParserRules.from_mapping(config.owa.parser)
    query = build_search_query(config.owa.search_query, keyword, target, sender)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel=config.browser.channel or None,
            headless=config.browser.headless,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            mailbox = OwaMailbox(page, config.owa.selectors, config.browser.timeout_seconds * 1000)
            mailbox.open(config.owa.url)
            mailbox.search(query)
            return mailbox.find_mail(target, keyword, rules)
        finally:
            context.close()


def login_owa(config: AgentConfig) -> Path:
    """画面付きのブラウザで OWA を開き、利用者が手動でサインインしてブラウザを閉じるまで待つ。"""
    return manual_login(config, owa_profile_dir(config), config.owa.url)
