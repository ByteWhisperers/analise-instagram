# T8 — Seleção e edição de vídeo

**ID:** T8
**Workflow:** BUILD + DESIGN
**Status:** NÃO INICIADA — desenhada, não construída
**Depende de:** T7 (a seleção lê do banco), T4 (as palavras vêm da transcrição)

## Objetivo

Pegar os vídeos que mais engajaram e aplicar um molde visual: formato de Reels,
fundo, logo, headline e legenda queimada.

## Escopo

Dentro:
- `src/selecionar.py` — escolhe os top N do banco
- `src/legenda.py` — monta o `.ass` a partir da tabela `palavras`
- `src/editar.py` — aplica o template com ffmpeg
- `templates/padrao.json` — o visual, em arquivo

Fora: motion design, animação complexa, gráfico animado (seria Remotion — ver
ADR 004, e a decisão foi não instalar por especulação).

## Decisões

- **ffmpeg**, [ADR 004](../../docs/decisions/004-ffmpeg-em-vez-de-remotion.md).
  Já instalado e **verificado**: libass, libfreetype, libharfbuzz, fontconfig,
  drawtext, subtitles, overlay, scale, pad, gblur, concat, fade.
- **O editor é genérico quanto à origem do vídeo.** Aceita material gravado pelo
  usuário ou baixado na coleta. O código não distingue — a escolha é do usuário,
  vídeo a vídeo. Decisão dele, com o risco declarado abaixo.
- **Template em JSON, não em código.** Trocar cor, fonte, posição da headline ou
  logo é editar um arquivo.
- **Legenda palavra-por-palavra sai de graça:** o Whisper entrega
  `word_timestamps` e o `.ass` tem marcação de karaokê nativa. Sem dependência
  nova. É a razão de a tabela `palavras` existir.

## O que o editor faz

| Operação | Filtro | Verificado |
|---|---|---|
| Cortar para 9:16 | `scale` + `crop`/`pad` | sim |
| Fundo de cor sólida | `pad` | sim |
| Fundo desfocado do próprio vídeo | `gblur` | sim |
| Logo por cima | `overlay` | sim |
| Headline | `drawtext` | sim |
| Legenda queimada, palavra a palavra | `.ass` + libass | sim |

## Risco declarado

O editor aceita vídeo de terceiro porque **essa foi a decisão do usuário**,
tomada com o risco na mesa: republicar vídeo alheio com marca própria expõe a
denúncia, remoção e queda de conta.

O sistema não impede. O sistema também não finge que o risco não existe.

O caminho recomendado continua sendo o **molde**: usar a análise para descobrir
como os que funcionam são construídos, e aplicar essa forma em material próprio.

## Passos

- [ ] `templates/padrao.json` com os tokens do visual
- [ ] `src/legenda.py` — palavras → `.ass` com karaokê
- [ ] `src/editar.py` — montar a linha de filtros do ffmpeg
- [ ] `src/selecionar.py` — top N do banco
- [ ] Registrar cada edição na tabela `edicoes`
- [ ] **PORTÃO: assistir ao vídeo editado.** Não existe "ficou bom" por leitura
      de código — vale a mesma regra da T6.
- [ ] Medir quanto tempo leva por vídeo nesta máquina

## Critérios de aceitação

1. Um vídeo entra, sai em 9:16 com fundo, logo, headline e legenda sincronizada.
2. Trocar o template muda o visual **sem tocar no código**.
3. A legenda acompanha a fala — conferido assistindo, não lendo o `.ass`.
4. O tempo por vídeo fica registrado.

## Resultado

_(preencher ao concluir)_
