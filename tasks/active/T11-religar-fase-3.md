# T11 — Religar a Fase 3 ao PostgreSQL

**ID:** T11
**Workflow:** BUILD
**Status:** NÃO INICIADA — é o próximo trabalho
**Depende de:** T10 (migração para PostgreSQL)
**Criada:** 2026-08-28

## Por que existe

`banco.py` e `consultas.py` (os do SQLite) deveriam ter sido apagados junto
com o resto na faxina de 28/08. **Não foram, e o motivo é concreto:**

```
src/transcrever.py:23   import banco
src/analisar.py:20      import banco
src/editar.py:25        import banco
src/editar.py:27        import consultas
```

Esses três são a Fase 3 — a parte do projeto que **já está pronta e testada**
(a transcrição está medida em 0,41x, e o editor já produziu vídeo de verdade).
Apagar o SQLite antes de portá-los quebraria os três.

## Objetivo

Trocar as chamadas a `banco.*` e `consultas.*` por `repos.*` nesses três
arquivos, e então apagar o SQLite de vez.

## Passos

- [ ] `transcrever.py` — `banco.salvar_transcricao` → `repos.transcripts.salvar`
      (a tabela nova já existe, com trechos e palavras)
- [ ] `transcrever.py` — enfileirar por `processing_jobs` (`job_type =
      'transcription'`) em vez de varrer pastas
- [ ] `analisar.py` — `banco.salvar_metricas` → `repos.analyses.salvar_do_conteudo`
      com `model='metricas.py'`
- [ ] `editar.py` — `consultas.melhores_posts` → `repos.consultas.melhores_posts`
- [ ] `editar.py` — `banco.registrar_edicao` → `repos.media.registrar` com
      `asset_type='edit'`
- [ ] `editar.py` — as palavras vêm de `repos.transcripts.palavras`
- [ ] `relatorio.py` — ler das novas consultas
- [ ] Rodar a esteira inteira: coletar → baixar → transcrever → analisar →
      relatório, com evidência real colada aqui
- [ ] **Só então:** apagar `src/banco.py`, `src/consultas.py` e
      `tests/test_banco.py` (54 conferências de código morto)

## Onde cada coisa mora no modelo novo

| Antes (SQLite) | Agora (PostgreSQL) |
|---|---|
| `transcricoes` | `transcripts` |
| `segmentos` | `transcript_segments` |
| `palavras` | `transcript_words` |
| `transcricoes_fts` (FTS5) | coluna `search_pt` (`tsvector` + GIN) |
| `metricas` | `content_analyses` com `model='metricas.py'` |
| `edicoes` | `media_assets` com `asset_type='edit'` |
| `downloads` | `processing_jobs` |

## O `post.json` é entrada, não cópia — descoberto em 01/09/2026

**`transcrever.py` e `analisar.py` não consultam o PostgreSQL.** Eles varrem
`dados/perfis/*/` procurando `perfil.json` e `post.json`, leem dali, e escrevem
em `dados/analises/*.json` + SQLite.

Medido em 01/09/2026:

```
disco:      16 post.json    15 mp4    0 transcricao.json
PostgreSQL: contents 16     media_assets 15
            transcripts 0   content_analyses 0
SQLite:     dados/analise.db NÃO EXISTE
```

Os 16 batem porque `coletar` grava banco e disco em linhas adjacentes, sem
desvio entre elas (`pipeline.py:824` e `:832`). O que não bate é a Fase 3: ela
nunca rodou na era PostgreSQL.

**Duas consequências que precisam entrar no trabalho:**

1. **O comentário em `pipeline.py:830` está errado e é perigoso.** Ele diz que
   o `post.json` "não é redundância: é o que permite conferir a coleta a olho,
   sem abrir o banco" — como se fosse conveniência. Ele é **carga**: sem ele a
   Fase 3 não tem entrada. Corrigir o comentário faz parte desta task.
2. **O `limpar` não protege o `post.json`.** Conferir isso antes de rodar
   qualquer faxina, ou a Fase 3 perde a entrada de posts já pagos.

Portar a Fase 3 resolve os dois de uma vez: a entrada passa a ser o banco, e o
`post.json` volta a ser o que o comentário diz que ele é.

## Cuidado que vale registrar

A busca full-text mudou de motor. O FTS5 casava substring; o `tsvector`
português faz **stemming**, e o comportamento não é o mesmo. Verificado no
banco em 28/08:

- `casas` e `casa` → ambos `cas` ✅ casam
- `falando` e `falar` → ambos `fal` ✅ casam
- `dando` → `dand`, mas `dar` → `dar` ❌ **não** casam

Quem depender da busca precisa saber disso; não é bug, é como o dicionário
português do PostgreSQL funciona.

## Depois desta

O editor (T8) volta a ser o assunto, que foi o combinado com o usuário.
