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

## Importante: não rode dois ao mesmo tempo
Se o bot estiver rodando no PC **e** no Discloud com o **mesmo token**, ele responde
**em dobro**. Quando migrar pro Discloud, **desligue o do PC** (feche o `start.bat`).
