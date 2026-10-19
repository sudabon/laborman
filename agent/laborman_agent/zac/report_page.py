"""zac の業務報告画面の Page Object（design D6・D12）。

公開する操作は、開く・サインイン・既存入力の確認・勤怠と休憩と工数の入力・スクリーンショット・「保存」だけ。
「確定」「確定解除」「月報確定」「申請」を押す操作は持たない。選択肢は表示名の完全一致（NFKC）で選ぶ。
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from typing import Any

from playwright.sync_api import Locator, Page, Response, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from laborman_agent.config import AgentConfig
from laborman_agent.logs import ensure_private_dir

logger = logging.getLogger("laborman_agent")

UI_TIMEOUT_MS = 10_000
# 案件を選んでから売上項目の通信が始まるまで待つ時間（始まらなければ選択欄を開いて待つ）
SALES_REQUEST_GRACE_SECONDS = 5.0
# 通信の応答のあと、選択肢が描き直されるまでの余裕
SETTLE_MS = 300
POLL_INTERVAL_SECONDS = 0.5
CLOSED_MARK = "売上計上済"
# 休憩の時間帯（勤務日基準の分）。22:00〜24:00 と 24:00〜29:00 は別の欄に入れる
LATE_BAND = (22 * 60, 24 * 60)
OVERNIGHT_BAND = (24 * 60, 29 * 60)


class ZacOptionNotFoundError(Exception):
    """zac の選択肢に、ドラフトの値と一致するものがない。"""

    def __init__(self, field_label: str, value: str, seen: list[str] | None = None) -> None:
        super().__init__(f"{field_label}「{value}」が zac の選択肢にありません")
        self.field_label = field_label
        self.value = value
        # 原因調査のため、そのとき画面に出ていた選択肢（ログにだけ出す）
        self.seen = seen or []


class ZacPageError(Exception):
    """zac の画面を想定どおりに操作できない（画面の変更・未確定の日でないなど）。"""


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


def option_name(text: str) -> str:
    """選択肢の表示（1 行目）。「売上計上済」などの印を除く。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if line != CLOSED_MARK]
    return lines[0] if lines else ""


def hhmm_to_minutes(value: str) -> int:
    hours, minutes = (int(part) for part in value.split(":"))
    return hours * 60 + minutes


def minutes_to_zac(minutes: int) -> str:
    """zac の時間数の表記（H:MM）。"""
    return f"{minutes // 60}:{minutes % 60:02d}"


def zac_time(value: str) -> str:
    """勤務日基準の HH:MM を zac の時刻の表記（先頭の 0 を除く H:MM）にする。"""
    return minutes_to_zac(hhmm_to_minutes(value))


def split_break_minutes(breaks: list[dict[str, str]]) -> tuple[int, int, int]:
    """休憩（勤務日基準の HH:MM）を、通常・22〜24時・24〜29時の分数に分ける。"""
    normal = late = overnight = 0
    for item in breaks:
        start, end = hhmm_to_minutes(item["start"]), hhmm_to_minutes(item["end"])
        late_part = max(0, min(end, LATE_BAND[1]) - max(start, LATE_BAND[0]))
        overnight_part = max(0, min(end, OVERNIGHT_BAND[1]) - max(start, OVERNIGHT_BAND[0]))
        late += late_part
        overnight += overnight_part
        normal += (end - start) - late_part - overnight_part
    return normal, late, overnight


@dataclass
class ZacMasters:
    work_kinds: list[str] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)

    def as_import_payload(self) -> dict[str, Any]:
        return {"work_kinds": self.work_kinds, "projects": self.projects}


PROJECT_OPTION = re.compile(r"^(?P<code>\d+)\s+(?P<name>.+)$")


