# Arquitetura

> Reescrito em 31/08/2026. A versão anterior descrevia **SQLite com tabelas em
> português** (`perfis`, `posts`, `hashtags`) e módulos que foram apagados em
> 28/08 (`src/ig.py`, `src/buscar.py`, `src/coletar.py`). Nada daquilo existe.
> O `CLAUDE.md` aponta este arquivo como autoridade, então ele estava mentindo
> com confiança — que é o pior modo de errar.

## O que o sistema é, em uma frase

Um instrumento para descobrir **como uma comunidade do Instagram fala e o que
ela publica**, a partir de um termo em português comum.

## O fluxo inteiro

```
termo em português
   │
   ├─ 0. MAPEAR      tema → tribos, vocabulário, banda medida   (seco)
   │                 term_observations · dossiê JSON
   │
   ├─ 1. DESCOBRIR   nicho → perfis                             (paga)
   │                 profiles · niche_profiles
   │
   ├─ 2. COLETAR     perfis → posts + métricas                  (paga)
   │                 contents · content_metric_snapshots · processing_jobs
   │
   ├─ 3. BAIXAR      posts → mp4 em disco                       (grátis)
   │                 media_assets  (o arquivo NÃO entra no banco)
   │
   ├─ 4. TRANSCREVER mp4 → texto com tempo por palavra          (CPU)
   │                 transcripts · transcript_segments · transcript_words
   │
   └─ 5. ANALISAR    tudo → score, relatório
                     content_analyses · saida/
```

**As etapas 0 a 3 estão no PostgreSQL. As etapas 4 e 5 ainda falam com o SQLite
antigo** — é a dívida da T11, e é a única razão de `src/banco.py` e
`src/consultas.py` continuarem existindo.

### A esteira paralela: edição de material próprio

O editor tem um segundo caminho, que **não passa por banco nenhum** — nem
PostgreSQL, nem SQLite:

```
dados/gravacoes/*.mp4  +  roteiro.txt
   │
   ├─ fala.py      mp4 → palavras com tempo    (Whisper local, CPU)
   │               cache em <video>.palavras.json — retomável
   │
   ├─ roteiro.py   arquivo → {video: headline}  (função pura)
   │
   └─ editar.py    template + palavras → mp4 em 9:16
                   saida/editados/ · relatorio.json
```

**Por que fora do banco.** `media_assets` e `processing_jobs` são chaveadas por
`content_id` — um post do Instagram. Vídeo gravado pelo usuário não tem um, e
inventar vínculo torceria o schema para caber um caso que não é o dele. O
registro de tempo por vídeo, que a T8 exige, mora em `relatorio.json`.

O caminho `editar --lote`, que lê do banco, **continua quebrado** contra o
SQLite que sumiu. Marcado no código; conserta a T11.

---

## As quatro camadas, e a regra de cada uma

A regra que organiza o projeto inteiro é **separar decisão de orquestração de
acesso**. Não é estética: é o que permite testar 607 conferências sem rede,
sem banco e sem gastar um centavo.

| Camada | Quem mora ali | A regra |
|---|---|---|
| **Orquestração** | `pipeline.py` | decide a ordem, imprime, gasta dinheiro. **Nenhuma conta e nenhum SQL.** |
| **Decisão** | `mapeador`, `grafo`, `assinatura`, `lexico`, `idioma`, `metricas`, `desempenho`, `legenda`, `roteiro` | **só função pura.** Entra dado, sai dado. Sem rede, sem banco, sem relógio (o `agora` é sempre parâmetro) |
| **Acesso a dados** | `repos/` — onze módulos, um por agregado | **a única camada que escreve SQL.** Também é a fronteira de idioma: o Python fala português, o banco fala inglês |
| **Acesso ao mundo** | `coletor`, `downloader`, `storage`, `midia`, `db`, `fala` | tudo que fala com fora. Interface abstrata + implementação, para o teste poder usar dublê |

