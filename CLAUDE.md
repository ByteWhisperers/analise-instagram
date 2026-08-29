# Análise Instagram

## Por que existe

Entender **como os posts que funcionam no Instagram são construídos**, de forma repetível.
Hoje isso é feito no olho: abrir um perfil, assistir, tentar perceber o padrão.

Aqui: você digita um termo ("apostas", "tigrinho"), o sistema acha os perfis,
baixa os posts, transcreve o que é falado, mede a estrutura e monta um relatório
comparativo que abre no navegador.

## O que faz

```
termo → perfis → posts + mídia → transcrição → métricas ─┬─► relatório HTML
                                                          └─► vídeos editados
```

Tudo vai para um banco SQLite (`dados/analise.db`), que é a espinha: perguntas
novas viram consulta, não código novo.

**A arquitetura completa está em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** —
ela manda sobre o plano original em `docs/PROJECT.md`, que ficou defasado quando
o escopo cresceu.

| Etapa | Comando | Entrega |
|---|---|---|
| Preparo | `preparar.py verificar` | o que falta na máquina, e o conserto |
| Esquema | `migrar.py aplicar` | as 20 tabelas do PostgreSQL |
| Descoberta | `pipeline.py descobrir "<nicho>"` | perfis em `profiles` |
| Coleta | `pipeline.py coletar --nicho X` | conteúdo + fila em `processing_jobs` |
| Download | `pipeline.py baixar` | `dados/perfis/<perfil>/<id>/midia.mp4` |
| Situação | `pipeline.py status` | cobertura, fila e custo por nível |
| Score | `pipeline.py ranking --nicho X` | quem performa acima do grupo |
| Conferência | `pipeline.py schema "<nicho>"` | item cru do Actor, por centavos |
| Faxina | `pipeline.py limpar` | o que dá para liberar. Só apaga com `--aplicar` |
| Transcrição | `src/transcrever.py` | `transcricao.json` por post |
| Análise | `src/analisar.py` | `dados/analises/<perfil>.json` |
| Relatório | `src/relatorio.py` | `saida/relatorio.html` |
| Edição | `src/editar.py` | `saida/editados/` |

Módulos de apoio, sem linha de comando própria:

| Arquivo | Responsabilidade |
|---|---|
| `src/config.py` | caminhos do projeto e leitura validada do `config.local.json` |
| `src/console.py` | faz stdout aguentar emoji. **Sem ele o `ranking` quebra** |
| `src/preparar.py` | as 7 checagens do ambiente. Verifica e instrui, não instala |
| `src/db.py` | conexão com o PostgreSQL e execução das migrations |
| `src/repos/` | **a única camada que escreve SQL** — dez módulos, um por agregado |
| `src/banco.py` | SQLite antigo. **Só sobrevive porque `transcrever.py`, `analisar.py` e `editar.py` ainda o importam.** Morre quando a Fase 3 for portada |
| `src/consultas.py` | idem — substituído por `repos/consultas.py` |
| `src/coletor.py` | `InstagramCollector` / `ApifyInstagramCollector` — só descobre |
| `src/downloader.py` | `VideoDownloader` / `YtDlpDownloader` — só baixa |
| `src/storage.py` | `Storage` / `LocalStorage` — só guarda |
| `src/midia.py` | achar o ffmpeg e extrair áudio |
| `src/metricas.py` | as contas da análise, só função pura |
| `src/desempenho.py` | engajamento, velocidade e score, só função pura |
| `src/legenda.py` | palavras com tempo → `.ass` com karaokê |
| `src/relatorio.css` | design system do relatório, em variáveis CSS |
| `tests/test_metricas.py` | 34 conferências das contas |
| `tests/test_banco.py` | 54 conferências do banco e das consultas |
| `tests/test_coleta.py` | 73 conferências da normalização, storage, download e faxina |
| `tests/test_desempenho.py` | 66 conferências dos scores e do crescimento |
| `tests/test_db.py` | 58 conferências da conexão, das migrations e do config |
| `tests/test_preparar.py` | 26 conferências do preparo e da saída de console |
| `tests/test_repos_*.py` | 263 conferências contra um PostgreSQL de verdade |

