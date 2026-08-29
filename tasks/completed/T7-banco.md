# T7 — Banco de dados

**ID:** T7
**Workflow:** BUILD
**Status:** NÚCLEO PRONTO E TESTADO — falta ligar as etapas existentes nele
**Depende de:** nada (é offline)
**Bloqueia:** T8 (a seleção lê do banco)

## Objetivo

Trocar os JSON soltos por um banco, para que "compare hashtag com visualização e
tema" seja uma pergunta ao banco, e não código novo a cada pergunta.

Pedido direto do usuário: *"eu quero uma lista armazenável em um banco de dados"*.

## Escopo

Dentro:
- `src/banco.py` — esquema e escrita. **Nenhum outro módulo escreve SQL.**
- `src/consultas.py` — as perguntas. Só leitura.
- Ligar `buscar.py`, `coletar.py`, `transcrever.py` e `analisar.py` ao banco.

Fora: trocar o relatório para ler do banco (fica para depois de T8).

## Decisões

- **SQLite**, [ADR 003](../../docs/decisions/003-sqlite-como-espinha.md).
  Já vem no Python. Verificado na máquina: 3.49.1 com FTS5 e JSON1.
- **Os JSON continuam sendo escritos.** O banco é adicional, não substituto —
  o JSON serve para conferir a olho o que foi coletado.
- **A mídia fica em disco.** O banco guarda o caminho, nunca o vídeo.
- **`hashtags` é tabela separada**, uma linha por par (post, tag). É isso que
  permite agrupar por tag numa consulta em vez de varrer texto de legenda.
- **`palavras` guarda cada palavra com seu segundo.** Nasce para a análise e
  vai alimentar a legenda palavra-por-palavra da T8.
- **`metricas` é separada de `posts`** porque é derivada: pode ser apagada e
  recalculada sem perder a coleta.

## Passos

- [x] `src/banco.py` — 9 tabelas, esquema idempotente
- [x] `src/consultas.py` — 11 perguntas
- [x] `tests/test_banco.py` — **45 conferências passando**
- [ ] `buscar.py` grava perfis e a busca no banco
- [ ] `coletar.py` grava posts, hashtags, menções e o caminho da mídia
- [ ] `transcrever.py` grava transcrição, trechos e palavras
- [ ] `transcrever.py` passa a pedir `word_timestamps=True`
- [ ] `analisar.py` grava métricas
- [ ] Rodar a esteira inteira e conferir o banco com dados reais

## Já verificado

```
.venv\Scripts\python.exe tests\test_banco.py
```

45 conferências, incluindo o que mais importa na prática:

- gravar duas vezes **não duplica** (a esteira é retomável)
- hashtag removida da legenda **sai** do banco
- refazer a transcrição **substitui**, não acumula
- apagar um perfil **leva os filhos junto** (cascade)
- FTS5 acha a palavra falada dentro das transcrições
- a consulta central (hashtag × engajamento × visualização) devolve o esperado
  e **descarta tag de post único**, que é ruído

## Critérios de aceitação

1. A esteira inteira roda e o banco fica coerente com os arquivos em disco.
2. `consultas.cobertura()` mostra onde a esteira parou.
3. Rodar tudo duas vezes não duplica nada.

## Resultado

_(preencher ao concluir)_
