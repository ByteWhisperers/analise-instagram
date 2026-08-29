# ADR 004 — ffmpeg para a edição, Remotion como caminho B

**Data:** 2026-08-25
**Status:** Aceita, com reavaliação condicional

## Contexto

O escopo cresceu: além de analisar, o projeto passa a **editar vídeo** — corte
para 9:16, fundo de cor ou desfocado, logo do perfil, headline e legenda.

O usuário levantou o **Remotion** como candidato.

## Decisão

**ffmpeg agora. Remotion só se aparecer algo que o ffmpeg não dê conta.**

## O que foi verificado na máquina

O ffmpeg 9.0 já instalado tem tudo que a edição descrita precisa:

```
libass  libfreetype  libharfbuzz  libfribidi  fontconfig  libx264  libwebp
drawtext  subtitles  ass  overlay  scale  pad  boxblur  gblur  colorkey
concat  fade
```

| O que o usuário pediu | Como o ffmpeg faz |
|---|---|
| Legenda | `.ass` queimado com libass |
| Headline | `drawtext` com fonte real |
| Fundo de cor X | `pad` com cor |
| Logo do perfil | `overlay` |
| Formato de Reels | `scale` + `crop`/`pad` |

## Por que não o Remotion

Não é defeito da ferramenta — é incompatibilidade com esta máquina.

O Remotion renderiza **quadro a quadro através de um Chromium invisível**. Um
vídeo de 30 segundos a 30fps são 900 quadros passando por um navegador, num
**i3-6006U de dois núcleos com cerca de 900 MB de RAM livre**. Some o projeto
Node e mais de 1 GB de `node_modules`.

E o que foi pedido — legenda, headline, fundo, logo — é **sobreposição estática**.
É o território natural do ffmpeg, que resolve em segundos por vídeo. O Remotion
ganharia em animação complexa e motion design, que não está no pedido.

Instalá-lo agora seria complexidade especulativa (V1 §12).

## Um ganho que veio de graça

O faster-whisper aceita **`word_timestamps`** — tempo por palavra, não só por
frase. O formato `.ass` tem marcação de karaokê nativa. Juntando os dois, sai a
**legenda estilo Reels**, em que cada palavra acende quando é falada, **sem
nenhuma dependência nova**.

É a razão de a tabela `palavras` existir no banco (ADR 003).

## Consequências

- `transcrever.py` precisa passar a pedir `word_timestamps=True`.
- Três módulos novos: `selecionar.py`, `editar.py`, `legenda.py`.
- O visual fica em **template JSON**, não no código: trocar cor, fonte, posição
  da headline ou logo é editar arquivo de configuração.
- O editor é **genérico quanto à origem do vídeo** — aceita material gravado pelo
  usuário ou baixado na coleta. O código não distingue; a escolha é do usuário,
  vídeo a vídeo.

## Reavaliação condicional

Se aparecer necessidade de animação que o ffmpeg não faça bem — gráfico animado,
transição com movimento, elemento que se desloca com física — a decisão volta à
mesa. Antes de instalar, **medir** quanto tempo o Remotion leva para renderizar
30 segundos nesta máquina. Se passar de poucos minutos por vídeo, não entra.

## Alternativas descartadas

- **Remotion agora** — custo de instalação e de renderização alto demais para o
  que foi pedido, nesta máquina.
- **MoviePy** — camada Python sobre o ffmpeg; carrega quadros na memória e é
  lenta. Numa máquina com 900 MB livres, é o pior dos dois mundos.
- **Editor manual (CapCut, Premiere)** — resolve o vídeo, mas não automatiza:
  o projeto existe para aplicar o mesmo molde em lote.
