from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from laborman_agent.config import AgentConfig
from laborman_agent.logs import ensure_private_dir


def manual_login(config: AgentConfig, profile: Path, url: str) -> Path:
    """画面付きのブラウザを専用プロファイルで開き、利用者が手動でサインインしてブラウザを閉じるまで待つ。

    パスワードは入力・保存しない。プロファイル（セッション Cookie を含む）は所有者のみアクセス可能にする。
    """
    ensure_private_dir(config.browser.profile_dir)
    ensure_private_dir(profile)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile),
            channel=config.browser.channel or None,
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url)
            page.wait_for_event("close", timeout=0)
        except PlaywrightError:
            # 利用者がブラウザごと閉じた場合
            pass
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass
    return profile
