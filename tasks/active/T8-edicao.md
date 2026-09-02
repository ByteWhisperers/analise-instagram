# T8 — Seleção e edição de vídeo

**ID:** T8
**Workflow:** BUILD + DESIGN
**Status:** CONSTRUÍDA em 01/09/2026 — falta o portão humano (assistir)
**Depende de:** nada. O modo pasta **não passa pelo banco** — ver abaixo

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

## A decisão que reenquadrou a task — 01/09/2026

A T8 supunha que o editor comeria do banco: `selecionar.py` escolhe os top N,
`editar.py` lê a mídia e grava na tabela `edicoes`. **Isso foi abandonado**, e
por uma razão que não era visível quando a task foi escrita:

**O material é dele, não coletado.** Vídeo gravado por ele não tem
`content_id`. `media_assets` e `processing_jobs` são chaveadas por post do
Instagram — forçar um vínculo ali torceria o schema para caber um caso que não
é o dele. Então o modo pasta **não toca no PostgreSQL**, e o tempo por vídeo
(critério 4) sai em `saida/editados/relatorio.json`.

Consequência boa: a T8 **deixou de depender da T11**. A porta da Fase 3 para o
PostgreSQL continua pendente, e continua sendo problema da T11.

## Passos

- [x] `templates/padrao.json` com os tokens do visual — já existia
- [x] `src/legenda.py` — palavras → `.ass` com karaokê — já existia, agora
      **conferido**: 64 conferências, era o único módulo do editor sem teste
- [x] `src/editar.py` — montar a linha de filtros do ffmpeg — já existia;
      acrescentado o modo `--pasta` e o contorno opcional no `drawtext`
- [x] `src/fala.py` — vídeo → palavras com tempo, com cache em disco
- [x] `src/roteiro.py` — a lista de headlines, função pura
- [x] `templates/vertical.json` — para vídeo já gravado em pé
- [ ] ~~`src/selecionar.py` — top N do banco~~ — **fora de escopo**, ver acima
- [ ] ~~Registrar cada edição na tabela `edicoes`~~ — virou `relatorio.json`
- [x] Medir quanto tempo leva por vídeo nesta máquina — **medido, ver abaixo**
- [ ] **PORTÃO: assistir ao vídeo editado.** Não existe "ficou bom" por leitura
      de código — vale a mesma regra da T6. **Pendente: é ele quem assiste.**

## Critérios de aceitação

1. Um vídeo entra, sai em 9:16 com fundo, logo, headline e legenda sincronizada.
2. Trocar o template muda o visual **sem tocar no código**.
3. A legenda acompanha a fala — conferido assistindo, não lendo o `.ass`.
4. O tempo por vídeo fica registrado.

## Resultado — medido em 01/09/2026, não estimado

Três Reels reais de 57,9s cada, nesta máquina (i3-6006U, 3,9 GB):

| Etapa | Medida |
|---|---|
| Transcrição, modelo `small` | **0,9× a duração** — 49,8s para 57,9s de áudio |
| Edição sem legenda (`meme-branco`) | **50,9s por vídeo** |
| Edição com legenda (`vertical-cheio`) | **68,8s por vídeo** |
| Segunda rodada, transcrição do cache | zero segundos de Whisper |

Saída conferida com `ffprobe`: **1080×1920, 30 fps, trilha de áudio presente**
nos três. Quadro em t=2,2s mostra `veja` aceso em amarelo (`#FFE100`) sobre
contorno preto, exatamente na janela em que a palavra é dita (2,02–2,38s).

**Custo em dinheiro: US$ 0,00.** Whisper e ffmpeg rodam locais.

### O que a renderização revelou, e que nenhuma leitura de código pegaria

O `meme-branco` foi desenhado para vídeo **deitado ou quadrado**. Com fonte já
em 9:16 — que é o que sai de celular — o vídeo é reduzido a 540×960 dentro de
um canvas de 1080×1920: **metade do quadro vira branco**. Não é defeito do
template, é ele encontrando uma fonte para a qual não foi feito.

Daí o `templates/vertical.json`: o vídeo preenche a tela e o texto vai por
cima. Isso exigiu a **única** mudança de código no renderizador — `borderw`
opcional no `drawtext`, porque texto sobre imagem sem contorno some no primeiro
quadro claro. Padrão zero, então o `meme-branco` sai idêntico ao que sempre saiu.

### Critérios de aceitação

1. ✅ Entra vídeo, sai 9:16 com fundo, headline, @ e legenda sincronizada —
   conferido por `ffprobe` e por quadro extraído. Logo não foi exercitado
   (nenhum PNG de marca ainda), mas o filtro está coberto por teste.
2. ✅ Trocar o template muda o visual sem tocar no código — provado trocando
   `padrao` por `vertical` na linha de comando, com o mesmo binário.
3. ⏳ **Depende dele.** Eu conferi o `.ass` e o quadro; dizer se a legenda
   *acompanha a fala* ao longo do vídeo inteiro é assistir.
4. ✅ `saida/editados/relatorio.json`, por vídeo e em média.

## Fase 2 — 02/09/2026: enquadramento e edição dirigida por medição

Ele apontou dois problemas: o vídeo não estava enquadrado como queria e não
havia como ajustar, e a edição deveria ser dinâmica, usando o banco. Notou
também, lendo o repositório, que o ffmpeg é um decodificador e não só um
editor — e essa observação virou o eixo do trabalho.

**O enquadramento.** `src/enquadrar.py`, função pura: `encaixar` (o antigo, e
ainda o padrão), `preencher`, `desfoque`, mais `zoom`, `deslocar_x` e
`deslocar_y`. A conta é inteira em Python, não expressão de ffmpeg.

**A medição.** `pipeline.py medir` lê os mp4 com ffmpeg e preenche
`content_analyses`, que existia vazia. `src/formato.py` faz o parsing, também
função pura. Custo zero.

**O laço.** `medir --sugerir NOME` escreve um template a partir do medido, e
`cor.igualar` faz o editor medir **cada vídeo dele** e aplicar a diferença até
o alvo do nicho. As três cobaias receberam ajustes diferentes — é isso que
separa edição dinâmica de aplicar o mesmo filtro em tudo.

**O que a medição disse, e o que ela não disse.** Os 15 vídeos são 9:16 sem
tarja, cortam 17,6 vezes por minuto na mediana (de 12,6 a 24,3) e têm brilho
117,5. Mas o volume ficou dentro de 1,6 dB nos 4 perfis: isso é normalização
do Instagram, não escolha de quem edita, e por isso **não** virou alvo.

**Três defeitos achados renderizando, nenhum visível no código:** `zoom=0`
virando 1.0 calado; o modo `desfoque` cortando a frente; e o `write_text` do
Windows traduzindo `
` em `
`, o que dobrava o vão da headline de duas
linhas. Junto veio `text_align=C`, sem o qual as linhas curtas ficavam
encostadas à esquerda.

## O que ficou de fora, declarado

- **`editar --lote`** (o caminho do banco) continua quebrado contra o SQLite
  que não existe mais. Marcado no código, não consertado — é a T11.
- **`src/selecionar.py`** — só faz sentido para material coletado.
- **Logo** — o filtro existe e está testado, mas nunca rodou com PNG real.
- **A escolha entre os dois templates é manual.** O sistema não detecta se o
  vídeo já é 9:16 para sugerir o `vertical`.
