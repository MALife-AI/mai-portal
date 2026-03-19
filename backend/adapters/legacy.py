"""Legacy System Adapter: 레거시 전문 포맷 변환 + 비동기 격리."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LegacyAdapter:
    """사내 레거시 시스템(Java 등) 호출 어댑터."""

    ERROR_MESSAGES = {
        "E001": "사용자 인증 실패: 레거시 시스템 접근 권한을 확인하세요.",
        "E002": "필수 파라미터 누락: 요청 데이터를 확인하세요.",
        "E003": "레거시 시스템 내부 오류: 관리자에게 문의하세요.",
        "E999": "알 수 없는 오류가 발생했습니다.",
    }

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """레거시 API를 비동기로 호출. 동기 지연을 asyncio.to_thread로 격리."""
        def _sync_call() -> dict[str, Any]:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/{path.lstrip('/')}",
                    json=self._to_legacy_format(payload),
                    headers=headers or {},
                )
                return self._parse_response(resp)

        return await asyncio.to_thread(_sync_call)

    def _to_legacy_format(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Agent 페이로드 → 레거시 전문 포맷."""
        return {
            "header": {
                "txId": payload.get("tx_id", ""),
                "svcId": payload.get("service_id", ""),
                "timestamp": payload.get("timestamp", ""),
            },
            "body": payload.get("data", {}),
        }

    def _parse_response(self, resp: httpx.Response) -> dict[str, Any]:
        """레거시 응답 파싱 + 에러 코드 자연어 변환."""
        try:
            data = resp.json()
        except Exception:
            return {"success": False, "message": "응답 파싱 실패", "raw": resp.text[:500]}

        if resp.status_code >= 400 or data.get("header", {}).get("resultCode") != "0000":
            err_code = data.get("header", {}).get("resultCode", "E999")
            return {
                "success": False,
                "error_code": err_code,
                "message": self.ERROR_MESSAGES.get(err_code, self.ERROR_MESSAGES["E999"]),
                "raw": data,
            }

        return {"success": True, "data": data.get("body", {})}
