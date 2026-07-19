"""Cliente REST mínimo do Supabase usado apenas pela ponte Site → bot.

A chave secreta do Supabase nunca deve ser enviada ao navegador; ela fica
somente no ambiente privado onde o bot roda.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp


class SupabaseSyncError(RuntimeError):
    pass


class SupabaseSyncClient:
    def __init__(self, url: str, secret_key: str) -> None:
        self.url = url.rstrip("/")
        self._headers = {
            "apikey": secret_key,
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self._headers["apikey"])

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, path: str, *, json: object | None = None) -> Any:
        async with self.session.request(method, f"{self.url}/rest/v1{path}", json=json) as resp:
            body = await resp.text()
            if resp.status >= 300:
                raise SupabaseSyncError(f"{method} {path} -> HTTP {resp.status}: {body[:240]}")
            if not body:
                return None
            try:
                return await resp.json()
            except (aiohttp.ContentTypeError, ValueError):
                return body

    async def claim_events(self, batch_size: int = 20) -> list[dict]:
        data = await self._request(
            "POST", "/rpc/claim_sync_events", json={"batch_size": max(1, min(batch_size, 100))}
        )
        return data if isinstance(data, list) else []

    async def profile(self, user_id: str) -> dict:
        data = await self._request(
            "GET", f"/profiles?id=eq.{user_id}&select=display_name,avatar_url&limit=1"
        )
        return data[0] if isinstance(data, list) and data else {}

    async def movie_vote_count(self, movie_id: str) -> int:
        data = await self._request(
            "POST", "/rpc/get_movie_vote_count", json={"target_movie_id": movie_id}
        )
        return int(data or 0)

    async def mark_processed(self, event_id: int) -> None:
        await self._request(
            "PATCH",
            f"/sync_outbox?id=eq.{event_id}",
            json={"status": "processed", "processed_at": datetime.now(timezone.utc).isoformat(), "last_error": None},
        )

    async def mark_failed(self, event_id: int, error: str, attempts: int) -> None:
        delay = min(60, max(1, 2 ** max(0, attempts - 1)))
        retry_at = datetime.now(timezone.utc) + timedelta(minutes=delay)
        await self._request(
            "PATCH",
            f"/sync_outbox?id=eq.{event_id}",
            json={
                "status": "failed",
                "last_error": error[:500],
                "next_attempt_at": retry_at.isoformat(),
            },
        )