# T10 — Migração para PostgreSQL: modelo, migrations e repositories

**ID:** T10
**Workflow:** BUILD
**Status:** CONCLUÍDA em 28/08/2026 — falta só a Fase 3 (ver T11)
**Depende de:** T9 (pipeline Apify + yt-dlp)
**Criada:** 2026-08-28
**Origem:** arquitetura de dados enviada pelo usuário; motor escolhido por ele

## Objetivo

Trocar o SQLite pelo PostgreSQL implementando a arquitetura de 12 entidades
que o usuário desenhou, pelo caminho **mais lento e mais seguro**: primeiro
os repositories com testes, e só no fim religar o `pipeline.py`.

Consequência aceita: **o sistema fica sem rodar no meio do caminho.** Foi
avisado antes de começar.

## Decisão de motor

O usuário escolheu PostgreSQL + pgvector contra a minha recomendação, que era
SQLite agora com o modelo já em formato Postgres. O argumento que eu levantei
e que ele decidiu assumir: **428 MB de RAM livres** numa máquina de 3,9 GB,
com o `faster-whisper` querendo ~290 MB.

Decisão registrada. Não se reabre sem fato novo.

## Passos

- [x] `migrations/001_intelligence.sql` — 17 tabelas, transacional
- [x] `src/db.py` — conexão, criação do banco e runner de migrations
- [x] `src/migrar.py` — `aplicar` / `status` / `resumo`
- [x] PostgreSQL 17 instalado e o esquema aplicado **de verdade** (saída real)
- [x] `tests/_pg.py` — banco de teste descartável, criado e derrubado por rodada
- [x] `repos/niches.py` + `repos/profiles.py` — 52 conferências
- [x] `repos/contents.py` + `repos/metrics.py` — 41 conferências
- [x] `repos/jobs.py` + `repos/media.py` + `repos/costs.py` — 64 conferências
- [x] `repos/transcripts.py` e `repos/analyses.py`
- [x] Migration 002 (transcrição) e 003 (view `v_content_current`)
- [x] As 11 perguntas portadas em `repos/consultas.py` — 73 conferências
- [x] `pipeline.py` religado; **não escreve mais SQL**
- [x] Apagados `ig.py`, `buscar.py`, `coletar.py`, `test_pipeline.py`
- [x] **Esteira ponta a ponta contra o Postgres, com download real:**
      `Chunk8-jurw`, 1,9 MB, gravado em `media_assets`; rodar de novo
      respondeu "Fila vazia"
- [x] **Rodada real na Apify** (run `y7QKvQUMo73pGrPFD`, US$ 0,00) — três
      divergências de schema corrigidas, ver CHANGELOG
- [ ] `repos/comments.py` — camada de enriquecimento, última fase
- [ ] Apagar `banco.py` e `consultas.py`: **bloqueado pela T11**, porque
      `transcrever.py`, `analisar.py` e `editar.py` ainda os importam

## Três desvios do spec, todos decididos pelo usuário

1. **`niche_profiles`** em vez de `profiles.niche_id` — um perfil serve a
   vários nichos ao mesmo tempo.
2. **`embeddings.embedding` é `REAL[]`**, não `vector(N)`. pgvector no Windows
   exige MSVC, e nesta fase nenhum embedding é gerado. A troca depois é um
   `ALTER ... USING embedding::vector`.
3. **`content_hashtags` e `content_mentions`** acrescentadas — pelo princípio
   do próprio spec de não depender de JSONB para consulta importante.

## O que os testes travam, e que vale mais que o número

- recoletar **não** apaga bio, avatar nem link que não vieram na rodada
- recoletar **não** desfaz aprovação nem relevância (classificação é separada)
- `None` **nunca** vira `False`: "não sabemos" e "não é" são coisas diferentes
- hashtag removida da legenda **sai** do banco; campo ausente **não** apaga
- job concluído **não** volta para a fila ao reprocessar
- desligar o PC no meio **não** perde o item (`destravar_orfaos`)
- a tentativa é contada **na reserva**, antes de tentar
- `shares` e `saves` ficam `NULL`, nunca `0`
- sem vídeo baixado, custo por vídeo é `None`, não zero

## Percalços resolvidos, para não se repetirem

- **UAC:** o instalador do PostgreSQL exige administrador e a sessão do
  assistente não é. Só o usuário podia conceder.
- **BOM:** `Set-Content -Encoding utf8` do PowerShell 5.1 grava BOM e o
  `json.load` recusa. `config.py` passou a ler com `utf-8-sig`.
- **Senha na URL:** a senha gerada tem `/`, `[` e `:`, que são delimitadores
  de URI. A correção não foi enfraquecer a senha — foi conectar por
  parâmetros separados. Virou teste permanente.

## Pontos de parada (§14)

- Nada de dependência nova prevista até os embeddings.
- pgvector, quando for a hora, exige Visual Studio Build Tools (vários GB).

## Estado

488 conferências passando. O pipeline roda sobre PostgreSQL. O SQLite só
sobrevive por causa dos três módulos da Fase 3 — ver T11.