Duas fronteiras que valem a pena entender:

**`lexico` não conhece o schema do Actor.** Ele recebe texto, hashtags e menções
já extraídos e devolve termos. Quem sabe onde os campos moram dentro do item cru
é o `coletor`. É a mesma divisão que existe entre `idioma.detectar()`, que lê
texto, e quem vai buscar o texto.

**O commit fica com quem chamou**, nunca com o repositório. Gravar perfil,
vínculo e snapshot é uma operação só do ponto de vista de quem coleta, e três
commits separados deixariam o banco meio pronto se o processo morresse no meio.

---

## O banco

**PostgreSQL 17**, em `127.0.0.1:5432/analise_instagram`. Nativo, não Docker —
[ADR 006](decisions/006-postgres-nativo-em-vez-de-docker.md), e vale enquanto a
máquina for esta (3,9 GB de RAM).

Migrado do SQLite em 28/08 ([ADR 003](decisions/003-sqlite-como-espinha.md)
descreve a escolha original, hoje superada). **22 tabelas**, seis migrations.

### As famílias

**Quem é quem** — o cadastro

| Tabela | Guarda |
|---|---|
| `niches` | o nicho, seus `criteria` medidos e as `keywords` aprovadas |
| `profiles` | usuário, seguidores, bio, privacidade, `is_approved` |
| `niche_profiles` | a ligação N:N entre os dois |
| `profile_snapshots` | seguidores **na data da leitura** — é o que permite medir crescimento |

**O que foi publicado** — o conteúdo

| Tabela | Guarda |
|---|---|
| `contents` | o post: tipo, duração, legenda, link, `is_pinned`, `raw_data` |
| `content_hashtags`, `content_mentions` | uma linha por par, para agrupar sem varrer texto |
| `content_metric_snapshots` | **a tabela mais importante.** Curtidas/views *na hora da leitura*, com `hours_since_published` congelado junto |
| `media_assets` | o caminho do arquivo em disco. **O vídeo nunca entra no banco** |
| `comments` | camada cara: 1 comentário = 1 resultado cobrado. Só por regra de seleção |

**O que se aprendeu sobre a linguagem** — a T16

| Tabela | Guarda |
|---|---|
| `term_observations` | **append-only.** Uma linha por (termo, post), com `occurrences`, idioma, perfil e a rodada |
| `niche_terms` | o vocabulário **julgado**: `is_approved`, uma linha por termo, sobrescrita |

**O que custou e o que falta fazer** — a contabilidade

| Tabela | Guarda |
|---|---|
| `collection_jobs` | toda chamada externa: tipo, ator, run_id, quando abriu e fechou |
| `data_costs` | o dólar de cada operação, estimado ou real |
| `processing_jobs` | a fila local: baixar, transcrever, analisar |

**O que ainda não tem linha nenhuma** — construído e esperando a T11:
`transcripts`, `transcript_segments`, `transcript_words`, `content_analyses`,
`comment_analyses`, `embeddings`.

### O mapa de dependências

```
niches ──┬─ niche_profiles ─┬─ profiles ─┬─ profile_snapshots
         │                  │            └─ contents ─┬─ content_hashtags
         ├─ niche_terms     │                         ├─ content_mentions
         └─ term_observations                         ├─ content_metric_snapshots
                   │                                  ├─ media_assets
                   └──── collection_jobs ── data_costs├─ comments
                                                      ├─ transcripts ─┬─ segments
                                                      │               └─ words
                                                      └─ content_analyses
```

### As três decisões de esquema que importam

**1. Nunca depender do valor corrente.** Velocidade e aceleração são *diferença
entre duas leituras*. Por isso `content_metric_snapshots` e `profile_snapshots`
existem, e por isso `hours_since_published` é **gravado** e não recalculado:
recalcular amanhã com o mesmo número de views daria outra resposta.

**2. Medição e julgamento são tabelas diferentes.** `term_observations` é o que
foi *visto*; `niche_terms.is_approved` é o que foi *aceito*. Misturar as duas
faria remapear apagar decisão do usuário.

