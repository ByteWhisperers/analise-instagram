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
| **Mapeamento** | `pipeline.py mapear "<tema>"` | vocabulário, perfis-semente e a banda medida. Seco: só grava com `--aplicar` |
| Esquema | `migrar.py aplicar` | as 22 tabelas do PostgreSQL |
| Descoberta | `pipeline.py descobrir "<nicho>"` | perfis em `profiles`, filtrados pela banda |
| Coleta | `pipeline.py coletar --nicho X` | conteúdo + fila em `processing_jobs` |
| Download | `pipeline.py baixar` | `dados/perfis/<perfil>/<id>/midia.mp4` |
| Situação | `pipeline.py status` | cobertura, fila e custo por nível |
| Score | `pipeline.py ranking --nicho X` | quem performa acima do grupo |
| Conferência | `pipeline.py schema "<nicho>"` | item cru do Actor, por centavos |
| Faxina | `pipeline.py limpar` | o que dá para liberar. Só apaga com `--aplicar` |
| Transcrição | `src/transcrever.py` | `transcricao.json` por post |
| Análise | `src/analisar.py` | `dados/analises/<perfil>.json` |
| Relatório | `src/relatorio.py` | `saida/relatorio.html` |
| **Edição em massa** | `src/editar.py --pasta` | `dados/gravacoes/*.mp4` + `roteiro.txt` → `saida/editados/`. **Não passa por banco** |

Módulos de apoio, sem linha de comando própria:

| Arquivo | Responsabilidade |
|---|---|
| `src/config.py` | caminhos do projeto e leitura validada do `config.local.json` |
| `src/mapeador.py` | ranquear, saturar, medir, agrupar tribos e montar o dossiê. Só função pura |
| `src/lexico.py` | a legenda paga vira observação tipada: hashtag, palavra, bigrama, emoji, menção |
| `src/grafo.py` | Jaccard, comunidades determinísticas e o eixo **território↔tribo**. Só função pura |
| `src/assinatura.py` | `P(t\|tribo)/P(t\|fora)`, assinatura da tribo e classificação como distribuição |
| `src/idioma.py` | separa português de espanhol por heurística. Sem dependência nova |
| `src/console.py` | faz stdout aguentar emoji. **Sem ele o `ranking` quebra** |
| `src/preparar.py` | as 7 checagens do ambiente. Verifica e instrui, não instala |
| `src/db.py` | conexão com o PostgreSQL e execução das migrations |
| `src/repos/` | **a única camada que escreve SQL** — onze módulos, um por agregado |
| `src/banco.py` | SQLite antigo. **Só sobrevive por `transcrever.py`, `analisar.py` e o caminho `editar --lote`** — que está quebrado, porque `dados/analise.db` não existe mais. Morre com a T11 |
| `src/consultas.py` | idem — substituído por `repos/consultas.py` |
| `src/coletor.py` | `InstagramCollector` / `ApifyInstagramCollector` — só descobre |
| `src/downloader.py` | `VideoDownloader` / `YtDlpDownloader` — só baixa |
| `src/storage.py` | `Storage` / `LocalStorage` — só guarda |
| `src/midia.py` | achar o ffmpeg e extrair áudio |
| `src/metricas.py` | as contas da análise, só função pura |
| `src/desempenho.py` | engajamento, velocidade e score, só função pura |
| `src/legenda.py` | palavras com tempo → `.ass` com karaokê. Só função pura |
| `src/fala.py` | vídeo → palavras com tempo (Whisper local), com cache em `<video>.palavras.json` |
| `src/roteiro.py` | a lista de headlines do lote: `nome.mp4 \| texto`. Só função pura |
| `templates/padrao.json` | `meme-branco` — para vídeo **deitado ou quadrado** |
| `templates/vertical.json` | `vertical-cheio` — para vídeo **já gravado em pé** (celular) |
| `src/relatorio.css` | design system do relatório, em variáveis CSS |
| `tests/test_idioma.py` | 26 conferências do detector de idioma |
| `tests/test_lexico.py` | 41 conferências do colhedor de léxico |
| `tests/test_grafo.py` | 64 conferências do grafo e do eixo território↔tribo |
| `tests/test_assinatura.py` | 43 conferências da exclusividade e da classificação |
| `tests/test_mapeador.py` | 114 conferências do mapeamento e das tribos, sem rede |
| `tests/test_metricas.py` | 34 conferências das contas |
| `tests/test_banco.py` | 54 conferências do banco e das consultas |
| `tests/test_coleta.py` | 139 conferências da normalização, storage, download, faxina e critérios |
| `tests/test_desempenho.py` | 66 conferências dos scores e do crescimento |
| `tests/test_db.py` | 108 conferências da conexão, das migrations e do config |
| `tests/test_preparar.py` | 26 conferências do preparo e da saída de console |
| `tests/test_legenda.py` | 64 conferências do `.ass`: cor AABBGGRR, tempo, escape e karaokê |
| `tests/test_editar.py` | 83 conferências da corrente de filtros, da varredura e do relatório |
| `tests/test_roteiro.py` | 49 conferências do pareamento vídeo↔headline |
| `tests/test_fala.py` | 40 conferências do cache de transcrição, com dublê no Whisper |
| `tests/test_repos_*.py` | 312 conferências contra um PostgreSQL de verdade |

