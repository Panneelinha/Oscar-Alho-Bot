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

    async def movie_interest_count(self, movie_id: str) -> int:
        data = await self._request(
            "POST", "/rpc/get_movie_interest_count", json={"target_movie_id": movie_id}
        )
        return int(data or 0)

    async def movie_interest_ranking(self, limit: int = 20) -> list[dict]:
        data = await self._request(
            "POST",
            "/rpc/get_movie_interest_ranking",
            json={"result_limit": max(1, min(limit, 100))},
        )
        return data if isinstance(data, list) else []

    async def set_bot_interest_count(self, movie_id: str, count: int) -> None:
        await self._request(
            "POST",
            "/rpc/set_bot_movie_interest_count",
            json={"target_movie_id": movie_id, "target_count": max(0, int(count))},
        )

    async def movie_rating_count(self, movie_id: str) -> tuple[float | None, int]:
        data = await self._request(
            "POST", "/rpc/get_movie_rating_count", json={"target_movie_id": movie_id}
        )
        row = data[0] if isinstance(data, list) and data else {}
        count = int(row.get("rating_count") or 0)
        average = row.get("average_score")
        return (float(average) if average is not None else None, count)

    async def movie_rating_ranking(self, limit: int = 20) -> list[dict]:
        data = await self._request(
            "POST",
            "/rpc/get_movie_rating_ranking",
            json={"result_limit": max(1, min(limit, 100))},
        )
        return data if isinstance(data, list) else []

    async def set_bot_rating_summary(
        self, movie_id: str, rating_sum: int, rating_count: int
    ) -> None:
        await self._request(
            "POST",
            "/rpc/set_bot_movie_rating_summary",
            json={
                "target_movie_id": movie_id,
                "target_rating_sum": max(0, int(rating_sum)),
                "target_rating_count": max(0, int(rating_count)),
            },
        )

    async def site_points_by_discord(self) -> dict[int, int]:
        data = await self._request("POST", "/rpc/get_site_points_for_bot", json={})
        if not isinstance(data, list):
            return {}
        points: dict[int, int] = {}
        for row in data:
            try:
                points[int(row["discord_user_id"])] = int(row.get("site_points") or 0)
            except (KeyError, TypeError, ValueError):
                continue
        return points

    async def set_bot_points(self, discord_user_id: str, points: int) -> None:
        await self._request(
            "POST",
            "/rpc/set_bot_points",
            json={
                "target_discord_user_id": discord_user_id,
                "target_points": max(0, int(points)),
            },
        )

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