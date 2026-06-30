"""Copia o refresh token válido (que o bot mantém no banco, pois a Kick rotaciona)
para o .env. Rode ANTES de empacotar/subir para o Discloud, com o bot DESLIGADO.

    python atualizar_token_kick.py
"""
from __future__ import annotations

import asyncio
import pathlib
import re

from db import Database


async def main() -> None:
    db = Database("oscar_alho.sqlite3")
    await db.connect()
    token = await db.get_setting("kick_refresh_token")
    await db.close()
    if not token:
        print("Nenhum token da Kick no banco ainda (o bot precisa ter rodado a Kick).")
        return
    env = pathlib.Path(".env")
    if not env.exists():
        print(".env não encontrado.")
        return
    txt = env.read_text(encoding="utf-8")
    if re.search(r"(?m)^KICK_REFRESH_TOKEN=", txt):
        txt = re.sub(r"(?m)^KICK_REFRESH_TOKEN=.*$", f"KICK_REFRESH_TOKEN={token}", txt)
    else:
        txt = txt.rstrip() + f"\nKICK_REFRESH_TOKEN={token}\n"
    env.write_text(txt, encoding="utf-8")
    print("✅ KICK_REFRESH_TOKEN do .env atualizado com o token válido do banco.")
    print("   Agora pode empacotar/subir para o Discloud.")


if __name__ == "__main__":
    main_coro = main()
    asyncio.run(main_coro)
