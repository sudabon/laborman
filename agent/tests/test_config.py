from __future__ import annotations

from pathlib import Path

import pytest

from laborman_agent.config import (
    DEFAULT_API_BASE_URL,
    DEFAULT_OWA_SELECTORS,
    DEFAULT_PARSER_PATTERNS,
    ConfigError,
    load_config,
)


def write_config(path: Path, text: str, mode: int = 0o600) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def test_defaults_when_file_is_missing(tmp_path: Path) -> None:
    config = load_config(tmp_path / "missing.toml")
    assert config.exists is False
    assert config.api_base_url == DEFAULT_API_BASE_URL
    assert config.owa.selectors == DEFAULT_OWA_SELECTORS
    assert config.owa.parser == DEFAULT_PARSER_PATTERNS
    assert config.logs.retention_days == 14
    assert config.warnings == ()


def test_overrides_merge_with_defaults(tmp_path: Path) -> None:
    path = write_config(
        tmp_path / "config.toml",
        """
[laborman]
api_base_url = "http://127.0.0.1:9999/"

[browser]
profile_dir = "~/profiles"
channel = "msedge"
headless = false

[owa]
search_query = 'subject:"{hr_mail_subject_keyword}{target_date}"'

[owa.selectors]
search_box = "#searchBox"

[owa.parser]
body_start_pattern = 'Start\\s*(?P<start>\\d{1,2}:\\d{2})'

[logs]
dir = "/tmp/laborman-agent-logs"
retention_days = 7
""",
    )
    config = load_config(path)
    assert config.exists is True
    assert config.api_base_url == "http://127.0.0.1:9999"
    assert config.browser.profile_dir == Path("~/profiles").expanduser()
    assert config.browser.channel == "msedge"
    assert config.browser.headless is False
    assert config.owa.search_query == 'subject:"{hr_mail_subject_keyword}{target_date}"'
    assert config.owa.selectors["search_box"] == "#searchBox"
    # 上書きしていない項目は既定値のまま
    assert config.owa.selectors["message_body"] == DEFAULT_OWA_SELECTORS["message_body"]
    assert config.owa.parser["body_start_pattern"] == r"Start\s*(?P<start>\d{1,2}:\d{2})"
    assert config.owa.parser["subject_pattern"] == DEFAULT_PARSER_PATTERNS["subject_pattern"]
    assert config.logs.dir == Path("/tmp/laborman-agent-logs")
    assert config.logs.retention_days == 7


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
def test_warns_when_permission_is_loose(tmp_path: Path, mode: int) -> None:
    path = write_config(tmp_path / "config.toml", "", mode)
    config = load_config(path)
    assert len(config.warnings) == 1
    assert "chmod 600" in config.warnings[0]


def test_no_warning_for_owner_only(tmp_path: Path) -> None:
    assert load_config(write_config(tmp_path / "config.toml", "", 0o600)).warnings == ()


def test_invalid_toml_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path / "config.toml", "[owa\n"))
