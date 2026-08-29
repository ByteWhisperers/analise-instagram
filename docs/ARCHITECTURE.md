# Arquitetura

Revisada em 25/08/2026, depois que o escopo cresceu: entrou banco de dados e
entrou edição de vídeo. Este documento manda; onde o `docs/PROJECT.md` (o plano
original) divergir, vale o que está aqui.

---

## O que o sistema é, em uma frase

Uma esteira que transforma **um termo de busca** em **vídeos editados**, passando
por análise no meio — e que guarda tudo num banco para que perguntas novas não
exijam código novo.

---

## O fluxo inteiro

```
                    termo ("apostas")
                          │
                    ┌─────▼─────┐
                    │  BUSCAR   │  perfis com o termo no nome
                    │           │  + autores dos posts em alta da #
                    └─────┬─────┘
                          │  perfis
                    ┌─────▼─────┐
                    │  COLETAR  │  últimos N posts de cada perfil
                    └─────┬─────┘
                          │  posts, hashtags, arquivos de mídia
                    ┌─────▼─────┐
                    │TRANSCREVER│  áudio → texto com tempo por palavra
                    └─────┬─────┘
                          │  transcrições, palavras
                    ┌─────▼─────┐
                    │ ANALISAR  │  gancho, ritmo, CTA, engajamento
                    └─────┬─────┘
                          │  métricas
              ┌───────────┴───────────┐
              │                       │
        ┌─────▼─────┐           ┌─────▼──────┐
        │ RELATÓRIO │           │ SELECIONAR │  top N por engajamento
        │   HTML    │           └─────┬──────┘
        └───────────┘           ┌─────▼─────┐
         você lê e decide       │  EDITAR   │  ffmpeg + template
                                └─────┬─────┘
                                      │
                                saida/editados/
```

Duas saídas, não uma. O **relatório** é para você entender. O **editor** é para
você produzir. A análise alimenta os dois.

---

## O banco é a espinha

**Antes:** cada etapa cuspia um JSON solto numa pasta. Para perguntar "qual
hashtag aparece nos vídeos que mais engajam", era preciso escrever código que
abrisse todos os arquivos e cruzasse na mão.

**Agora:** cada etapa grava numa tabela. A mesma pergunta vira uma consulta.

**SQLite**, escolhido em [ADR 003](decisions/003-sqlite-como-espinha.md).
Já vem dentro do Python — não instala nada. Um arquivo só, `dados/analise.db`,
que dá para copiar, mandar por e-mail ou abrir em qualquer visualizador.

### As tabelas

| Tabela | Guarda | Por que separada |
|---|---|---|
| `perfis` | usuário, seguidores, bio, quando foi lido | o engajamento depende dos seguidores **do dia da coleta** |
| `posts` | tipo, duração, legenda, curtidas, comentários, views, data | o centro de tudo |
| `hashtags` | uma linha por par (post, tag) | é o que permite agrupar por tag sem varrer texto |
| `transcricoes` | o texto falado inteiro | + índice FTS5, para buscar palavra dentro de todas |
| `palavras` | cada palavra com início e fim | alimenta a legenda que acende palavra por palavra |
| `metricas` | gancho, ritmo, CTA, engajamento calculado | separado de `posts` porque é derivado, e pode ser recalculado |
| `edicoes` | qual vídeo, qual template, onde saiu | histórico do que já foi produzido |
| `buscas` | termo, quando, critérios | para saber de onde cada perfil veio |

**Os arquivos de mídia continuam em disco**, em `dados/perfis/`. O banco guarda o
caminho, não o vídeo. Banco com vídeo dentro fica intratável.

### O que o banco destrava

Perguntas que hoje exigiriam código e passam a ser consulta:

- qual hashtag aparece nos 10 vídeos de maior engajamento
- qual faixa de horário rende mais, por perfil e no geral
- quais vídeos falam a palavra "bônus" nos primeiros 3 segundos
- qual formato (Reels, carrossel, foto) engaja mais em cada perfil
- que perfis usam as mesmas hashtags — quem copia quem

---

## A etapa de edição

Decidido em [ADR 004](decisions/004-ffmpeg-em-vez-de-remotion.md): **ffmpeg**,
que já está instalado e verificado. Remotion fica como caminho B, só se aparecer
algo que o ffmpeg não dê conta.

