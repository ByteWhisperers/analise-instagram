> **CANCELADA em 26/08/2026 pela [ADR 005](../../docs/decisions/005-apify-em-vez-de-raspagem-propria.md).**
> A raspagem própria saiu do projeto; descoberta e coleta passaram para a
> Apify. O código desta task (`ig.py`, `buscar.py`, `coletar.py`) foi apagado
> em 28/08. O trabalho equivalente está na [T9](T9-pipeline-apify-ytdlp.md).

# T3 — Coleta

**ID:** T3
**Workflow:** BUILD
**Status:** CÓDIGO PRONTO — bloqueada pela T2
**Depende de:** T2
**Bloqueia:** T4

## Objetivo

Para cada perfil escolhido, baixar os últimos N posts: o arquivo de mídia mais
um `post.json` com todos os números.

## Escopo

Dentro: `src/coletar.py`.
Fora: transcrever (T4), calcular métricas (T5).

## Decisões de construção

- **Retomável.** Antes de baixar, confere se já existe `post.json` **e** algum
  arquivo `midia*`. Se existe, pula. Rodar duas vezes não baixa nada de novo —
  e se o Instagram cortar no meio, é só rodar outra vez.
- **Duas pausas diferentes.** Entre posts (8s) e entre perfis (60s). Trocar de
  perfil é o movimento que mais chama atenção de um sistema antifraude.
- **Carrossel é tratado à parte.** Cada imagem do carrossel vira `midia-01`,
  `midia-02`… Sem isso, só a primeira seria baixada.
- **Perfil privado é pulado**, mesmo que apareça na lista.
- Grava `perfil.json` junto — o engajamento depende do nº de seguidores **no dia
  da coleta**, não do de hoje.

## Passos

- [x] `src/coletar.py`
- [x] Verificação de sintaxe
- [ ] Rodar em 3 posts de 1 perfil (depende da T2)
- [ ] **Abrir o vídeo baixado e comparar o `post.json` com a tela do Instagram**

## Critérios de aceitação

1. `dados/perfis/<perfil>/<id>/` com mídia que abre e `post.json` preenchido.
2. Rodar de novo não baixa nada repetido.
3. Curtidas, comentários, data e duração **batem com o que está no Instagram** —
   conferido a olho, não no JSON.

## Verificação

```
.venv\Scripts\python.exe src\coletar.py --perfil <um_perfil> --posts 3
```

**Evidência exigida:** a saída real + a comparação de 1 post contra a tela (V1 §10).

## Resultado

_(preencher ao concluir)_
