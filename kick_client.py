"""Cliente da Kick: renova o token (OAuth refresh) e envia mensagens no chat.

O refresh token vem do .env (semente) e, como a Kick pode rotacioná-lo, o mais
recente é guardado no banco (settings 'kick_refresh_token'), o que sobrevive a
reinícios/redeploys (no Discloud o banco persiste).
"""
from __future__ import annotations

import logging
import time

import aiohttp

log = logging.getLogger("oscar.kick")

TOKEN_URL = "https://id.kick.com/oauth/token"
API = "https://api.kick.com/public/v1"


class KickClient:
    def __init__(self, client_id, client_secret, slug, refresh_seed, db) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.slug = slug
        self._seed = refresh_seed
        self.db = db
        self._access: str | None = None
        self._exp = 0.0
        self._broadcaster_id: int | None = None
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _refresh_value(self) -> str:
        v = await self.db.get_setting("kick_refresh_token")
        return v or self._seed

    async def _refresh(self) -> bool:
        rt = await self._refresh_value()
        if not rt:
            return False
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": rt,
        }
        try:
            async with self.session.post(TOKEN_URL, data=data) as r:
                if r.status != 200:
                    log.warning("Kick refresh falhou (%s): %s", r.status, (await r.text())[:200])
                    return False
                tok = await r.json()
        except aiohttp.ClientError as e:
            log.warning("Kick refresh erro de rede: %s", e)
            return False
        self._access = tok.get("access_token")
        self._exp = time.time() + int(tok.get("expires_in", 3600)) - 60
        if tok.get("refresh_token"):
            await self.db.set_setting("kick_refresh_token", tok["refresh_token"])
        return bool(self._access)

    async def _ensure(self) -> bool:
        if self._access and time.time() < self._exp:
            return True
        return await self._refresh()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access}"}

    async def broadcaster_id(self) -> int | None:
        if self._broadcaster_id:
            return self._broadcaster_id
        if not await self._ensure():
            return None
        try:
            async with self.session.get(
                f"{API}/channels", params={"slug": self.slug}, headers=self._headers()
            ) as r:
                if r.status != 200:
                    return None
                data = (await r.json()).get("data") or []
        except aiohttp.ClientError:
            return None
        if data:
            self._broadcaster_id = data[0].get("broadcaster_user_id")
        return self._broadcaster_id

    async def enviar(self, content: str) -> bool:
        """Posta uma mensagem no chat do canal. Retorna True se enviou."""
        if not await self._ensure():
            return False
        bid = await self.broadcaster_id()
        if not bid:
            return False
        payload = {"broadcaster_user_id": bid, "content": content[:480], "type": "user"}
        try:
            async with self.session.post(f"{API}/chat", json=payload, headers=self._headers()) as r:
                if r.status != 200:
                    log.warning("Kick enviar (%s): %s", r.status, (await r.text())[:200])
                    return False
                return True
        except aiohttp.ClientError as e:
            log.warning("Kick enviar erro de rede: %s", e)
            return False
