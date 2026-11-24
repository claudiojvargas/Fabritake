# Fabritake

Estúdio local para organizar cenas de vídeo em sequência, salvar clipes MP4 e reaproveitar o frame final anterior como referência. Cada cena continua disponível individualmente para edição manual.

O **simulador** executa o fluxo completo com três clipes sintéticos identificados, sem Google, rede ou créditos. O **Google Flow** está em diagnóstico com perfil persistente e autenticação manual. O adaptador registra a disponibilidade observável, mas a submissão, a seleção de modelo e a coleta real de mídia ainda dependem de validação autorizada.

## Requisitos

- Python 3.12 ou posterior.
- Node.js 22.12 ou posterior e npm para desenvolver ou compilar o painel.
- Chromium do Playwright e uma sessão gráfica para abrir o Google Flow.
- FFmpeg e FFprobe são opcionais para simulação. O backend verifica o hash das fixtures e, quando as duas ferramentas estão instaladas, também decodifica os arquivos. Mídia externa requer as ferramentas. No Windows, instale com `winget install --id Gyan.FFmpeg -e` e abra outro terminal. No Ubuntu/Debian, use `sudo apt install ffmpeg`. Confira com `ffmpeg -version` e `ffprobe -version`.

### Windows (PowerShell)

Na raiz do repositório:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "backend[test]"
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para o diagnóstico do Flow, instale o Chromium em outro terminal com `.\.venv\Scripts\python.exe -m playwright install chromium`.

### Linux

Na raiz do repositório:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
npm ci --prefix frontend
npm run build --prefix frontend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para o diagnóstico do Flow, instale o Chromium com `.venv/bin/python -m playwright install chromium`. Se faltar uma biblioteca do sistema, use `.venv/bin/python -m playwright install-deps chromium` em uma distribuição suportada. O navegador abre na sessão gráfica da máquina onde o backend roda.

Abra `http://127.0.0.1:8000` após compilar o frontend. Em desenvolvimento, deixe o backend rodando em 8000 e execute `npm run dev --prefix frontend` em outro terminal. O painel de desenvolvimento fica em `http://127.0.0.1:5173` e encaminha `/api` para o backend. O FastAPI expõe a documentação da API em `/docs`. Execute um processo do servidor por diretório de armazenamento. O Alembic aplica as migrations na inicialização.

### Armazenamento e configuração

O padrão é `storage/` na raiz. Copie `.env.example` para `.env` se precisar configurar outra pasta, origens explícitas de desenvolvimento, executáveis do FFmpeg ou Chromium. Caminhos relativos de armazenamento são resolvidos a partir da raiz do projeto. Mantenha o servidor vinculado ao loopback. Esta aplicação foi projetada para acesso local do usuário da máquina.

```text
storage/
  database/fabritake.sqlite3
  browser_profiles/<id>/
  projects/001-monolito-modular/
    projeto.json
    roteiro.md
    prompts.md
    referencias/
    videos/
    frames/
    tentativas/<cena>/<tentativa>/
    logs/eventos.jsonl
    edicao/
```

SQLite é a fonte de verdade. As tentativas mantêm a mídia original. `videos/` e `frames/` contêm seleções numeradas, e `edicao/` é reservada ao usuário. Faça cópias com o backend parado. Perfis do navegador podem conter sessões sensíveis e devem ficar fora de compartilhamentos e do Git. O endpoint de arquivos limita os downloads aos artefatos registrados e metadados do projeto.

## Simular um projeto

1. Na visão geral, clique em **Experimentar simulação** para criar uma cópia do [Monolito Modular](examples/monolito-modular.json).
2. Clique em **Iniciar geração**. A instância simulada copia as mídias de teste e registra a dependência entre as cenas. A primeira cena não precisa de um frame anterior.
3. Abra uma cena para reproduzir o clipe, conferir o frame final e consultar suas tentativas. A aba **Arquivos** dá acesso aos arquivos individuais e à pasta local.
4. Para experimentar revisão, ative **Exigir aprovação manual** antes de iniciar. Aprove o frame e retome o projeto para avançar. Rejeições e falhas exigem nova tentativa explícita.
5. Ao regenerar uma cena, a seleção anterior é preservada em `tentativas/`. As cenas que dependiam dela ficam desatualizadas. Em cada dependente, regenere ou confirme a versão existente. O restante da fila aguarda essa decisão.

As fixtures têm dois segundos e servem para validar formato, reprodução, organização e encadeamento. A resolução, o conteúdo e a duração da fixture são fixos. As configurações do projeto descrevem a intenção para um provedor real.

## Diagnóstico do Google Flow

1. Em **Instâncias**, cadastre uma instância Google Flow e clique em **Abrir navegador**.
2. Na janela criada, autentique-se manualmente e confira disponibilidade, permissões, modelo e eventuais restrições da sua conta. Use **Verificar** para atualizar o estado observável. O diagnóstico detecta a localização da página e possíveis redirecionamentos à página da conta. Autenticação e créditos ficam desconhecidos quando a interface não permite leitura confirmada.
3. Feche a janela pelo painel ao terminar. O perfil é reutilizado em reaberturas. Cada instância tem seu próprio diretório e bloqueio de sessão.
4. Para habilitar geração em uma tarefa futura, valide o fluxo autorizado descrito no [contrato do provedor](docs/provedor.md). Obtenha autorização específica para qualquer consumo pago antes desse teste. Os testes padrão usam somente simulação.

## Verificação

```bash
npm run build --prefix frontend
.venv/bin/python -m pytest backend/tests -q
FABRITAKE_TEST_CHROMIUM=1 .venv/bin/python -m pytest backend/tests/test_browser.py -q
```

No PowerShell, use `.\.venv\Scripts\python.exe` e defina `$env:FABRITAKE_TEST_CHROMIUM = "1"` antes do teste de interface. Se quiser usar um Chromium do sistema, configure `FABRITAKE_CHROMIUM_PATH` com o caminho do executável. O teste no Chromium usa o build, um servidor temporário e o simulador.

Veja o [formato de importação](docs/importacao.md), o [contrato do provedor](docs/provedor.md) e as [decisões de implementação e recuperação](docs/arquitetura.md).
