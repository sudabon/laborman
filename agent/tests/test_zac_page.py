from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from laborman_agent.config import DEFAULT_ZAC_SELECTORS, AgentConfig, ZacConfig
from laborman_agent.zac.report_page import (
    PlaywrightZacReportPage,
    ZacMasterReader,
    ZacOptionNotFoundError,
    ZacPageError,
    minutes_to_zac,
    option_name,
    split_break_minutes,
    zac_time,
)

FIXTURES = Path(__file__).parent / "fixtures" / "zac"
SALES_URL = "**/api/v2/reference/daily_report_project_sales**"
TARGET = date(2026, 10, 13)

STATE: dict[str, Any] = {
    "workKinds": ["プロジェクト作業", "プロジェクト関連打ち合わせ", "プロジェクト業務（QA）"],
    "projects": [
        {
            "code": "2602028",
            "name": "エンジンファーム様プロジェクトサポート（2026／09-2026／12）",
            "sales": [
                {"name": "プロジェクトサポート（2026／09）", "closed": True},
                {"name": "プロジェクトサポート（2026／10）", "closed": False},
            ],
        },
        {"code": "2601570", "name": "サービス開発本部 make.AI 業務", "sales": [{"name": "サービス開発本部 make.AI 業務"}]},
    ],
}

DRAFT: dict[str, Any] = {
    "attendance": {"start": "08:29", "end": "18:38", "source": "hr_mail"},
    "breaks": [{"start": "12:00", "end": "13:00"}],
    "entries": [
        {
            "work_kind": "プロジェクト作業",
            "job_code": "2602028",
            "sales_item": "プロジェクトサポート（2026／10）",
            "minutes": 300,
            "description": "- 設計レビュー\n- 障害調査",
        },
        {
            "work_kind": "プロジェクト関連打ち合わせ",
            "job_code": "2601570",
            "sales_item": "サービス開発本部 make.AI 業務",
            "minutes": 210,
            "description": "- 定例MTG",
        },
    ],
}


def zac_config(tmp_path: Path, **selectors: str) -> AgentConfig:
    return AgentConfig(
        path=tmp_path / "config.toml",
        exists=False,
        zac=ZacConfig(
            base_url=FIXTURES.as_uri(),
            report_url_template="{base_url}/daily_report.html",
            login_id="yu-suda",
            selectors={**DEFAULT_ZAC_SELECTORS, **selectors},
        ),
    )


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def open_page(browser: Browser) -> Iterator[Any]:
    pages: list[Page] = []

    def opener(state: dict[str, Any] | None = None) -> Page:
        page = browser.new_page()
        pages.append(page)
        page.add_init_script(f"window.__ZAC__ = {json.dumps(state if state is not None else STATE)};")
        # 案件を選んだあとの売上項目の読み込み（実画面の通信を模擬）
        page.route(SALES_URL, lambda route: route.fulfill(status=200, body="[]"))
        return page

    yield opener
    for page in pages:
        page.close()


def clicks(page: Page) -> dict[str, int]:
    result: dict[str, int] = page.evaluate("window.__CLICKS__")
    return result


# ---- 純粋関数 ----


@pytest.mark.parametrize(
    ("breaks", "expected"),
    [
        ([{"start": "12:00", "end": "13:00"}], (60, 0, 0)),
        ([{"start": "12:00", "end": "13:00"}, {"start": "23:30", "end": "24:15"}], (60, 30, 15)),
        ([{"start": "21:30", "end": "22:30"}], (30, 30, 0)),
        ([], (0, 0, 0)),
    ],
)
def test_split_break_minutes(breaks: list[dict[str, str]], expected: tuple[int, int, int]) -> None:
    assert split_break_minutes(breaks) == expected


def test_time_formats() -> None:
    assert minutes_to_zac(300) == "5:00"
    assert minutes_to_zac(45) == "0:45"
    assert zac_time("08:29") == "8:29"
    assert zac_time("25:15") == "25:15"
    assert option_name("プロジェクトサポート（2026／09）\n\n売上計上済") == "プロジェクトサポート（2026／09）"


# ---- sync-zac の読み取り ----


