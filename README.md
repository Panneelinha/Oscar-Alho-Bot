# Oscar Alho 🧄🎬 — Bot do Discord

Bot que lê os filmes do seu board **OSCAR ALHO** no Trello e, no Discord:

- 🎟️ **anuncia** filmes (manual e automático quando entram no streaming);
- 📅 mostra a **programação** (disponível agora + em breve);
- 🍿 mostra a **ficha** de cada filme (nota IMDb, duração, streaming, pôster);
- 📂 navega o **catálogo** e os **indicados** por categoria;
- 👍 deixa os membros **votarem** e ver o **ranking**.

## Comandos

| Comando | O que faz |
|---|---|
| `/programacao` | O que está disponível e o que vem por aí |
| `/filme <nome>` | Ficha completa (autocomplete pelo nome) |
| `/catalogo [categoria]` | Lista as categorias, ou os filmes de uma |
| `/indicados <categoria>` | Indicados de uma categoria de premiação |
| `/votar <filme>` | "Curtida" em um filme (clicar de novo remove) |
| `/ranking` | Filmes mais curtidos |
| `/meusvotos` | Em quais filmes você curtiu |
| `/votar_categoria <categoria>` | **Cédula secreta**: vote em 1 indicado da categoria |
| `/ranking_categoria <categoria>` | Apuração de uma categoria (só números) |
| `/apuracao` | Líder de cada categoria |
| `/anunciar <filme>` | (admin) Posta um anúncio no canal |
| `/sincronizar_trello` | (admin) Grava o placar de votos no Trello agora |

Os anúncios também trazem um botão **👍 Votar** que funciona mesmo depois de reiniciar o bot.

### Dois tipos de voto
- **Curtida** (`/votar`): hype geral em qualquer filme, vários por pessoa, público.
- **Cédula por categoria** (`/votar_categoria`): estilo Oscar — **um voto por categoria**, escolhido num menu, **secreto** (a mensagem só aparece pra quem vota; o ranking mostra apenas números). Votar de novo troca o voto.

### Placar diário no Trello (sigiloso)
Uma vez por dia (hora configurável) o bot grava nos cards **apenas os números** de votos —
nunca quem votou. Por padrão atualiza um bloco fixo no fim da descrição do card:

```
———————————
🗳️ Oscar Alho — votação (Discord)
🏆 Votos na categoria: 9
👍 Curtidas: 4
_atualizado em 28/06/2026_
```

O valor é **substituído** a cada dia (não acumula). Dá pra trocar para o modo
comentário ou desligar via `VOTE_SYNC_MODE`. Use `/sincronizar_trello` para rodar na hora.
> O token do Trello precisa ter permissão de **escrita** (os tokens normais já têm).

## Como rodar

### 1. Pré‑requisitos
- Python 3.10+ (testado no 3.13)
- Um bot criado no [Discord Developer Portal](https://discord.com/developers/applications)

### 2. Instalar
```bash
cd oscar-alho-bot
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar
Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

- **DISCORD_TOKEN** — Developer Portal → sua aplicação → *Bot* → *Reset Token*.
- **TRELLO_API_KEY / TRELLO_TOKEN** — em <https://trello.com/power-ups/admin> crie um Power‑Up e gere a *API Key*; depois clique em *Token* para autorizar e copiar o token (use a conta **panneelinha**, dona do board).
- **TRELLO_BOARD_ID** — já vem preenchido com o board OSCAR ALHO (`6a2a1f1c8edcf60ea0226a9a`).
- **ANNOUNCE_CHANNEL_ID** — (opcional) ID do canal de anúncios. Ative *Modo Desenvolvedor* no Discord (Configurações → Avançado), clique com o botão direito no canal → *Copiar ID*.
- **GUILD_ID** — (opcional) ID do seu servidor. Com ele, os comandos aparecem na hora; sem ele, o registro é global e pode levar até 1h na primeira vez.

### 4. Convidar o bot pro servidor
No Developer Portal → *OAuth2 → URL Generator*: marque os escopos `bot` e `applications.commands`, e a permissão *Send Messages*. Abra a URL gerada e adicione ao servidor.

### 5. Rodar
```bash
python bot.py
```

## Como funcionam os anúncios automáticos
A cada `POLL_MINUTES` (padrão 30) o bot relê a lista **STREAMING - DISPONÍVEL** do Trello.
Na **primeira** execução ele apenas registra os filmes que já estão lá (sem postar, pra não floodar).
A partir daí, todo filme **novo** que aparecer como disponível vira um anúncio no canal configurado.

## Estrutura

```
oscar-alho-bot/
├── bot.py            # entrypoint; sobe o cliente e os cogs
├── config.py         # lê o .env
├── trello_client.py  # acesso à API do Trello (isolado aqui)
├── movies.py         # modelo Movie + parser do desc dos cards
├── catalog.py        # cache + consultas (programação, busca, categorias)
├── db.py             # SQLite: votos e controle de anúncios
├── embeds.py         # cartões visuais do Discord
├── ui.py             # botão de votar persistente
├── cogs/
│   ├── filmes.py     # /programacao /filme /catalogo /indicados
│   ├── votacao.py    # /votar /ranking /meusvotos
│   ├── categorias.py # /votar_categoria /ranking_categoria /apuracao
│   ├── anuncios.py   # /anunciar + tarefa automática
│   └── trello_sync.py# placar diário de votos no Trello (só números)
└── test_parser.py    # testes offline do parser (python test_parser.py)
```

## Trocar o Trello pelo Composio
Todo o acesso ao Trello está em `trello_client.py`. Se preferir usar o **Composio SDK**
no runtime em vez da API REST direta, basta reimplementar os métodos
`get_lists_with_cards` e `get_card_attachments` chamando o Composio — o resto do bot
não muda. A API REST foi escolhida como padrão por ser estável e não depender de
versão de SDK num processo que roda 24/7.

## Notas
- O parser entende o padrão dos seus cards (`Estreia`, `Streaming: X — data`, `Duração`,
  bloco `## IMDb`). Cards sem esses campos simplesmente exibem menos informação.
- Os votos são por usuário do Discord e ficam em `oscar_alho.sqlite3` (local).
## Site + Supabase

A ponte opcional `cogs/site_sync.py` consome a outbox criada pela migration do site e sincroniza comentários, votos e presenças com os cards do Trello. Para ativar no ambiente privado do bot:

```env
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_POLL_SECONDS=30
```

A `SUPABASE_SECRET_KEY` fica somente no bot. Não coloque essa chave no site, no Git ou em mensagens públicas. Quando as variáveis não existem, a ponte permanece desligada e o restante do bot funciona normalmente.