class ZacBasePage:
    def __init__(self, page: Page, config: AgentConfig) -> None:
        self.page = page
        self.config = config
        self.selectors = config.zac.selectors
        # 売上項目の通信の応答の回数（案件を選んだあとの読み込み完了の判定に使う）
        self._sales_loads = 0
        self._sales_mark = 0
        page.on("response", self._count_sales_load)

    def _count_sales_load(self, response: Response) -> None:
        pattern = self.config.zac.sales_response_pattern
        if pattern and pattern in response.url:
            self._sales_loads += 1

    def _wait_sales_loaded(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self._sales_loads > self._sales_mark:
                return True
            self.page.wait_for_timeout(100)
        return self._sales_loads > self._sales_mark

    def s(self, key: str) -> str:
        selector = self.selectors.get(key, "")
        if not selector:
            raise ZacPageError(f"[zac.selectors] {key} が未設定です")
        return selector

    def report_url(self, work_date: date) -> str:
        zac = self.config.zac
        return zac.report_url_template.format(
            base_url=zac.base_url,
            date=work_date.isoformat(),
            date_slash=work_date.strftime("%Y/%m/%d"),
        )

    def open(self, work_date: date) -> None:
        self.page.goto(self.report_url(work_date), wait_until="domcontentloaded")
        # セレクタの種類（CSS・text=）が混ざってもよいよう、ロケーターを or で組み合わせる
        ready = (
            self.page.locator(self.s("login_form"))
            .or_(self.page.locator(self.s("register_open")))
            .or_(self.page.locator(self.s("confirmed_indicator")))
        )
        try:
            ready.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise ZacPageError("zac の業務報告画面を認識できません（URL・セレクタを確認してください）") from exc

    def is_login_page(self) -> bool:
        return self.page.locator(self.s("login_form")).first.is_visible()

    def login(self, login_id: str, password: str) -> None:
        self.page.locator(self.s("login_id_input")).first.fill(login_id)
        self.page.locator(self.s("login_password_input")).first.fill(password)
        self.page.locator(self.s("login_submit")).first.click()
        # サインイン後、zac は元のページ（ReturnUrl）へ自分で移動する。移動中に開き直すと読み込みが
        # 中断される（net::ERR_ABORTED）ため、サインイン画面が消えるまで待つ。消えなければ呼び出し元が
        # サインイン画面のままと判定する
        try:
            self.page.locator(self.s("login_form")).first.wait_for(state="detached", timeout=UI_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return
        self.page.wait_for_load_state("domcontentloaded")

    # ---- 作業登録のダイアログ ----

    def _dialog(self) -> Locator:
        return self.page.locator(self.s("dialog")).last

    def open_register_dialog(self) -> Locator:
        button = self.page.locator(self.s("register_open")).first
        if not button.is_visible():
            raise ZacPageError("作業登録を開けません（確定済みの日は登録できません）")
        button.click()
        dialog = self._dialog()
        dialog.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        return dialog

    def _options(self) -> Locator:
        options = self.page.locator(self.s("option"))
        options.first.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        return options

    def _option_texts(self) -> list[str]:
        """開いている選択肢の表示を読む。

        サインイン直後などは選択肢を後から読み込み、それまでは空の項目だけが出ている
        （2026-10-19 に判明）。名前のある項目が出てから、件数が落ち着くまで待って読む。
        """
        options = self._options()
        deadline = time.monotonic() + UI_TIMEOUT_MS / 1000
        texts: list[str] = []
        while True:
            current: list[str] = options.evaluate_all("(els) => els.map((el) => el.innerText)")
            loaded = any(option_name(text) for text in current)
            if loaded and current == texts:
                return current
            if time.monotonic() > deadline:
                return current
            texts = current if loaded else []
            self.page.wait_for_timeout(SETTLE_MS)

    def _pick(self, field_label: str, value: str, *, prefix: bool = False) -> None:
        """開いている選択肢から、表示名が一致するものを選ぶ（prefix は JOB 番号での前方一致）。"""
        wanted = normalize(value)
        texts = self._option_texts()
        for index, text in enumerate(texts):
            name = normalize(option_name(text))
            if name == wanted or (prefix and name.startswith(f"{wanted} ")):
                self._options().nth(index).click()
                return
        self.page.keyboard.press("Escape")
        raise ZacOptionNotFoundError(field_label, value, [option_name(text) for text in texts])

    def choose_work_kind(self, dialog: Locator, work_kind: str) -> None:
        dialog.locator(self.s("row_work_kind")).first.click()
        self._pick("作業内容", work_kind)

    def choose_project(self, dialog: Locator, job_code: str) -> None:
        project = dialog.locator(self.s("row_project_input")).first
        project.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        project.click()
        project.fill(job_code)
        self._sales_mark = self._sales_loads
        self._pick("案件", job_code, prefix=True)

    def open_sales_options(self, dialog: Locator) -> None:
        """案件を選んだあとの売上項目の読み込みを待ってから、売上項目の選択肢を開く。

        読み込みの前に開くと、前の案件の選択肢が残っていることがある（2026-10-14 の sync-zac で判明）。
        """
        sales = dialog.locator(self.s("row_sales_item")).first
        sales.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
        if not self._wait_sales_loaded(SALES_REQUEST_GRACE_SECONDS):
            # 選択欄を開いたときに読み込む画面の場合は、開いてから待ち、開き直す
            sales.click()
            if not self._wait_sales_loaded(UI_TIMEOUT_MS / 1000):
                self.page.keyboard.press("Escape")
                raise ZacPageError("売上項目の選択肢の読み込みを確認できません（sales_response_pattern を確認してください）")
            self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(SETTLE_MS)
        sales.click()

    def choose_sales_item(self, dialog: Locator, sales_item: str) -> None:
        self.open_sales_options(dialog)
        self._pick("売上項目", sales_item)

    def cancel_dialog(self, dialog: Locator) -> None:
        dialog.locator(self.s("row_cancel")).first.click()
        dialog.wait_for(state="detached", timeout=UI_TIMEOUT_MS)


class ZacMasterReader(ZacBasePage):
    """zac の作業内容・案件・売上項目の選択肢を読むだけの Page Object（sync-zac 用）。

    「登録」「保存」「確定」を押す操作は持たない。開いた作業登録は必ずキャンセルで閉じる。
    """

    def read_masters(self) -> ZacMasters:
        dialog = self.open_register_dialog()
        try:
            dialog.locator(self.s("row_work_kind")).first.click()
            work_kinds = [option_name(text) for text in self._option_texts()]
            work_kinds = [name for name in work_kinds if name]
            self._pick("作業内容", self.config.zac.sync_work_kind)

            project = dialog.locator(self.s("row_project_input")).first
            project.wait_for(state="visible", timeout=UI_TIMEOUT_MS)
            project.click()
            candidates = []
            for text in self._option_texts():
                match = PROJECT_OPTION.match(option_name(text))
                if match:
                    candidates.append((match.group("code"), match.group("name").strip()))
            self.page.keyboard.press("Escape")

            projects: list[dict[str, Any]] = []
            for code, name in candidates:
                self.choose_project(dialog, code)
                self.open_sales_options(dialog)
                items = []
                for text in self._option_texts():
                    item_name = option_name(text)
                    if item_name:
                        items.append({"name": item_name, "is_closed": CLOSED_MARK in text})
                self.page.keyboard.press("Escape")
                projects.append({"code": code, "name": name, "sales_items": items})
        finally:
            self._close_dialog_quietly(dialog)
        return ZacMasters(work_kinds=work_kinds, projects=projects)

    def _close_dialog_quietly(self, dialog: Locator) -> None:
        """後始末として作業登録を閉じる。閉じられなくても元の例外を隠さない（保存はしていない）。"""
        try:
            if dialog.is_visible():
                self.cancel_dialog(dialog)
        except Exception:  # noqa: BLE001
            logger.warning("作業登録のダイアログをキャンセルで閉じられませんでした")


class PlaywrightZacReportPage(ZacBasePage):
    """ZacReportPage（zac/__init__.py）の実装。"""

    def __init__(self, page: Page, config: AgentConfig) -> None:
        super().__init__(page, config)
        self._work_date: date | None = None
        self._save_statuses: list[int] = []
        page.on("response", self._on_response)

    def _on_response(self, response: Response) -> None:
        """保存の通信の結果を記録する（assist で利用者が押した「保存」も検知する）。"""
        if self._work_date is None:
            return
        pattern = self.config.zac.save_response_pattern.format(date=self._work_date.isoformat())
        if pattern and pattern in response.url and response.request.method == "POST":
            self._save_statuses.append(response.status)

    def open(self, work_date: date) -> None:
        self._work_date = work_date
        self._save_statuses.clear()
        super().open(work_date)

    def has_existing_entries(self) -> bool:
        if self.page.locator(self.s("confirmed_indicator")).count() > 0:
            return True
        return self.page.locator(self.s("existing_rows")).count() > 0

    def _set_time(self, key: str, value: str) -> None:
        field_input = self.page.locator(self.s(key)).first
        field_input.fill(value)
        field_input.press("Tab")
        if field_input.input_value() == value:
            return
        # fill が反映されない場合は、選択してから 1 文字ずつ打ち直す
        field_input.click()
        field_input.press("ControlOrMeta+a")
        field_input.press("Backspace")
        field_input.press_sequentially(value)
        field_input.press("Tab")
        actual = field_input.input_value()
        if actual != value:
            raise ZacPageError(f"zac の勤怠欄（{key}）に {value or '空'} を入力できませんでした（画面の値: {actual or '空'}）")

    def fill(self, draft: dict[str, Any]) -> None:
        """工数明細（ドラフトの入力行）と出社・退社を入力する。休憩は fill_breaks で入れる。

        zac は明細を登録するたびに勤怠欄を入れ直すため、出社・退社は明細のあとに入れる。
        """
        attendance = draft.get("attendance") or {}
        for entry in draft.get("entries", []):
            dialog = self.open_register_dialog()
            try:
                self.choose_work_kind(dialog, entry["work_kind"])
                self.choose_project(dialog, entry["job_code"])
                self.choose_sales_item(dialog, entry["sales_item"])
            except ZacOptionNotFoundError:
                if dialog.is_visible():
                    self.cancel_dialog(dialog)
                raise
            minutes = dialog.locator(self.s("row_minutes")).first
            minutes.fill(minutes_to_zac(int(entry["minutes"])))
            minutes.press("Tab")
            dialog.locator(self.s("row_description")).first.fill(entry.get("description", ""))
            dialog.locator(self.s("row_register")).first.click()
            dialog.wait_for(state="detached", timeout=UI_TIMEOUT_MS)
        self._set_time("attendance_start", zac_time(attendance["start"]))
        self._set_time("attendance_end", zac_time(attendance["end"]))

    def fill_breaks(self, breaks: list[dict[str, str]]) -> None:
        """休憩を勤怠欄の時間数に入れる（通常・22〜24時・24〜29時。該当なしは空）。"""
        normal, late, overnight = split_break_minutes(breaks)
        for key, minutes in (("break_normal", normal), ("break_late", late), ("break_overnight", overnight)):
            self._set_time(key, minutes_to_zac(minutes) if minutes else "")

    def screenshot(self, path: Path) -> None:
        self.page.screenshot(path=str(path), full_page=True)

    def click_save(self) -> None:
        """「保存」だけを押す（「確定」は押さない）。"""
        self.page.locator(self.s("save_button")).first.click()

    def wait_saved(self, timeout_seconds: float) -> bool:
        """保存の通信の成功（2xx）、保存完了の表示、または「日報確定済」の表示を待つ。"""
        indicators = [self.s("confirmed_indicator")]
        saved = self.selectors.get("saved_indicator", "")
        if saved:
            indicators.append(saved)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if any(200 <= status < 300 for status in self._save_statuses):
                return True
            if any(self.page.locator(selector).count() > 0 and self.page.locator(selector).first.is_visible() for selector in indicators):
                return True
            self.page.wait_for_timeout(int(POLL_INTERVAL_SECONDS * 1000))
        return False

    def has_error(self) -> bool:
        """保存の通信が失敗した、またはエラー表示がある。"""
        if any(status >= 400 for status in self._save_statuses):
            return True
        selector = self.selectors.get("error_message", "")
        return bool(selector) and self.page.locator(selector).count() > 0


@contextmanager
def zac_browser_page(config: AgentConfig, headed: bool) -> Iterator[Page]:
    profile = ensure_private_dir(config.browser.profile_dir / "zac")
    ensure_private_dir(config.browser.profile_dir)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel=config.browser.channel or None,
            headless=not headed and config.browser.headless,
        )
        try:
            yield context.pages[0] if context.pages else context.new_page()
        finally:
            context.close()