def test_master_reader_reads_options_without_registering(open_page: Any, tmp_path: Path) -> None:
    page = open_page()
    reader = ZacMasterReader(page, zac_config(tmp_path))
    reader.open(TARGET)

    masters = reader.read_masters()

    assert masters.work_kinds == ["プロジェクト作業", "プロジェクト関連打ち合わせ", "プロジェクト業務（QA）"]
    assert masters.projects == [
        {
            "code": "2602028",
            "name": "エンジンファーム様プロジェクトサポート（2026／09-2026／12）",
            "sales_items": [
                {"name": "プロジェクトサポート（2026／09）", "is_closed": True},
                {"name": "プロジェクトサポート（2026／10）", "is_closed": False},
            ],
        },
        {
            "code": "2601570",
            "name": "サービス開発本部 make.AI 業務",
            "sales_items": [{"name": "サービス開発本部 make.AI 業務", "is_closed": False}],
        },
    ]
    # 「登録」「保存」「確定」は一度も押さず、ダイアログは閉じている
    assert clicks(page) == {"register": 0, "save": 0, "confirm": 0}
    assert page.locator(".dialog").count() == 0


def test_master_reader_waits_for_sales_items_of_each_project(open_page: Any, tmp_path: Path) -> None:
    # 売上項目は案件を選んだあとの通信の応答で入れ替わる。応答の前に読むと前の案件の選択肢になる
    page = open_page({**STATE, "projects": [*STATE["projects"], {"code": "2600901", "name": "社内管理業務", "sales": [{"name": "外部研修"}]}]})
    reader = ZacMasterReader(page, zac_config(tmp_path))
    reader.open(TARGET)

    masters = reader.read_masters()

    assert {p["code"]: [item["name"] for item in p["sales_items"]] for p in masters.projects} == {
        "2602028": ["プロジェクトサポート（2026／09）", "プロジェクトサポート（2026／10）"],
        "2601570": ["サービス開発本部 make.AI 業務"],
        "2600901": ["外部研修"],
    }


def test_master_reader_needs_unconfirmed_day(open_page: Any, tmp_path: Path) -> None:
    page = open_page({**STATE, "confirmed": True})
    reader = ZacMasterReader(page, zac_config(tmp_path))
    reader.open(TARGET)
    with pytest.raises(ZacPageError, match="確定済み"):
        reader.read_masters()


# ---- 業務報告の入力 ----


def test_fill_enters_attendance_rows_and_breaks_without_saving(open_page: Any, tmp_path: Path) -> None:
    page = open_page()
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    assert zac.is_login_page() is False
    assert zac.has_existing_entries() is False

    zac.fill(DRAFT)
    zac.fill_breaks([{"start": "12:00", "end": "13:00"}, {"start": "23:30", "end": "24:15"}])

    def value(name: str) -> str:
        return str(page.locator(f"zac-time-duration-input[formcontrolname={name}] input").input_value())

    assert (value("TimeIn"), value("TimeOut")) == ("8:29", "18:38")
    assert (value("TimeBreak"), value("TimeBreak3"), value("TimeBreak4")) == ("1:00", "0:30", "0:15")
    rows = page.locator("tr.zac-row.cdk-row.data-row").all_inner_texts()
    assert rows == [
        "プロジェクト作業 / #2602028 / プロジェクトサポート（2026／10） / 5:00 / - 設計レビュー\n- 障害調査",
        "プロジェクト関連打ち合わせ / #2601570 / サービス開発本部 make.AI 業務 / 3:30 / - 定例MTG",
    ]
    # 工数明細に休憩の行は入れない。保存・確定は押していない
    assert clicks(page) == {"register": 2, "save": 0, "confirm": 0}
    assert zac.has_existing_entries() is True


def test_fill_waits_for_options_loaded_after_sign_in(open_page: Any, tmp_path: Path) -> None:
    # サインイン直後は作業内容の選択肢を後から読み込み、それまでは空の項目だけが出る（2026-10-19）
    page = open_page({**STATE, "optionsDelayMs": 800})
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)

    zac.fill({**DRAFT, "entries": DRAFT["entries"][:1]})

    rows = page.locator("tr.zac-row.cdk-row.data-row").all_inner_texts()
    assert rows == ["プロジェクト作業 / #2602028 / プロジェクトサポート（2026／10） / 5:00 / - 設計レビュー\n- 障害調査"]


def test_fill_clears_unused_break_bands(open_page: Any, tmp_path: Path) -> None:
    page = open_page()
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    zac.fill_breaks([{"start": "12:00", "end": "12:45"}])
    breaks = [
        page.locator(f"zac-time-duration-input[formcontrolname={name}] input").input_value()
        for name in ("TimeBreak", "TimeBreak3", "TimeBreak4")
    ]
    assert breaks == ["0:45", "", ""]


