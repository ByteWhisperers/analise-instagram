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
