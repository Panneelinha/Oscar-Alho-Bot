"""Cliente fino para a API REST do Trello (mesma coisa que o Composio faz por baixo).

Isola todo o acesso ao Trello num só lugar. Se um dia você quiser trocar por
outra fonte (Composio SDK, banco, etc.), basta reimplementar estes métodos.
"""
from __future__ import annotations

import aiohttp

BASE = "https://api.trello.com/1"


class TrelloError(RuntimeError):
    pass


class TrelloClient:
    def __init__(self, key: str, token: str, board_id: str) -> None:
        self._auth = {"key": key, "token": token}
        self.board_id = board_id
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "TrelloClient":
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, path: str, **params) -> object:
        params.update(self._auth)
        async with self.session.request(method, f"{BASE}{path}", params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise TrelloError(f"{method} {path} -> HTTP {resp.status}: {body[:200]}")
            return await resp.json()

    async def _get(self, path: str, **params) -> object:
        return await self._request("GET", path, **params)

    async def get_lists_with_cards(self) -> list[dict]:
        """Retorna as listas abertas do board, cada uma com seus cards abertos."""
        data = await self._get(
            f"/boards/{self.board_id}/lists",
            cards="open",
            card_fields="name,desc,due,labels,idMembersVoted,badges,url,shortUrl,idAttachmentCover,dateLastActivity,pos",
            fields="name,pos",
            filter="open",
        )
        if not isinstance(data, list):
            raise TrelloError("Resposta inesperada do Trello ao listar listas.")
        return data

    async def get_board_last_activity(self) -> str:
        """Marca leve usada para detectar mudanças no board sem baixar todos os cards."""
        data = await self._get(
            f"/boards/{self.board_id}",
            fields="dateLastActivity",
        )
        return str(data.get("dateLastActivity") or "") if isinstance(data, dict) else ""

    async def update_card_desc(self, card_id: str, desc: str) -> None:
        """Sobrescreve a descrição do card (usado para gravar o placar de votos)."""
        await self._request("PUT", f"/cards/{card_id}", desc=desc)

    async def create_card(self, name: str, list_id: str, desc: str = "") -> dict:
        """Cria um card numa lista. Retorna o card criado (com id/shortUrl)."""
        data = await self._request("POST", "/cards", idList=list_id, name=name, desc=desc)
        return data if isinstance(data, dict) else {}

    async def move_card(self, card_id: str, list_id: str) -> None:
        await self._request("PUT", f"/cards/{card_id}", idList=list_id)

    async def add_comment(self, card_id: str, text: str) -> None:
        await self._request("POST", f"/cards/{card_id}/actions/comments", text=text)

    async def get_card_attachments(self, card_id: str) -> list[dict]:
        data = await self._get(f"/cards/{card_id}/attachments", fields="id,name,url,mimeType,date")
        return data if isinstance(data, list) else []

    async def get_card_comments(self, card_id: str, limit: int = 20) -> list[str]:
        """Textos dos comentários do card, do mais recente para o mais antigo."""
        data = await self._get(
            f"/cards/{card_id}/actions", filter="commentCard", limit=str(limit)
        )
        if not isinstance(data, list):
            return []
        return [
            a["data"]["text"]
            for a in data
            if a.get("data", {}).get("text")
        ]

    async def download_attachment(self, url: str) -> bytes | None:
        """Baixa o conteúdo de um anexo privado do Trello (requer header OAuth)."""
        headers = {
            "Authorization": (
                f'OAuth oauth_consumer_key="{self._auth["key"]}", '
                f'oauth_token="{self._auth["token"]}"'
            )
        }
        try:
            async with self.session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
        except aiohttp.ClientError:
            return None

    async def get_poster(self, card_id: str) -> tuple[bytes, str] | None:
        """Retorna (bytes, nome_do_arquivo) do pôster do card, ou None."""
        url = await self.first_image_url({"id": card_id, "badges": {"attachments": 1}})
        if not url:
            return None
        data = await self.download_attachment(url)
        if not data:
            return None
        nome = url.rstrip("/").split("/")[-1] or "poster.jpg"
        return data, nome

    async def first_image_url(self, card: dict) -> str | None:
        """URL da primeira imagem anexada (pôster), se houver."""
        badges = card.get("badges") or {}
        if not badges.get("attachments"):
            return None
        try:
            attachments = await self.get_card_attachments(card["id"])
        except TrelloError:
            return None
        for att in attachments:
            mime = (att.get("mimeType") or "").lower()
            url = att.get("url") or ""
            if mime.startswith("image/") or url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif")
            ):
                return url
        return None