@pytest.mark.parametrize(
    ("entry_change", "field_label"),
    [
        ({"sales_item": "プロジェクトサポート（2027／01）"}, "売上項目"),
        ({"job_code": "2609999"}, "案件"),
        ({"work_kind": "プロジェクト作業（存在しない）"}, "作業内容"),
    ],
)
def test_fill_stops_when_option_is_missing(
    open_page: Any, tmp_path: Path, entry_change: dict[str, str], field_label: str
) -> None:
    page = open_page()
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    draft = {**DRAFT, "entries": [{**DRAFT["entries"][0], **entry_change}]}

    with pytest.raises(ZacOptionNotFoundError) as info:
        zac.fill(draft)

    assert info.value.field_label == field_label
    assert clicks(page) == {"register": 0, "save": 0, "confirm": 0}
    assert page.locator(".dialog").count() == 0


def test_prefix_match_does_not_pick_a_longer_work_kind(open_page: Any, tmp_path: Path) -> None:
    # 「プロジェクト業務」は「プロジェクト業務（QA）」と一致させない（完全一致）
    page = open_page()
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    draft = {**DRAFT, "entries": [{**DRAFT["entries"][0], "work_kind": "プロジェクト業務"}]}
    with pytest.raises(ZacOptionNotFoundError):
        zac.fill(draft)


def test_existing_entries_and_confirmed_day(open_page: Any, tmp_path: Path) -> None:
    rows = [{"workKind": "プロジェクト作業", "code": "2602028", "sales": "x", "time": "5:00", "memo": ""}]
    page = open_page({**STATE, "rows": rows})
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    assert zac.has_existing_entries() is True

    confirmed = open_page({**STATE, "confirmed": True})
    zac = PlaywrightZacReportPage(confirmed, zac_config(tmp_path))
    zac.open(TARGET)
    assert zac.has_existing_entries() is True


SAVE_URL = "**/api/v2/daily_report/daily_reports/2026-10-13/save"


def test_save_is_confirmed_by_the_save_request(open_page: Any, tmp_path: Path) -> None:
    # zac は保存しても画面にメッセージを出さないので、保存の通信の成功で判定する
    page = open_page({**STATE, "saveShows": ""})
    page.route(SAVE_URL, lambda route: route.fulfill(status=200, body="{}"))
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)

    zac.click_save()

    assert zac.wait_saved(5) is True
    assert clicks(page) == {"register": 0, "save": 1, "confirm": 0}
    assert zac.has_error() is False


def test_failed_save_request_is_an_error(open_page: Any, tmp_path: Path) -> None:
    page = open_page({**STATE, "saveShows": ""})
    page.route(SAVE_URL, lambda route: route.fulfill(status=500, body="{}"))
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    zac.click_save()
    assert zac.wait_saved(1) is False
    assert zac.has_error() is True


def test_save_indicator_can_also_be_configured(open_page: Any, tmp_path: Path) -> None:
    page = open_page()
    page.route(SAVE_URL, lambda route: route.abort())
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path, saved_indicator="#toast:has-text('保存しました')"))
    zac.open(TARGET)
    zac.click_save()
    assert zac.wait_saved(5) is True


def test_wait_saved_times_out_without_save(open_page: Any, tmp_path: Path) -> None:
    page = open_page({**STATE, "saveShows": ""})
    page.route(SAVE_URL, lambda route: route.abort())
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    zac.click_save()
    assert zac.wait_saved(1) is False


def test_screenshot(open_page: Any, tmp_path: Path) -> None:
    page = open_page()
    zac = PlaywrightZacReportPage(page, zac_config(tmp_path))
    zac.open(TARGET)
    path = tmp_path / "shot.png"
    zac.screenshot(path)
    assert path.stat().st_size > 0


# ---- サインイン ----


def test_login_page_detection_and_login(browser: Browser, tmp_path: Path) -> None:
    page = browser.new_page()
    config = zac_config(tmp_path)
    config = AgentConfig(**{**config.__dict__, "zac": ZacConfig(**{**config.zac.__dict__, "report_url_template": "{base_url}/logon.html"})})
    zac = PlaywrightZacReportPage(page, config)
    zac.open(TARGET)
    assert zac.is_login_page() is True

    zac.login("yu-suda", "s3cr3t-pw")

    assert page.evaluate("window.__LOGIN__") == {"id": "yu-suda", "pw": len("s3cr3t-pw")}
    page.close()