### O editor é genérico de propósito

Ele aceita **qualquer vídeo de entrada** — gravado por você ou baixado na coleta.
O código não sabe nem se importa com a origem. Quem decide o que entra é você,
vídeo a vídeo.

O caminho principal é o **molde**: a análise mostra como os que funcionam são
construídos (onde entra o gancho, quanto dura, onde cai o CTA, que estilo de
legenda), e o editor aplica essa forma no seu próprio material.

### O que o editor faz

| Operação | Filtro do ffmpeg | Verificado |
|---|---|---|
| Cortar para 9:16 (Reels) | `scale` + `crop`/`pad` | sim |
| Fundo de cor sólida | `pad` com cor | sim |
| Fundo desfocado do próprio vídeo | `gblur` / `boxblur` | sim |
| Logo por cima | `overlay` | sim |
| Headline com fonte de verdade | `drawtext` + libfreetype | sim |
| Legenda queimada, palavra por palavra | `.ass` + libass | sim |
| Cortar trecho, juntar, fade | `trim`, `concat`, `fade` | sim |

A legenda palavra-por-palavra — aquela em que cada palavra acende quando é dita —
sai de graça: o Whisper entrega `word_timestamps`, e o formato `.ass` tem marcação
de karaokê nativa. É por isso que a tabela `palavras` existe.

### Template em arquivo, não em código

```
templates/
├── padrao.json
└── <seu-estilo>.json
```

Cor de fundo, fonte, tamanho, posição da headline, arquivo da logo, estilo da
legenda. **Trocar o visual é editar um arquivo, não mexer no código.**

---

## Os módulos

| Arquivo | Responsabilidade | Estado |
|---|---|---|
| `src/config.py` | caminhos e configuração | pronto |
| `src/banco.py` | esquema e acesso ao SQLite | **a construir (T7)** |
| `src/ig.py` | conexão com o Instagram | pronto |
| `src/buscar.py` | termo → perfis | pronto, grava JSON — migrar para o banco |
| `src/coletar.py` | perfil → posts + mídia | pronto, grava JSON — migrar para o banco |
| `src/midia.py` | achar ffmpeg, extrair áudio | pronto |
| `src/transcrever.py` | vídeo → texto | pronto — falta `word_timestamps` |
| `src/metricas.py` | as contas, funções puras | pronto, 33 testes |
| `src/analisar.py` | agregação por perfil | pronto |
| `src/relatorio.py` + `.css` | HTML final | pronto, portão visual em aberto |
| `src/selecionar.py` | escolher os top N para editar | **a construir (T8)** |
| `src/editar.py` | aplicar template com ffmpeg | **a construir (T8)** |
| `src/legenda.py` | montar o `.ass` a partir das palavras | **a construir (T8)** |

---

## Limites conhecidos, declarados

**Visualizações podem não vir.** O Instagram vem removendo a contagem pública de
views das respostas que o raspador enxerga. Se `video_view_count` voltar vazio, a
comparação "hashtag × visualização" cai para **curtidas e comentários por
seguidor** — que sempre existem. É a primeira coisa a testar com a conta de pé.

**"Tema" é por palavra, não por sentido.** Classificar tema de forma semântica
exigiria um modelo de linguagem, e o projeto tem custo zero de API como restrição.
O que dá para fazer sem pagar: agrupar por palavras que se repetem na transcrição
e na legenda, e nomear os grupos na leitura. É mais pobre do que classificação
semântica, e isso está dito na cara.

**A coleta depende de API interna do Instagram.** Se mudarem, quebra. Nesse dia
é DEBUG, não BUILD.

**Conteúdo de terceiro tem dono.** O editor aceita vídeo baixado porque essa foi a
decisão do usuário, ciente de que republicar vídeo alheio com marca própria é
risco de denúncia, remoção e queda de conta. O sistema não impede; o sistema
também não esconde que o risco existe.

---

## O que continua fora

- Postar, curtir ou comentar no Instagram — o projeto é só leitura
- Perfis privados
- Criar contas de Instagram — recusado, é o padrão de conta falsa em massa
- Monitoramento contínuo agendado
