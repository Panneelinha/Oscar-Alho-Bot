# Deploy do Oscar Alho 🚀

Dois cenários: **rodar no seu PC** (agora) e **Discloud** (quando finalizar).

---

## 1. Rodar no seu PC (agora)

### Primeira vez
```powershell
cd oscar-alho-bot
pip install -r requirements.txt
```
Confirme que o `.env` está preenchido (DISCORD_TOKEN, TRELLO_API_KEY, TRELLO_TOKEN…).

### Ligar o bot
Dê **dois cliques** em **`start.bat`**. Ele:
- inicia o bot,
- **reinicia sozinho** se cair,
- mostra os logs na janela.

Para **desligar**, feche a janela.

> ⚠️ O bot só fica online enquanto **essa janela** estiver aberta e o PC ligado.

### (Opcional) Iniciar junto com o Windows
1. Tecla **Windows + R** → digite `shell:startup` → Enter (abre a pasta de Inicializar).
2. Clique com o botão direito em `start.bat` → **Enviar para → Área de trabalho (criar atalho)**.
3. Mova esse atalho para dentro da pasta de Inicializar.

Assim o bot sobe sozinho toda vez que você liga o PC. (Para não abrir a janela na cara,
dá para configurar via Agendador de Tarefas — me peça que eu monto.)

---

## 2. Discloud (produção 24/7)

O projeto já vem pronto: tem **`discloud.config`** e **`.discloudignore`**.

### Passo a passo
1. Crie conta em **<https://discloud.com>** e entre no servidor de Discord deles (o painel/upload é por lá ou pelo site).
2. **Garanta que o `.env` está preenchido** — ele vai junto no upload e carrega os tokens.
3. Gere o **.zip** do projeto:
   - Selecione **todos os arquivos** da pasta `oscar-alho-bot` (não a pasta, mas o conteúdo) e compacte em `.zip`.
   - Não se preocupe com `.venv`, cache e o banco local: o **`.discloudignore`** já manda ignorar (se usar a CLI/extensão do Discloud). No upload manual pelo site, evite incluir a pasta `.venv`.
4. No painel do Discloud, faça **Upload** do `.zip` e **inicie** a aplicação.

### Detalhes que já deixei resolvidos
- **`discloud.config`**: `MAIN=bot.py`, `TYPE=bot`, `RAM=256`, `AUTORESTART=true`.
- **Banco persistente**: o `*.sqlite3` está no `.discloudignore`, então **re-deploys não apagam os votos/indicações** — o Discloud mantém os arquivos criados em runtime.
- **Python + dependências**: detectados pelo `requirements.txt` automaticamente.

### Variáveis de ambiente no Discloud
Duas opções (escolha uma):
- **Mais simples:** deixe o `.env` dentro do `.zip` (o bot lê via python-dotenv).
- **Mais seguro:** suba sem o `.env` e cadastre as variáveis pelo painel/CLI do Discloud
  (DISCORD_TOKEN, TRELLO_API_KEY, TRELLO_TOKEN, GUILD_ID, ANNOUNCE_CHANNEL_ID, etc.).

### RAM
`RAM=256` é uma folga segura. Se seu plano tiver menos, dá para baixar para `128`
(o bot é leve), mas evite `100` por causa dos picos ao baixar pôster.

---

## Telegram e Kick (opcionais)
Se você usa as pontes, inclua no `.env` (ou no painel de variáveis do Discloud):
- **Telegram:** `TELEGRAM_TOKEN`, `TELEGRAM_ALLOWED_IDS`, `TELEGRAM_CHAT_ID`.
- **Kick:** `KICK_CHANNEL_SLUG`, `KICK_CLIENT_ID`, `KICK_CLIENT_SECRET`, `KICK_REFRESH_TOKEN`.

### ⚠️ Token da Kick antes de subir
A Kick **rotaciona** o refresh token, e o válido fica no banco. Como o banco do
Discloud começa vazio, o `.env` precisa de um token **válido** na hora do upload.
Então, **antes de empacotar**:
1. **Desligue o bot** (feche o `start.bat`).
2. Rode: `python atualizar_token_kick.py` (copia o token válido do banco para o `.env`).
3. Aí sim gere o `.zip` e suba.

## Importante: não rode duas instâncias ao mesmo tempo
Com o **mesmo token** rodando no PC **e** no Discloud:
- o Discord responde **em dobro**;
- a **Kick** quebra (cada instância rotaciona o refresh token e **invalida o da outra**).

Então, ao migrar pro Discloud, **desligue o do PC** (feche o `start.bat`) e rode só lá.

## Kick mão-dupla (comandos no chat) — depois do deploy
Hoje o bot **posta** na Kick (mão-única). Para **ler comandos** (`!programacao`) do
chat, a Kick exige **webhook** (URL pública) + escopo `events:subscribe`. Isso a
gente configura **depois** que o bot estiver no Discloud (que fornece o endereço
público) — me avise quando estiver lá.