**3. `term_observations` não tem UNIQUE, e a ausência é a decisão.** Chave única
forçaria UPDATE e mataria o passado — que é justamente o que a tabela existe
para guardar. O que separa uma rodada da outra é `job_id`. `apagar_rodada()`
existe para descartar uma rodada envenenada: *append-only* não é imutável para
sempre.

### O que o banco destrava

Perguntas que viram consulta em vez de código novo:

- qual hashtag aparece nos 10 vídeos de maior engajamento
- que perfis usam o mesmo vocabulário — quem anda com quem
- **o vocabulário deste nicho mudou entre agosto e outubro** (só depois da 006)
- **este termo é raro fora desta tribo** (idem)
- quanto já se gastou, por operação e por nível

---

## As contas

Todas em função pura, todas testadas sem rede.

### Desempenho — `src/desempenho.py`

**Engajamento** prefere views e cai para seguidores quando o Instagram não
devolve a contagem pública:

```
taxa = (curtidas + comentários) / visualizações      ← se houver views
     = (curtidas + comentários) / seguidores         ← senão
```

O segundo valor devolvido diz **qual base foi usada**, porque comparar uma taxa
sobre views com uma sobre seguidores é comparar coisas diferentes.

**Velocidade** é interação por hora, com piso de 1 hora — sem o piso, um post de
dez minutos teria velocidade infinita.

**Recência** decai por meia-vida:

```
recência = 0.5 ^ (horas / 48)
```

**Score de oportunidade**, 0 a 100: cada sinal vira **percentil dentro do
grupo**, e os percentis são combinados por peso.

| sinal | peso |
|---|---|
| velocidade | 0,30 |
| engajamento | 0,25 |
| comentário | 0,20 |
| visualização | 0,15 |
| recência | 0,10 |

Duas propriedades deliberadas: **o score só existe dentro do grupo escolhido** —
trocar o grupo troca o número, e isso é a definição e não um defeito. E **os
pesos são renormalizados sobre o que existe**: se `visualizações` não veio, o
score não é punido em 15%, ele se redistribui. Dado ausente não pode virar nota
baixa.

### Linguagem — `src/grafo.py` e `src/assinatura.py` (T16)

**Similaridade entre dois perfis**, Jaccard ponderado por raridade:

```
              Σ idf(t) para t em A∩B
sim(A, B) =  ─────────────────────────        idf(t) = log(N / perfis_com_t)
              Σ idf(t) para t em A∪B
```

O `idf` é o que impede o **território** de dissolver as tribos: `#moto`, em 60
de 68 perfis, vale 0,12; `#grauderua`, em 6, vale 2,42.

**O grafo é podado por k-vizinhos mais próximos (k=3)**, união e não
interseção. Limiar absoluto e percentil foram tentados e falharam — os números
estão no topo de `grafo.py`.

**Comunidades** por propagação de rótulos determinística: ordem alfabética,
empate pelo menor rótulo. Determinismo é requisito, não gosto — agrupamento que
muda entre duas rodadas iguais não serve de evidência.

**Generalidade** — o eixo território↔tribo, entropia de Shannon normalizada
pelo **total** de tribos:

```
generalidade(t) = H(distribuição de t entre as tribos) / log(total_de_tribos)

    0.0 = marcador de pertencimento   (`mandrake`, `torque`)
    1.0 = território                  (`moto`, `tragédias`)
```

**Exclusividade** — o que separa tribo de território, com suavização add-k
(Jeffreys, k = 0,5):

```
                     (dentro + k) / (N_tribo + 2k)
exclusividade  =  ─────────────────────────────────
                     (fora + k) / (N_fora + 2k)
```

Sem a suavização a divisão estoura, e em amostra pequena denominador zero é o
caso comum — no limite o termo *mais raro* iria ao topo dos marcadores, o
oposto do que se quer.