**574 conferências, todas passando** (contadas na saída real, não estimadas).
Rode as onze antes de dar qualquer coisa por pronta. As `test_repos_*` exigem
o PostgreSQL de pé; se ele não responder, elas avisam e saem sem falhar.

Apagados em 28/08/2026: `src/ig.py`, `src/buscar.py`, `src/coletar.py`,
`tests/test_pipeline.py`. A construir: `src/selecionar.py`.

**O banco é PostgreSQL 17**, em `127.0.0.1:5432/analise_instagram`. Os testes
usam um banco descartável (`..._teste`) criado e derrubado a cada rodada.
`pgvector` ainda não está instalado — no Windows exige compilar com MSVC, e
nenhum embedding é gerado nesta fase.

O `python` do sistema não serve — use sempre `.venv\Scripts\python.exe`.
**Nunca rode com `PYTHONIOENCODING` setado à mão:** foi assim que o bug do
emoji no `ranking` ficou escondido por dois dias. Quem cuida disso é
`console.preparar()`, dentro do próprio programa.

**O projeto é um repositório Git desde 29/08/2026.** Antes disso não havia
desfazer, e isso travava faxina de código.

## Restrições

- **Só leitura.** Nunca postar, curtir ou comentar.
- **Só perfil público.** Perfil privado não entra.
- **Nenhuma conta do Instagram é usada.** A descoberta é da Apify e o download é
  anônimo — verificado. Isto substitui a antiga regra da conta descartável.
- **A descoberta custa dinheiro.** US$ 2,70 por 1.000 resultados; o plano grátis
  dá US$ 5/mês. Três freios no código: estimativa com confirmação,
  `teto_usd_por_rodada` e `max_items`. Ver
  [ADR 005](docs/decisions/005-apify-em-vez-de-raspagem-propria.md).
- **A análise continua sem API paga.** O Python calcula os números; a leitura
  qualitativa é escrita por mim. Nenhum LLM entra na conta.
- **Nunca criar conta de Instagram.** Recusado, é padrão de conta falsa em massa.

## Máquina

i3-6006U, 3,9 GB de RAM, ~900 MB livres na prática.

**A transcrição é rápida — medido, não estimado.** O plano original chutava
3 a 5 minutos por minuto de vídeo. A medição real de 25/08/2026 deu **0,41x**
com o modelo `base`: 42,7s de áudio transcritos em 17,5s. Um Reels de 1 minuto
leva por volta de 25 segundos.

O gargalo não é a transcrição — é a **pausa deliberada** entre requisições ao
Instagram, que existe para a conta não ser bloqueada.

O modelo fica em configuração, nunca chumbado no código. Ver
[ADR 002](docs/decisions/002-modelo-de-transcricao.md).

## Onde mora

`C:\Users\55219\projetos\analise-instagram\` — **fora do `C:\xampp\htdocs\`**
de propósito. Isto é uma ferramenta, não um site publicado.

## Decisões registradas

- [001 — Instaloader em vez de ScrapeGraphAI](docs/decisions/001-instaloader-em-vez-de-scrapegraphai.md) — *aposentada pela 005 na parte da coleta*
- [002 — Modelo de transcrição: `small` por padrão, `base` como escape](docs/decisions/002-modelo-de-transcricao.md)
- [003 — SQLite como espinha](docs/decisions/003-sqlite-como-espinha.md)
- [004 — ffmpeg em vez de Remotion](docs/decisions/004-ffmpeg-em-vez-de-remotion.md)
- [005 — Apify descobre, yt-dlp baixa; a raspagem própria sai](docs/decisions/005-apify-em-vez-de-raspagem-propria.md)
- [006 — PostgreSQL nativo em vez de Docker](docs/decisions/006-postgres-nativo-em-vez-de-docker.md) — *vale enquanto a máquina for esta*

## Processo

Vale o **Operating Model V1** (`~/.claude/CLAUDE.md`).
A fila de trabalho está em `tasks/active/`. O plano completo em `docs/PROJECT.md`.

Nada é declarado pronto por leitura de código — só com evidência (V1 §10).