**1.263 conferências, todas passando** (contadas na saída real, não
estimadas). Rode as vinte antes de dar qualquer coisa por pronta. As
`test_repos_*` exigem o PostgreSQL de pé; se ele não responder, elas avisam e
saem sem falhar.

Apagados em 28/08/2026: `src/ig.py`, `src/buscar.py`, `src/coletar.py`,
`tests/test_pipeline.py`. `src/selecionar.py` **saiu do plano** em 01/09: a
edição passou a comer de uma pasta dele, não do banco (ver T8).

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
- **O acento do tema decide a comunidade.** `#tragedias` é espanhola;
  `#tragédias` é portuguesa — são duas comunidades diferentes, e a diferença é
  um acento no que você digita. Medido em 30/08/2026.
- **O termo não identifica uma comunidade — identifica o território onde
  várias vivem.** `#tragédias` são pelo menos três tribos: literatura
  (`sêneca`, `aristófanes`), desastre real (`acidenteaéreo`, `br242`) e drama
  pessoal (`amor`, `autopiedade`). Por isso o mapeamento agrupa **perfis** e
  dá a cada termo uma nota **por tribo**, em vez de uma lista de aprovados.
  Ver [ADR 007](docs/decisions/007-assinatura-tribal-em-vez-de-lista-de-tags.md).
- **A legenda já foi paga.** Ela chega dentro do item que custou dinheiro, e
  dela sai gíria, emoji, abreviação, bigrama e menção — sem uma chamada nova.
  O que o mapeamento observa fica em `term_observations`, **append-only**:
  é o corpus de fundo da exclusividade e a série temporal do vocabulário.
- **Antes de buscar, mapeia.** Um tema em português comum não é uma hashtag:
  `#desastresetragedias` devolveu 1 item e zero termos, enquanto `#desastres`
  devolveu 64. O `mapear` descobre o vocabulário, mede a banda do nicho e
  espera sua aprovação — nada entra sozinho. Ver a T14.
- **Os critérios de coleta são configuração, nunca constante.** Quem escolhe
  a banda de seguidores, a janela de dias, o eixo de busca e o que fazer com
  post fixado é o `config.local.json`, com flag espelho na linha de comando.
  A precedência é `flag > config > padrão`. Ver a T13.
- **O post fixado escapa do filtro de data do Actor** — medido, não suposto.
  Ele entra marcado (`contents.is_pinned`) para não se passar por recente.
- **A análise continua sem API paga.** O Python calcula os números; a leitura
  qualitativa é escrita por mim. Nenhum LLM entra na conta.
- **Nunca criar conta de Instagram.** Recusado, é padrão de conta falsa em massa.
- **A edição em massa é de material próprio, e não passa por banco.** Vídeo
  gravado por ele não tem `content_id` — forçar vínculo em `media_assets`
  torceria o schema. O tempo por vídeo mora em `saida/editados/relatorio.json`.
  `dados/gravacoes/` é ignorada pelo git: o repositório é público.
- **O template certo depende da proporção do vídeo, e a escolha é sua.** O
  `meme-branco` foi feito para vídeo deitado ou quadrado; com fonte já em 9:16
  ele encolhe o vídeo à metade do quadro. Para celular, use o `vertical`.

## Máquina

i3-6006U, 3,9 GB de RAM, ~900 MB livres na prática.

**A transcrição é rápida — medido, não estimado.** O plano original chutava
3 a 5 minutos por minuto de vídeo. A medição real de 25/08/2026 deu **0,41x**
com o modelo `base`: 42,7s de áudio transcritos em 17,5s. Um Reels de 1 minuto
leva por volta de 25 segundos. Com `small`, medido em 01/09/2026: **0,9x** —
49,8s para 57,9s de áudio, com qualidade visivelmente melhor em português.

**A edição custa mais que a transcrição.** Medido em 01/09/2026, num Reel de
57,9s: **51s sem legenda, 69s com legenda queimada**. Como as palavras ficam
em cache, refazer o lote só para trocar o template paga só o ffmpeg.

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
- [007 — Assinatura tribal em vez de lista de tags](docs/decisions/007-assinatura-tribal-em-vez-de-lista-de-tags.md)

## Processo

Vale o **Operating Model V1** (`~/.claude/CLAUDE.md`).
A fila de trabalho está em `tasks/active/`. O plano completo em `docs/PROJECT.md`.

Nada é declarado pronto por leitura de código — só com evidência (V1 §10).
