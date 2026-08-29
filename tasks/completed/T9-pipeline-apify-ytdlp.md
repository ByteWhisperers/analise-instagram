# T9 — Pipeline: busca → registro → download

**ID:** T9
**Workflow:** BUILD, com um ciclo de INVESTIGATION pendente
**Status:** CONCLUÍDA em 28/08/2026 — esteira provada de ponta a ponta com dados reais
**Depende de:** [ADR 005](../../docs/decisions/005-apify-em-vez-de-raspagem-propria.md)
**Substitui:** T2 (busca) e T3 (coleta), que a ADR 005 aposentou
**Criada:** 2026-08-26

## Objetivo

O bloco que o usuário pediu, nesta ordem:

```
[busca de perfis] → [categorização e registro] → [baixar vídeos]
```

Sem conta do Instagram, sem cookie, sem risco de bloqueio na conta dele.

## Regra de arquitetura

```
DISCOVERY ≠ SCRAPING ≠ DOWNLOAD ≠ STORAGE ≠ PROCESSING
```

Cada módulo tem uma responsabilidade e não sabe do vizinho. `coletor.py` não
sabe baixar; `downloader.py` não sabe onde o arquivo mora; `storage.py` não sabe
o que é Instagram; `banco.py` continua sendo o único que escreve SQL.

## Passos

- [x] `apify-client`, `yt-dlp`, `curl-cffi` instalados; `browser_cookie3` fora
- [x] Banco na versão 2: tabelas `coletas` e `downloads`, 5 colunas em `perfis`
- [x] Migração por `ALTER TABLE` — banco antigo continua abrindo
- [x] `src/coletor.py` — interface + implementação Apify + normalizador
- [x] `src/downloader.py` — interface + implementação yt-dlp
- [x] `src/storage.py` — interface + disco local, no layout que a análise já lê
- [x] `src/pipeline.py` — `descobrir`, `coletar`, `baixar`, `status`, `schema`
- [x] Freios de custo: estimativa + `max_total_charge_usd` + `max_items`
- [x] 75 conferências novas (34 do pipeline, 41 da coleta); 153 no total
- [x] **Prova real:** yt-dlp baixou Reels público sem login — 1,95 MB em 8,1s
- [x] **GATE: token da Apify no `config.local.json`** — entregue pelo usuário
- [x] **INVESTIGATION: `pipeline.py schema "<nicho>"`** — feito em 28/08;
      três divergências achadas (`resultsLimit` mínimo 1, `externalUrls`
      plural e lista, posts aninhados em `latestPosts`)
- [x] Ajustar o normalizador ao schema real — três correções, mais o `-1`
      de curtidas ocultas achado só na rodada com dados reais
- [x] Rodada ponta a ponta — **maior que o combinado**: nicho `receitas`,
      8 perfis descobertos, 3 coletados, 15 reels, 15 baixados (293 MB,
      5min40, zero falhas). Custo: US$ 0,0459
- [x] Rodar duas vezes: a segunda respondeu **"Fila vazia. Nada a baixar."**
- [ ] Religar a Fase 3: `transcrever.py` → `analisar.py` → `relatorio.py`
      — **é a T11**, e agora tem 15 vídeos reais no disco para mastigar

## O que era `[NÃO VERIFICADO]` — e deixou de ser em 28/08

Duas rodadas reais (conferência do schema + esteira do MVP) trocaram a
documentação por fato. O que sobrou de aviso está no CHANGELOG; o que
importa aqui é que **o mapeamento não é mais hipótese**.

## Registro histórico do que estava `[NÃO VERIFICADO]`

O mapeamento de campos do Actor (`searchType`, `resultsType`, `shortCode`,
`followersCount`…) veio da **documentação**, não de uma rodada real.

Mitigação já no código: `_primeiro()` aceita vários nomes para o mesmo dado, e
`pipeline.py schema` despeja o item cru. **Nada disso vira fato antes de rodar.**

## Critérios de aceitação

1. Informar um nicho e receber perfis públicos no banco
2. Coletar os reels desses perfis, com metadado
3. Identificar o que é novo e ignorar o que já existe
4. Baixar pelo yt-dlp e guardar em `dados/perfis/<user>/<id>/midia.mp4`
5. Registrar todo o processo no banco
6. **Reexecutar sem duplicar download** — já coberto por teste
7. `pipeline.py status` mostrar custo por vídeo e taxa de falha

## Pendências que não são minhas (§14)

- **Conta na Apify** e o token. O plano grátis não pede cartão.
- **Decidir sobre os arquivos aposentados.** `src/ig.py`, `src/buscar.py` e
  `src/coletar.py` continuam no disco e fora do caminho. Não apaguei: não fui
  eu que os criei nesta sessão e **o projeto não está em Git** — não haveria
  como desfazer.

## Depois desta

O editor volta a ser o assunto (T8), por decisão do usuário.

## Fechamento (28/08/2026)

Os 7 critérios de aceitação foram exercidos contra o ambiente real, não
contra dublê. O que a rodada real ensinou e nenhum teste teria ensinado:

- a busca por termo depende do autocomplete do Facebook Ads — funciona em
  `receitas` (8 perfis grandes), falha em `apostas` (1 perfil, 12 seguidores);
- `-1` em curtidas significa "ocultas", e envenenava o score;
- post de colaboração cria perfil que ninguém descobriu.

Os dois últimos itens abertos viraram assunto de outra task ou de decisão do
usuário — ver CHANGELOG de 28/08 (2).
