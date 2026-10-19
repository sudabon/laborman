from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, cast

import httpx

AttendanceSource = Literal["hr_mail", "manual"]
AttendanceKind = Literal["work", "leave"]


class ApiUnavailableError(Exception):
    """laborman API に接続できない（laborman が起動していないなど）。"""


class ApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ConflictError(ApiError):
    """409 Conflict。"""


class AttendanceConflictError(ConflictError):
    """手入力（manual）の出退勤実績があり、人事メールの値で上書きできない（409）。"""


def _error_message(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return cast(str, detail["message"])
    if isinstance(detail, list):
        return " / ".join(str(item.get("msg", item)) for item in detail if isinstance(item, dict))
    return str(detail)


class LabormanClient:
    """laborman の HTTP API クライアント。エージェントは DB に直接接続しない。"""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LabormanClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ApiUnavailableError(
                f"laborman API（{self.base_url}）に接続できません。laborman が起動しているか確認してください"
            ) from exc
        if response.status_code == 409:
            raise ConflictError(409, _error_message(response))
        if response.is_error:
            raise ApiError(response.status_code, _error_message(response))
        return response.json()

    def health(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/api/health"))

    def get_report(self, work_date: date) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/api/work-reports/{work_date.isoformat()}"))

    def put_attendance(
        self,
        work_date: date,
        start_at: datetime | None,
        end_at: datetime | None,
        *,
        source: AttendanceSource = "hr_mail",
        kind: AttendanceKind = "work",
    ) -> dict[str, Any]:
        payload = {
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
            "source": source,
            "kind": kind,
        }
        try:
            return cast(
                dict[str, Any],
                self._request("PUT", f"/api/work-reports/{work_date.isoformat()}/attendance", json=payload),
            )
        except ConflictError as exc:
            raise AttendanceConflictError(exc.status_code, exc.message) from exc

    def get_automation_settings(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/api/automation-settings"))

    # ---- zac 連携 ----

    def get_zac_draft(self, work_date: date) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/api/work-reports/{work_date.isoformat()}/zac-draft"))

    def create_zac_run(self, work_date: date, mode: str, agent_version: str) -> dict[str, Any]:
        payload = {"work_date": work_date.isoformat(), "mode": mode, "agent_version": agent_version}
        return cast(dict[str, Any], self._request("POST", "/api/zac-sync-runs", json=payload))

    def update_zac_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        """status・message・entries・screenshot_path・mode・agent_version を更新する。"""
        return cast(dict[str, Any], self._request("PATCH", f"/api/zac-sync-runs/{run_id}", json=fields))

    def list_zac_runs(
        self, *, status: str | None = None, work_date: date | None = None, oldest_first: bool = False
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"order": "asc" if oldest_first else "desc"}
        if status:
            params["status"] = status
        if work_date:
            params["work_date"] = work_date.isoformat()
        return cast(list[dict[str, Any]], self._request("GET", "/api/zac-sync-runs", params=params))

    def claim_zac_run(self, run_id: str) -> dict[str, Any]:
        """依頼（requested）を実行中にする。取得済み・取り消し済みなら ConflictError。"""
        return cast(dict[str, Any], self._request("POST", f"/api/zac-sync-runs/{run_id}/claim"))

    def import_zac_masters(self, payload: dict[str, Any]) -> dict[str, Any]:
        """zac の作業内容・案件・売上項目を laborman のマスタに追加・更新する。"""
        return cast(dict[str, Any], self._request("POST", "/api/zac-masters/import", json=payload))

