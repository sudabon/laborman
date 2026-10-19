from __future__ import annotations

import subprocess
from typing import Any

from laborman_agent.zac.credentials import has_password, read_password, registration_hint

SECRET = "s3cr3t-パスワード"


class FakeSecurity:
    def __init__(self, returncode: int = 0, stdout: str = SECRET + "\n", error: Exception | None = None) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.error = error
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        assert kwargs["capture_output"] is True
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(command, self.returncode, stdout=self.stdout, stderr="")


def test_reads_password_from_keychain() -> None:
    security = FakeSecurity()
    assert read_password("laborman-agent.zac", "yu-suda", security) == SECRET
    assert security.calls == [["security", "find-generic-password", "-s", "laborman-agent.zac", "-a", "yu-suda", "-w"]]


def test_missing_password_is_none() -> None:
    assert read_password("laborman-agent.zac", "yu-suda", FakeSecurity(returncode=44, stdout="")) is None
    assert has_password("laborman-agent.zac", "yu-suda", FakeSecurity(returncode=44, stdout="")) is False


def test_without_login_id_does_not_call_security() -> None:
    security = FakeSecurity()
    assert read_password("laborman-agent.zac", "", security) is None
    assert security.calls == []


def test_security_command_failure_is_none() -> None:
    assert read_password("s", "u", FakeSecurity(error=FileNotFoundError("security"))) is None
    assert read_password("s", "u", FakeSecurity(error=subprocess.TimeoutExpired("security", 10))) is None


def test_registration_hint() -> None:
    assert registration_hint("laborman-agent.zac", "yu-suda") == (
        "security add-generic-password -s laborman-agent.zac -a yu-suda -w"
    )
