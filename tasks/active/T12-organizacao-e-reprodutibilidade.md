# T12 — Organização: reprodutibilidade e arquivos sob controle

**ID:** T12
**Workflow:** BUILD, com um ciclo de INVESTIGATION no começo
**Status:** CONCLUÍDA em 29/08/2026
**Origem:** pedido do usuário — *"acho que preciso de um Docker, pra organizar
essa parte da aplicação, pra organizar melhor os arquivos e banco de dados"*
**Decide:** [ADR 006](../../docs/decisions/006-postgres-nativo-em-vez-de-docker.md)
**Criada:** 2026-08-29

## Objetivo

Atender os dois incômodos que o usuário marcou — **arquivos crescendo sem
controle** e **reprodutibilidade** — sem pagar o custo de RAM do Docker numa
máquina com 521 MB livres.

O Docker foi descartado por medição, não por preferência: 17 MB nativos contra
~1,2 GB. Ver ADR 006.

## Parte A — Reprodutibilidade

- [x] **A1.** `config.py`: removido o portão de `instagram.usuario` (campo que
      nenhum código lia desde a ADR 005) e `usuario_instagram()`. No lugar,
      `_exigir_postgres()` — a exigência que é real. **11 conferências.**
- [x] **A2.** `config.local.example.json` com a seção `postgres` e a seção
      `dados`; seção `instagram` removida.
- [x] **A3.** `src/preparar.py` — `verificar` e `criar-banco`. Substitui o
      `instalar-postgres.ps1` apagado, mas **verifica e instrui, não instala**
      (§14). 7 checagens, saída 0/1. **26 conferências.**
- [x] **A4.** `git init` + primeiro commit. 78 arquivos, 12.248 linhas.
      `git check-ignore` conferido antes, e não por confiança.
- [x] `.gitattributes` fixando LF, para o git do Windows não inventar diff.

## Parte B — Arquivos sob controle

- [x] **B1.** `repos/media.py` + 6 funções: `com_derivado_pronto`, `por_tipo`,
      `por_perfil`, `chaves_registradas`, `registros_da_chave`, `esquecer`.
      Nenhuma migration: `media_assets` já tinha tudo. **33 conferências.**
- [x] **B2.** `pipeline.py limpar` — seco por padrão, apaga só com `--aplicar`.
      Alvos: `--transcritos`, `--orfas`, `--antes-de N`.
- [x] **B3.** Reconciliação disco↔banco nos dois sentidos.
- [x] **B4.** `status` com quebra por tipo, por perfil, liberável e aviso de
      teto.
- [x] **B5.** `config.dados()` — retenção em configuração, tudo desligado.

## O bug que apareceu no meio, e que valia mais que a task

A simulação de clone limpo derrubou o `preparar.py` com `UnicodeEncodeError`.
Puxando o fio: **`pipeline.py ranking` quebrava com traceback em qualquer
legenda com emoji** — ou seja, quase toda legenda de Instagram.

O erro morria em `'\U0001f353'`, o morango de *"Morango Cravejado 🍓"* — o post
que estava em **primeiro lugar** no ranking. O comando quebrava exatamente no
melhor resultado.

Ficou escondido porque toda conferência da sessão em que o ranking nasceu rodou
com `PYTHONIOENCODING=utf-8` no ambiente. **A variável mascarava a falha.**

Conserto: `src/console.py`, chamado no início de cada `main()` dos sete
comandos. Relatório feio é melhor que relatório que não sai.

Lição para registrar: *variável de ambiente conveniente no terminal de quem
desenvolve é uma forma de não testar o que o usuário vai rodar.*

## O que os testes travam

- só sai do disco o que **já virou transcrição** — o mp4 é re-baixável, a
  transcrição não
- apagar o arquivo apaga o registro, **e não devolve o vídeo para a fila**
  (senão a limpeza vira moto-contínuo caro)
- a transcrição e o conteúdo **sobrevivem** ao apagar o vídeo
- `post.json` nunca entra na conta de mídia
- pasta que ficou vazia some junto; pasta com `post.json` fica
- apagar o que não existe devolve `False`, não estoura
- `carregar()` aceita config **sem** seção `instagram` e recusa **sem**
  `postgres`
- a senha nunca aparece em mensagem de erro de config

## Verificação (V1 §10)

1. **574 conferências, zero falhas** — 11 arquivos de teste. Eram 488 na
   abertura da sessão.
2. **Clone limpo simulado**, em pasta temporária, sem `config.local.json`:
   `preparar.py verificar` listou exatamente o que faltava e **não pediu conta
   do Instagram**. Depois, com o exemplo copiado, apontou a senha do Postgres
   como único bloqueio restante.
3. **`limpar` seco contra os 15 vídeos reais**: reportou 0 liberáveis (nada
   transcrito ainda) e nenhum descompasso. **Os 15 arquivos continuam no
   disco** — conferido por `find` antes e depois da suíte inteira.
4. `ranking` rodado **sem** `PYTHONIOENCODING`, com emoji na tela e sem
   traceback.
5. `git check-ignore` provando que `config.local.json`, `.venv/`, `dados/*` e
   `.sessoes/` ficaram fora do commit.

## Uma previsão minha que estava errada

O plano dizia que `limpar --orfas` acharia `dados/perfis/premiere/` como
descompasso. **Não achou, e está certo:** `premiere` foi baixado pelo pipeline
e está devidamente registrado em `media_assets`. A anomalia dele é de
**perfil** (criado sem nicho e sem aprovação), não de **arquivo**. Continua em
aberto, como decisão do usuário.

## Aberto, e que é decisão do usuário (§14)

1. **`config.local.json` ainda guarda `instagram.usuario` e uma senha de 85
   caracteres** que nada lê. Recomendo apagar a seção. Não mexo: o arquivo é
   dele.
2. **`raw_data` nunca é gravado** — os repositories aceitam `guardar_bruto`, o
   `pipeline.py` não passa. Ligar duplica payload no banco e no `post.json`.
3. **Perfil-fantasma por post de colaboração** (`pipeline.py:219`).

## Depois desta

A T11 — religar a Fase 3 ao PostgreSQL. Tem 15 vídeos reais no disco esperando,
e agora tem `git` para desfazer se der errado.