**Classificar um perfil** devolve distribuição, nunca rótulo:

```
pontos(tribo)  = Σ log P(termo | tribo) / nº de termos     ← média geométrica
pontos(outros) = Σ log P(termo | fundo) / nº de termos
distribuição   = softmax(pontos)
```

Duas decisões aqui: **`outros` é um competidor de verdade**, com o corpus de
fundo por distribuição — perfil que só fala genérico faz o fundo ganhar. E a
divisão pelo número de termos evita que sessenta termos virem `{tribo: 1.0}`,
que seria afirmar certeza que a amostra não sustenta.

**Escolher a próxima chamada** — `mapeador.ganho_do_termo`:

```
ganho = exclusividade_máxima × log(1 + perfis)
```

Dois terços da rodada aprofundam nos marcadores; um terço explora a fronteira
entre tribos. Os pesos são a primeira aposta, não uma medição — está escrito no
docstring.

### Conteúdo — `src/metricas.py`

Contagem de palavras, palavras por minuto, emojis, primeira linha da legenda,
detecção de CTA, gancho falado nos primeiros 3 segundos, blocos no tempo.

---

## Onde as coisas ficam em disco

```
dados/
├── perfis/<perfil>/<post_id>/midia.mp4    ← o vídeo; o banco só guarda o caminho
├── mapeamentos/<tema>.json                ← o dossiê, para você marcar entra=true
├── analises/<perfil>.json                 ← agregação da fase antiga
└── analise.db                             ← SQLite, só para as fases 4 e 5
saida/
├── relatorio.html
└── editados/
```

**Arquivo grande nunca entra no banco.** Banco com vídeo dentro fica intratável
de copiar, de fazer backup e de consultar.

---

## Limites conhecidos, declarados

**A Fase 3 ainda fala SQLite.** `transcrever.py`, `analisar.py` e o caminho
`editar --lote` importam `banco.py`. Enquanto isso não for portado (T11), o
projeto tem dois bancos e 16 vídeos reais esperando. Cuidado registrado: a
busca mudou de FTS5 para `tsvector` com stemming português. **A edição de
material próprio não espera por isso** — ela não passa por banco.

**O template `meme-branco` supõe vídeo deitado ou quadrado.** Com fonte já em
9:16, ele reduz o vídeo a 540×960 num canvas de 1080×1920 e metade do quadro
vira branco — medido em 01/09/2026. Para vídeo de celular existe o
`vertical.json`. **A escolha é manual:** o sistema não olha a proporção da
entrada para sugerir o template certo.

**Visualizações podem não vir.** O Instagram vem removendo a contagem pública. O
código já cai para curtidas e comentários por seguidor, e diz qual base usou.

**A estatística é mais magra onde se fala menos.** Medido em 31/08: `tragédias`
rendeu 23.660 observações e `grau de moto`, 3.394 — legenda de nicho de moto é
quase só hashtag. O sistema aguenta os dois, mas a assinatura é mais frágil no
segundo.

**A lista de palavras vazias do `lexico.py` é pequena demais.** `também`, `dia`,
`vida`, `tudo`, `durante`, `coisa` ainda aparecem no núcleo semântico. O `idf`
reduz o estrago no agrupamento, mas elas sujam a leitura.

**Nenhum LLM, nenhum embedding.** `pgvector` não está instalado — no Windows
exige compilar com MSVC. A tabela `embeddings` existe com `REAL[]`, vazia. A
leitura qualitativa continua sendo escrita por gente.

**A descoberta custa dinheiro.** US$ 2,70 por 1.000 resultados. Três freios:
estimativa, `teto_usd_por_rodada` e `max_items`.
[ADR 005](decisions/005-apify-em-vez-de-raspagem-propria.md).

---

## O que continua fora

- Postar, curtir ou comentar — o projeto é só leitura
- Perfis privados
- Criar conta de Instagram — recusado, é padrão de conta falsa em massa
- Monitoramento contínuo agendado
