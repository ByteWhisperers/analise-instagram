# Changelog

Formato: o que mudou no sistema, do mais recente para o mais antigo.

## [Não lançado]

### 2026-08-31 — a tribo aparece pelo sub-grafo, e não pela palavra

O mapeamento devolvia uma **lista plana de hashtags**. Essa forma não consegue
expressar o que se quer saber, e os dois dossiês de 30/08 provam:

- em `tragédiaseresgates`, três tribos dividem uma palavra e ficam no mesmo
  nível do ranking — literatura (`sêneca`, `aristófanes`, `teatro`), desastre
  real (`acidenteaéreo`, `br242`, `aviões`) e drama pessoal (`amor`,
  `autopiedade`);
- em `desastresetragedias`, `esquilo · grecia · greekliterature ·
  literaturagriega · littératuregrecque` é tragédia grega coerente em quatro
  idiomas, e foi lido como ruído. (`esquilo` em espanhol é **Ésquilo**.)

O diagnóstico, nas palavras do usuário: *"`moto` não identifica uma comunidade.
É apenas o território onde várias comunidades vivem."*

#### A economia que viabilizou tudo

**A legenda já estava paga e estava sendo jogada fora.** O `mapear` recebia os
itens crus, lia a legenda uma vez para votar idioma, colhia só o campo
`hashtags` e descartava o resto. Gíria, emoji, abreviação, bigrama e menção
estavam ali. Colher isso custou **zero chamadas novas**.

#### O que mudou

- **`src/lexico.py`** — item cru vira observação tipada em cinco *kinds*.
  Emoji agrupado à mão (ZWJ, bandeira e tom de pele contam como um), sem
  dependência nova. Número é palavra: `244` é o nome de uma tribo.
- **`migrations/006` + `repos/observacoes.py`** — `term_observations`,
  append-only. É o corpus de fundo da exclusividade e a série temporal do
  vocabulário. **A ausência de UNIQUE é a decisão**, não um esquecimento.
- **`src/grafo.py`** — Jaccard, propagação de rótulos determinística e o eixo
  território↔tribo por entropia normalizada.
- **`src/assinatura.py`** — `P(termo|tribo) / P(termo|fora)`, com suavização
  add-k, e classificação como distribuição com `outros` competindo.
- **`mapeador.proximos_alvos()`** — a rodada deixa de perguntar "quais as tags
  mais fortes?" e passa a perguntar "qual observação mais reduz a incerteza
  sobre a identidade dos clusters?".

#### Três armadilhas de contagem dupla, fechadas com teste

`@fulano_mt` virava as palavras `fulano` e `mt` (sublinhado não é letra para o
regex); a muralha de trinta hashtags no fim da legenda afogava a prosa; e o
campo do Actor somava com o regex. Agora o campo manda e o regex é plano B.

#### Um erro corrigido durante a construção

`generalidade()` normalizava pelo número de tribos **em que o termo aparece**.
Um termo em 2 de 3 tribos dava 0,9183 contra 1,0 de um em 3 de 3 — quase
empate. E o marcador puro caía em `None` e sumia do eixo, sendo o caso que mais
interessa. Normalizado pelo universo: marcador é 0,0, território é 1,0.

#### Medido, no cenário das três tribos de moto

| termo | generalidade | leitura |
|---|---|---|
| `moto` | 1,0000 | território puro |
| `grau` | 0,9206 | espalhado, puxando para uma |
| `role` | 0,5794 | em duas de três |
| `mandrake`, `torque`, `familia` | 0,0000 | marcador |

E a mesma palavra com nota diferente por tribo: `torque` vale >5 na oficina e
<1 na quebrada.

#### Verificação

**1.013 conferências, zero falhas**, em 16 arquivos (eram 820). Os dois
critérios de aceitação passam e podem falhar de verdade. **Falta a prova em
dado real pago** — nada disso rodou contra chamada nova.

Ver [ADR 007](docs/decisions/007-assinatura-tribal-em-vez-de-lista-de-tags.md)
e a [T16](tasks/active/T16-assinatura-tribal.md).

### 2026-08-30 (3) — o mapeamento aprende a ver idioma, e o acento vira decisão

A descrição honesta do processo de mapeamento, feita depois de três rodadas
reais, expôs cinco defeitos. Quatro foram corrigidos.

#### O defeito central

A primeira porta que abria decidia tudo: `#desastres` rendeu vocabulário, então
`#tragedias` **nunca foi tentada**. E `#desastres` é tag hispanófona — o
mapeamento inteiro foi parar em defesa civil peruana, e o avanço guloso
aprofundou nesse cluster por três rodadas pagas.

#### O que mudou

- **Todas as sementes** são tentadas, não só a primeira que render
- **`src/idioma.py`** — separa português de espanhol por heurística explícita,
  sem instalar nada (§14). Três estados: `pt`, `es` e **`None` para "não sei"**
- O filtro age **na exploração** (tag espanhola não vira alvo da rodada
  seguinte, e é aí que ele economiza), **no dossiê** e no banco
- **Ritmo de postagem**, que estava vazio por desperdício: `_montar()` já
  desaninhava os posts datados, e o `mapear` os jogava fora
- **Amostra por relevância** — quem aparece em mais tags fortes, e não quem
  chegou primeiro

#### Medido, antes e depois, no mesmo tema com o mesmo teto

| | antes | depois |
|---|---|---|
| sementes tentadas | 2 | 3 |
| ritmo | `None` | 0,7 dias |
| mediana de seguidores | 1.435 | 2.293 |

#### O achado: o acento decide a comunidade

`tag_do_termo()` preserva acento desde a T13, e a consequência só apareceu
agora:

| tema | semente | idioma | banda medida |
|---|---|---|---|
| "desastres e tragedias" | `#tragedias` | es | 811–5.647 |
| "tragédias e resgates" | `#tragédias` | **pt** | 1.484–205.812 |

Com acento vieram `#notícias`, `#acidenteaéreo` e
`#atlasdigitaldedesastresnobrasil`. **`#tragedias` e `#tragédias` são duas
comunidades diferentes, em dois idiomas** — e a diferença, no que se digita, é
um acento.

#### O filtro duro tem um custo, e ele ficou visível

Com o tema sem acento, o filtro descartou `#desastres` (21 perfis) e
`#tragedias` (20 perfis) — as duas mais fortes — e o topo virou ruído
(`#esquilo`, `#greekliterature`). O detector não errou: aquelas legendas são
espanholas. **O tema, escrito assim, vive em espanhol.** As 40 descartadas
ficam no dossiê com idioma e votos, e voltam movendo a linha.

#### Dois defeitos que os testes pegaram no detector

- Um dígrafo sozinho decidia: `"llama"` virava espanhol. Limiar subiu para 3.
- `que`, `mas` e `como` estavam na lista espanhola, e são portuguesas
  comuníssimas.

#### Verificação

**820 conferências, zero falhas**, em 13 arquivos (eram 762). Custo das duas
rodadas de campo: US$ 0,054.


### 2026-08-30 (2) — o mapeamento: a fase que faltava antes da busca

O sistema tinha um regime só: você já sabia o termo, pedia, recebia. Isso
assume que o vocabulário do assunto é conhecido — e funcionou com "receitas"
por acidente, porque o termo é a palavra que as pessoas usam.

Com *"perfis que falam de desastres e tragédias"* quebra na primeira linha:
**o input que o comando exige é justamente o output que ainda não se tem.**

#### A prova, e ela é curta

```
#desastresetragedias    1 item,   0 termos
#desastres             20 itens, 64 termos
```

O tema escrito em português não é uma hashtag. A cascata de sementes
(concatenação, depois cada palavra significativa, parando na primeira que
render) nasceu dessa falha real — não de previsão.

#### E o que o mapeamento mostrou sobre o tema

O vocabulário voltou **em espanhol**: `#emergencias`, `#bomberos`,
`#prevención`, `#gestióndelriesgo`, `#perú`, `#inscripcionesabiertas`. É um
cluster de defesa civil e cursos de formação hispano-americano — não notícia de
tragédia brasileira. Ninguém teria adivinhado, e ficou sabido por US$ 0,03 em
vez de por uma coleta inteira desperdiçada.

#### O que passou a existir

- `pipeline.py mapear "<tema>"` — **seco por padrão**, como o `limpar`: escreve
  um dossiê em `dados/mapeamentos/` e não toca no banco. `--aplicar` grava o
  que você marcou
- `src/mapeador.py` — ranquear, saturar, medir, montar dossiê. Só função pura
- Migration 005: `niche_terms` (o vocabulário **com a evidência**),
  `niches.criteria`, e os dois `CHECK` abertos para `niche_mapping`
- `coletor.tags_dos_itens()` — co-ocorrência de hashtag, de graça: o campo já
  vem dentro do item pago
- `coletor.relacionados_de()` — liga `perfis_relacionados()`, que estava
  **escrito, testado e órfão** desde que nasceu
- Precedência final: **flag > nicho (banco) > global (config) > padrão**

#### A decisão de ranqueamento, e o número que a sustenta

As hashtags reais de @receitasdepai trouxeram `publi`, `MercadoLivre`,
`PagBank` e `AeC440` — propaganda, não receita. Tag de patrocínio aparece
**muito**, mas num perfil só; tag do nicho aparece em vários. Por isso o
ranking é por **perfis distintos** e não por frequência: a propaganda afunda
sozinha, sem lista negra e sem LLM.

#### Uma inversão que corrige um erro da T13

Na T13 a banda 10k–500k foi escolhida por intuição, sem ninguém ter medido
nada. Agora os números são **resultado** do mapeamento: percentis dos perfis
achados, com a conta ao lado (`"p25 a p75 de 15 perfis medidos, mediana
1.435"`). Número sem a conta que o produziu é chute com cara de medição.

#### Três defeitos consertados no caminho

- **As migrations 004 e 005 não se registravam em `schema_migrations`** —
  herdado da T13. Idempotentes, então sem estrago, mas rodavam para sempre.
- **`costs.NIVEL` não conhecia `niche_mapping`:** o comando gastava e estourava
  na hora de registrar o gasto.
- **A medição ficava sem orçamento.** Agora a exploração guarda uma chamada de
  reserva: explorar mais vale menos que saber de quem se está falando.

#### Verificação

**762 conferências, zero falhas**, em 12 arquivos (eram 645). Rodadas reais:
o teto parando o laço em US$ 0,0540 de 0,06; o mapeamento completo com 292
termos e 40 perfis; o seco não escrevendo linha nenhuma; o `--aplicar` gravando
6 aprovadas e 34 reprovadas; e a busca exibindo `tags do nicho: #emergencias,
#desastres, #bomberos` com `banda vem de: nicho mapeado`.

Custo total: **US$ 0,0702 registrados**.


### 2026-08-30 — os critérios de coleta saem do código e viram variáveis

Até aqui, a única coisa que decidia o que a Apify trazia era o nicho e um teto
de quantidade. O resto era implícito. Esta entrada troca isso por critério
declarado, num lugar que o usuário controla.

#### Três hipóteses foram testadas contra o Actor. Duas caíram.

Custo total das sondas: **US$ 0,0081**.

1. **`onlyPostsNewerThan` funciona, mas vaza.** `"30 days"` virou `2026-07-31`
   corretamente. Ainda assim, 2 dos 4 reels devolvidos estavam fora da janela —
   e eram **exatamente os 2 com `isPinned: true`**:

   | data | fixado | views |
   |---|---|---|
   | 2024-10-09 | sim | 6.960.164 |
   | 2026-04-18 | sim | 3.348.237 |
   | 2026-08-28 | não | 953.973 |
   | 2026-08-25 | não | 351.405 |

   A correlação foi perfeita. Explica o post de abril com 3,3M que destoava no
   banco desde 28/08: é post fixado, não post recente.

2. **`searchType: "hashtag"` está morto.** Duas tentativas, as duas
   `no_items — Empty or private data`. Item de erro não é cobrado.

3. **Mas a descoberta por hashtag funciona por `directUrls`**, com
   `instagram.com/explore/tags/<tag>/`.

#### O viés que isso revelou

A busca por nome acha quem tem a palavra no **nome**, não quem publica no
assunto. **7 dos 9 perfis do banco tinham "receitas" no username.** A primeira
rodada pelo eixo novo trouxe `mf.meatfreaks` e `leonardoriverob` — dois perfis
que a busca por nome nunca acharia.

#### O que passou a existir

- `config.descoberta()` — eixos, banda de seguidores, só públicos, teto de
  qualificação
- `config.coleta()` — janela de dias, tipo, maturidade, o que fazer com fixado
- Flags espelho: `descobrir --eixos --seguidores MIN-MAX --max-qualificar` e
  `coletar --janela-dias --tipo --sem-fixados`
- Precedência declarada e testada: **flag > config > padrão**
- `pipeline.py` imprime os critérios em vigor no início de cada rodada
- Migration 004: `contents.is_pinned`, índice parcial, e a coluna na
  `v_content_current`
- `coletor.na_banda()` com **três** respostas: True, False e **None para "não
  dá para saber"** — o item da hashtag não traz contagem de seguidores, e
  reprovar por falta de informação mataria o candidato mais interessante calado
- `coletor.qualificar()`, a segunda chamada que resolve o None, com teto

#### A seção de config que ninguém lia

`busca.min_seguidores`, `busca.max_perfis` e `busca.somente_publicos` estavam
no `config.local.example.json` desde o começo e **nenhum código os
referenciava** — a config prometia um filtro que não acontecia, e nada na tela
denunciava. A seção saiu; `descoberta` a substitui, e agora é lida de verdade.

#### Verificação, com número

- **645 conferências, zero falhas**, 11 arquivos (eram 574)
- **Rodada real de descoberta por hashtag:** 10 candidatos, 5 qualificados
  (teto respeitado), **2 aprovados pela banda** — `mf.meatfreaks` (26.846) e
  `leonardoriverob` (11.895). Custo: US$ 0,0054
- **Os 9 perfis anteriores não foram tocados**, inclusive os 5 que a banda
  reprovaria (decisão do usuário: a banda vale para descoberta nova)
- **Rodada real de coleta** em `receitasdepai`: os 2 fixados entraram
  **marcados**, os recentes como `false`, e nenhum não-fixado furou os 30 dias.
  Os 2 posts da coleta de 28/08 ficaram `NULL` — "não se sabe" —, que é o
  honesto para linha gravada antes de a coluna existir

#### Decisões do usuário registradas

Janela de 30 dias (aprender o que funciona, não monitorar tendência); banda de
10k–500k; a banda vale só para descoberta nova. O teto de qualificação (20) foi
assumido por mim na ausência de resposta, e é configurável como todo o resto.


### 2026-08-29 — organização: sem Docker, com git, e o bug do emoji

O pedido era Docker, para "organizar os arquivos e o banco". A medição inverteu
a conclusão: **PostgreSQL nativo custa 17 MB**; Docker Desktop + WSL2 custaria
~1,2 GB numa máquina com **521 MB livres**. Seria trocar 17 MB por 1,2 GB para
substituir justamente a peça que funciona. Decisão do usuário, com o número na
mão: sem Docker. Registrada na [ADR 006](docs/decisions/006-postgres-nativo-em-vez-de-docker.md),
com prazo de validade — vale enquanto a máquina for esta.

Os incômodos por trás do pedido eram reais, e as causas não tinham nada a ver
com contêiner.

#### Reprodutibilidade: o clone novo não subia

Três bloqueios em sequência, todos removidos:

- **O portão morto.** `config.carregar()` exigia `instagram.usuario` e mandava
  "use a conta descartável". A ADR 005 tirou a conta do projeto em 26/08, e
  `usuario_instagram()` estava sem um único chamador. Era um portão trancado
  por uma chave que não existe mais — e `tests/_pg.py` também passava por ele,
  então **nem os testes rodavam em máquina limpa**. No lugar entrou
  `_exigir_postgres()`, que cobra o que de fato é obrigatório.
- **`config.local.example.json` não tinha a seção `postgres`.** Ganhou ela e a
  seção `dados`; perdeu a `instagram`.
- **Não havia caminho para montar o banco** desde que o `instalar-postgres.ps1`
  foi apagado. Entrou `src/preparar.py`: `verificar` faz 7 checagens e diz o
  conserto de cada uma; `criar-banco` cria e migra. **Verifica e instrui, não
  instala** (§14).

**Provado em clone limpo de verdade**, em pasta temporária: sem
`config.local.json`, apontou o que faltava e não pediu conta do Instagram; com
o exemplo copiado, apontou a senha do Postgres como único bloqueio restante.

#### O projeto virou um repositório

Existia `.gitignore`, não existia `.git` — impedimento que a T9 já registrava
("não haveria como desfazer"). Primeiro commit: **78 arquivos, 12.248 linhas**,
com `git check-ignore` conferido antes para provar que `config.local.json`,
`.venv/`, `dados/*` e `.sessoes/` ficaram de fora. Mais `.gitattributes`
fixando LF, para o git do Windows não inventar sessenta arquivos modificados.

#### BUG: o ranking quebrava no primeiro colocado

A simulação de clone limpo derrubou o `preparar.py` com `UnicodeEncodeError`.
Puxando o fio, apareceu coisa pior: **`pipeline.py ranking` quebrava com
traceback em qualquer legenda com emoji** — quase toda legenda de Instagram.

O erro morria em `'🍓'`, o morango de *"Morango Cravejado 🍓"*, que era
o **primeiro colocado** do ranking. O comando quebrava exatamente no melhor
resultado.

Por que ninguém viu: toda conferência da sessão em que o ranking nasceu rodou
com `PYTHONIOENCODING=utf-8` no ambiente. **A variável mascarava a falha.**
Fica a lição — variável conveniente no terminal de quem desenvolve é uma forma
de não testar o que o usuário vai rodar.

Conserto: `src/console.py`, chamado no início de cada `main()` dos sete
comandos. UTF-8 com `errors="replace"` de rede: relatório feio é melhor que
relatório que não sai. Vale sobretudo para o `preparar.py`, que existe para
dizer o que está errado.

#### Arquivos sob controle

`media_assets` já tinha `storage_key`, `file_size`, `asset_type` e
`created_at` — **nenhuma migration foi necessária**, só leitura e um comando.

- **`pipeline.py limpar`, seco por padrão.** Só apaga com `--aplicar`, pela
  mesma disciplina do freio de custo da Apify: mostra a conta antes de cobrar.
  Alvos: `--transcritos` (mídia cujo conteúdo já virou transcrição),
  `--orfas` (descompasso disco↔banco), `--antes-de N`.
- **A regra que decide o que pode sumir:** só o que já tem transcrição. O mp4
  é re-baixável pelo link; a transcrição custou CPU e não volta.
- **Apagar o arquivo apaga o registro** — `media.tem()` é a checagem de
  idempotência, e uma linha apontando para arquivo inexistente faz o sistema
  mentir. Mas **não devolve o vídeo para a fila**: o job continua `done`, senão
  a limpeza vira moto-contínuo caro. Há teste para as duas afirmações.
- **Reconciliação nos dois sentidos**: registro sem arquivo e arquivo sem
  registro.
- **`status` diz para onde o disco foi**: quebra por tipo, os 5 perfis mais
  pesados, quanto dá para liberar agora, e aviso ao passar do teto do config.
- **`config.dados()`** — retenção em configuração, tudo desligado por padrão.

#### Números

- **574 conferências, zero falhas** (eram 488 na abertura do dia), em 11
  arquivos. Dois novos: `test_preparar.py` e `test_repos_arquivos.py`.
- `limpar` rodado seco contra os 15 vídeos reais: 0 liberáveis (nada transcrito
  ainda), nenhum descompasso, e **os 15 arquivos continuam no disco** —
  conferido por `find` antes e depois.

### 2026-08-28 (2) — a esteira do MVP contra o ambiente real, e o `-1`

Primeira rodada de ponta a ponta com dados reais desde a migração. Nicho
escolhido: `receitas`. Custo total da prova: **US$ 0,0459**.

- **`descobrir "receitas"` → 8 perfis**, todos públicos, com bio, categoria,
  contagem e link. Contraste que vale registrar: `apostas` tinha devolvido
  **1** perfil com 12 seguidores. A busca por termo não é ruim em geral — ela
  é ruim para nichos que o autocomplete do Facebook Ads não indexa.
- **`coletar` → 15 posts, 15 vídeos**, com `content_metric_snapshots`,
  41 hashtags e 10 menções. `profile_snapshots` gravou a série temporal.
- **`baixar` → 15 de 15, zero falhas**, 293 MB em 5min40. Rodar de novo
  respondeu **"Fila vazia"** — reexecução não duplica, agora provado com 15
  itens e não com um.
- **`ranking` funcionou sobre os dados reais** e comparou 14 dos 15 (o
  décimo quinto é de outro dono, fora do nicho — exclusão correta).
- **Série temporal provada de verdade:** a recoleta 14 minutos depois gravou
  uma segunda leitura, e as visualizações subiram (5.870 → 6.131). O modelo de
  snapshot faz o que prometia.

#### BUG encontrado e corrigido: `-1` não é um número

Dois dos 15 posts (@receitas) vieram com `likesCount: -1`. **É o sentinela do
Instagram para "curtidas ocultas", não uma medição.** Guardado cru, produzia
**engajamento negativo (-0,01%)** e derrubava o post no ranking por um motivo
que nada tem a ver com desempenho.

O projeto já tinha a regra certa escrita no próprio arquivo — *"None é
honesto; zero seria afirmar que ninguém salvou"* — mas ela só protegia
`shares` e `saves`. O `-1` passava por baixo dela.

- `coletor._contagem()` novo: qualquer contagem negativa vira `None`.
  Aplicado a seguidores, seguindo, posts, visualizações, curtidas,
  comentários, compartilhamentos e salvamentos.
- **6 conferências novas** (494 no total), incluindo dois controles: zero
  continua zero e número normal passa intacto.
- Verificado contra a API real, não só no teste: a recoleta do mesmo perfil
  gravou `likes = NULL`, e a view voltou a dar engajamento positivo.
- As duas leituras antigas com `-1` foram zeradas para `NULL` no banco.
- Limpo também o `processing_jobs` órfão da sessão anterior (apontava para um
  `content_id` que não existe mais — a referência é polimórfica, sem FK).

#### Dois achados registrados, ainda sem conserto

1. **`raw_data` nunca é preenchido.** `repos/profiles.salvar` e
   `repos/contents.salvar` aceitam `guardar_bruto`, e a docstring diz que é
   ele que permite auditar a fonte. **O `pipeline.py` não passa em nenhuma das
   4 chamadas** — 0 de 15 conteúdos e 0 de 9 perfis têm o JSON cru. Foi
   exatamente o que faltou para conferir o `-1`: tive de deduzir.
2. **Perfil-fantasma por post de colaboração.** `@premiere` foi criado
   automaticamente (`pipeline.py:219`) porque um post de @receitas tem outro
   dono. Ficou sem nicho, sem seguidores e sem aprovação — mas o vídeo dele
   foi baixado e ocupa `dados/perfis/premiere/`. Atribuir o post ao dono real
   está certo; criar perfil não descoberto em silêncio é que merece decisão.

### 2026-08-28 — PostgreSQL de verdade, repositories, e o Actor conferido

Migração completa do SQLite para o PostgreSQL pelo caminho lento e seguro,
escolhido pelo usuário: primeiro os repositories com testes, e só no fim o
pipeline religado.

- **PostgreSQL 17 instalado e rodando.** Três percalços resolvidos e que valem
  ficar registrados: o instalador exige **UAC** (só o usuário podia conceder);
  o `Set-Content -Encoding utf8` do PowerShell 5.1 grava **BOM** e o
  `json.load` recusa (o `config.py` passou a ler com `utf-8-sig`); e a senha
  gerada tem `/`, `[` e `:`, que **quebram a URL de conexão** — a correção não
  foi enfraquecer a senha, foi conectar por parâmetros separados.
- **Três migrations, 20 tabelas:**
  - `001_intelligence` — as 12 entidades da arquitetura do usuário, mais
    `niche_profiles` (N:N), `content_hashtags` e `content_mentions`
  - `002_transcricao` — `transcripts`, `transcript_segments` e
    `transcript_words`. Nasceu de um buraco real: 4 das 11 perguntas não
    tinham onde morar, e o editor precisa do **tempo por palavra** para a
    legenda karaokê. Busca full-text com `tsvector` português + GIN, no lugar
    do FTS5.
  - `003_visao_atual` — a view `v_content_current`, que entrega conteúdo +
    dono + a leitura mais recente das métricas, com o engajamento calculado e
    **a base dele declarada**. Seis consultas usavam o mesmo `DISTINCT ON`.
- **`src/repos/` — a única camada que escreve SQL.** Dez módulos: `niches`,
  `profiles`, `contents`, `metrics`, `jobs`, `media`, `costs`, `transcripts`,
  `analyses`, `consultas`.
- **`processing_jobs` substituiu a tabela `downloads`.** Uma mecânica para
  todas as etapas caras, em vez de uma máquina de estados por etapa.
- **`pipeline.py` reescrito** sobre os repositories. **Não escreve mais SQL.**
- **`content_analyses` não é só para LLM:** as contas determinísticas gravam
  com `model='metricas.py'`, o que permite comparar depois com um modelo pago
  e decidir se ele vale a fatura — em vez de aceitar por fé.
- **Prova de ponta a ponta, com download real:** o Reel público
  `Chunk8-jurw` baixado pelo pipeline novo (1,9 MB), gravado em
  `media_assets`, e rodar de novo respondeu "Fila vazia".
- **Rodada real na Apify** (run `y7QKvQUMo73pGrPFD`, custo US$ 0,00). Três
  coisas só apareceram aí, e nenhuma estava na documentação:
  - `resultsLimit` tem mínimo **1** — não existe "só o perfil, nenhum post";
  - **`externalUrls` é plural e é lista**, não `externalUrl` string. O link da
    bio vinha sempre vazio e ninguém notaria, porque `None` é plausível;
  - **os posts vêm aninhados em `latestPosts`** dentro do item de perfil, não
    como itens soltos. Sem desaninhar, a coleta traria zero posts.
  - Bônus: existe `relatedProfiles`, fonte de descoberta melhor que a busca
    por termo, porque parte de um perfil já conhecido.
- **A busca por termo mostrou o que ela é:** "apostas" devolveu **um** perfil,
  com **12 seguidores**, via autocomplete do Facebook Ads. Confirma na prática
  a ressalva registrada desde o começo.
- **Apagados** (cópia no scratchpad da sessão): `src/ig.py`, `src/buscar.py`,
  `src/coletar.py`, `tests/test_pipeline.py`.
- **488 conferências passando.**

### 2026-08-26 (2) — banco v3: série temporal e score de oportunidade

O usuário achou o banco cru e mandou uma lista de variáveis. Metade delas o
Instagram **não publica** — a tabela de honestidade ficou registrada na T9.
O que era obtenível entrou; o que não era virou coluna `NULL` explícita.

- **Duas tabelas de série temporal.** Foi o achado que mudou o desenho:
  `followers_growth_7d` e `avg_views_per_reel` **não são calculáveis de uma
  coleta só**. `perfis` guarda o agora e sobrescreve; crescimento é diferença,
  e diferença precisa de duas linhas.
  - `perfis_historico` — uma foto de seguidores/seguindo/posts por coleta
  - `metricas_historico` — os números de cada post com a hora da medição
- **Velocidade não virou coluna, e de propósito.** `views_per_hour` depende de
  *quando* foi medido; congelar isso numa coluna guardaria uma resposta que
  envelhece. Grava-se a medição crua com a hora; a velocidade é conta de
  leitura e continua correta para sempre.
- **13 colunas novas** em `perfis` (avatar, categoria de negócio, aprovado,
  classificado_em) e `posts` (thumbnail, áudio, local, e
  `compartilhamentos`/`salvamentos` que ficam `NULL` porque o Instagram não
  os publica — `NULL` é honesto, `0` seria mentira).
- **`classificar_perfil()` separado de `salvar_perfil()`.** Recoletar o perfil
  não pode apagar o julgamento que você fez sobre ele. Coberto por teste.
- **`src/desempenho.py`** — só função pura, como `metricas.py`:
  - engajamento que **declara a base** (views, ou seguidores quando o
    Instagram esconde as views — 4% sobre uma base não é 4% sobre a outra)
  - velocidade com piso de 1h, para post de 3 minutos não virar foguete
  - **score de oportunidade em percentil dentro do grupo**, não em valor
    absoluto: a pergunta é "quem performa anormalmente bem no nicho"
  - **mediana, não média** — views de Reels têm cauda longa e um viral
    sozinho deformaria a média
  - **peso ausente é renormalizado**: se `visualizacoes` não vier, o score não
    é punido em 15%; o peso se redistribui. Dado ausente não pode virar nota baixa
- **Pesos em configuração, score calculado na leitura.** Mudar um peso
  re-ranqueia tudo na hora, sem recoletar e sem gastar um centavo.
- **Bug achado por teste:** velocidade era só views/hora, então sem views o
  score perdia 45% do peso — justo quando o Instagram esconde views. Agora ela
  cai para curtidas/hora e declara a base, igual ao engajamento.
- **`pipeline.py ranking`** — novo comando. Provado com dados sintéticos: o
  reel de um perfil de 32k com 41k views **ganhou** de um perfil de 210k com
  71k views, porque estava correndo mais rápido. É o comportamento pedido.
- **273 conferências passando** (34 + 54 + 68 + 51 + 66).

### 2026-08-26 — a coleta troca de mãos: Apify + yt-dlp

O gargalo que travava o projeto era a conta do Instagram. Ela nunca conseguiu
entrar. **A raspagem própria sai inteira** e vira serviço de terceiro.

- **ADR 005:** Apify descobre e lista, yt-dlp baixa. A restrição "Sem API paga"
  do `CLAUDE.md` foi revogada pelo usuário nesta data (V1 §14.4).
- **Dois fatos verificados antes de escrever código:**
  - o `InstagramUserIE` do yt-dlp tem `_WORKING = False` no código-fonte — ele
    **não** lista perfil, e é por isso que a Apify entra;
  - o yt-dlp **baixa Reels público sem login e sem cookie** — testado contra
    `instagram.com/reel/Chunk8-jurw/`: 1,95 MB em 8,1s.
- **Banco na versão 2.** Duas tabelas novas e cinco colunas:
  - `downloads` — a máquina de estados do pipeline (`discovered`, `queued`,
    `downloading`, `downloaded`, `processed`, `failed`). **Esta tabela é a
    fila**: não há Redis nem Celery, e `status='queued'` é quem espera vez.
    Separada de `posts` pelo mesmo critério que já separou `metricas`: o que o
    Instagram afirma fica em `posts`, o que nós fizemos fica aqui.
  - `coletas` — o que cada rodada custou de verdade, com `usage_total_usd` vindo
    da própria Apify. Sem isso as métricas de custo seriam chute.
  - `perfis` ganhou `perfil_id`, `link_perfil`, `nicho`, `categoria`,
    `relevancia`, com migração por `ALTER TABLE` para banco antigo continuar
    abrindo.
- **Módulos novos, uma interface e uma implementação cada** (sem adaptador
  especulativo de S3 nem coletor de Playwright — V1 §12):
  - `src/coletor.py` — `InstagramCollector` / `ApifyInstagramCollector`
  - `src/downloader.py` — `VideoDownloader` / `YtDlpDownloader`
  - `src/storage.py` — `Storage` / `LocalStorage`
  - `src/pipeline.py` — `descobrir`, `coletar`, `baixar`, `status`, `schema`
- **Três freios de custo**, porque o botão é silencioso: estimativa com
  confirmação antes de rodar, `max_total_charge_usd` (quem para é a Apify, não
  a fatura) e `max_items`.
- **O layout de disco não mudou de propósito:** `dados/perfis/<user>/<id>/` com
  `post.json` + `midia.*`. É exatamente onde `transcrever.py` e `analisar.py` já
  procuram — a etapa de análise nem fica sabendo que a coleta trocou de dono.
- **48 conferências novas do pipeline** (`tests/test_pipeline.py`) e **51 da
  coleta** (`tests/test_coleta.py`). Com as antigas: **187 passando**, contadas
  na saída real dos quatro arquivos.
  Incluem o critério que o usuário pediu: rodar o pipeline duas vezes não gera
  dois downloads, e desligar o PC no meio não perde o item da fila.
- Instalados: `apify-client 3.1.3`, `yt-dlp 2026.8.19`, `curl-cffi 0.16.2`.
  Removido: `browser_cookie3`.
- **Pendente:** o mapeamento de campos do Actor está `[NÃO VERIFICADO]` — veio
  da documentação. `pipeline.py schema` troca isso por fato por alguns centavos.

### 2026-08-25 — escopo revisado (banco + edição)

O usuário ampliou o escopo: além de analisar, o projeto passa a **guardar em banco
de dados** e a **editar vídeo**. Aprovado por ele nesta data (V1 §14.4).

- **`docs/ARCHITECTURE.md` criado** — a arquitetura revisada passa a mandar sobre o
  plano original em `docs/PROJECT.md`.
- **ADR 003:** SQLite como espinha, no lugar de JSON solto. Verificado na máquina:
  3.49.1 com FTS5 e JSON1, sem instalar nada.
- **ADR 004:** ffmpeg para a edição; Remotion recusado por ora. Motivo medido, não
  opinado: o Remotion renderiza quadro a quadro por um Chromium invisível, e tudo
  que foi pedido (legenda, headline, fundo, logo) é sobreposição estática.
  Verificado que o ffmpeg instalado tem libass, libfreetype, libharfbuzz, fontconfig
  e os filtros drawtext, subtitles, overlay, scale, pad, gblur, concat e fade.
- **T7 — banco: núcleo pronto.**
  - `src/banco.py` — 9 tabelas, esquema idempotente, nenhum outro módulo escreve SQL
  - `src/consultas.py` — 11 perguntas, incluindo hashtag × engajamento × visualização
  - `tests/test_banco.py` — **45 conferências passando**: não duplica ao regravar,
    hashtag removida some, refazer transcrição substitui, cascade funciona, FTS5 acha
    palavra falada
- **T8 — edição: desenhada, não construída.** `selecionar.py`, `legenda.py`,
  `editar.py` e template em JSON.
- Descoberto que o Whisper aceita **`word_timestamps`** — tempo por palavra. É o que
  permite legenda estilo Reels, palavra acendendo conforme é falada, sem dependência
  nova. `transcrever.py` precisa passar a pedir.
- **Recusado:** automatizar criação de conta no Instagram. É o padrão de conta falsa
  em massa e derrubaria o projeto junto.
- `config.local.json` criado com o usuário da conta descartável. A senha não está lá
  e não vai estar.

### 2026-08-25

- **ADR 002 registrada:** modelo de transcrição `small` por padrão, `base` como
  escape. Medição: `base` 0,17x e `small` 0,49x a duração do vídeo, **ambos com
  1,2% de palavras erradas** em português acentuado. Carga do modelo em cache: 9s.
  A escolha do `small` é margem de segurança para áudio com música, não ganho medido —
  e há reavaliação marcada com Reels real.
- **Bug de ordem de captura de exceção corrigido** em `buscar.py` e `coletar.py`:
  `LoginRequiredException` **não** é subclasse de `ConnectionException`. Caía no
  `except InstaloaderException` genérico, então uma sessão morta no meio da execução
  imprimiria "falhou - pulando" para cada perfil e terminaria dizendo que nada foi
  encontrado, em vez de avisar que o login caiu. Achado conferindo a hierarquia de
  exceções da biblioteca instalada, não em produção.
- Conferência da API do Instaloader 4.14.1: **as 40 chamadas, campos e parâmetros
  usados pelo código existem nesta versão**, verificado por introspecção.
- **T4 (Transcrição) — código escrito e MEDIDO:**
  - `src/midia.py` — acha o ffmpeg sem depender do PATH (terminal aberto antes da
    instalação não o enxerga) e extrai áudio 16 kHz mono. Verificado: 5,00s exatos.
  - `src/transcrever.py` — faster-whisper local, VAD ligado, retomável, apaga o WAV
    depois de usar.
  - **Medição real:** 42,7s de fala em português transcritos em 17,5s com o modelo
    `base` = **0,41x** a duração. O plano estimava 3 a 5 minutos por minuto de vídeo,
    ou seja, errou por uma ordem de grandeza. RAM do `base`: ~240 MB.
- **T5 (Análise) — código escrito e testado:**
  - `src/metricas.py` — só função pura (gancho, ritmo, legenda, chamada para ação,
    engajamento), para poder conferir cada conta isoladamente.
  - `src/analisar.py` — agrega por perfil e monta `_comparativo.json` entre perfis.
  - `tests/test_metricas.py` — **33 conferências, todas passando**, sem instalar pytest.
- **T6 (Relatório) — código escrito, portão visual PENDENTE:**
  - `src/relatorio.css` — design system em variáveis CSS, modo escuro, regra de
    tela pequena. Sem Tailwind: o projeto não tem Node.
  - `src/relatorio.py` — HTML único, CSS embutido, funciona offline.
  - **Bug encontrado e corrigido:** a linha do tempo do vídeo aparecia zero vezes,
    porque só era mostrada para o post mais engajado — e quando esse post era um
    carrossel, a estrutura sumia da página. Agora vem do vídeo mais engajado.
  - **A nota visual não foi dada:** não há navegador automatizado nesta sessão, e a
    regra proíbe declarar tela pronta lendo código.
- `CLAUDE.md` corrigido: a estimativa de lentidão da transcrição estava errada.
- **T1 (Ambiente) CONCLUÍDA.** Python 3.12.10, ffmpeg 9.0, instaloader 4.14.1 e
  faster-whisper 1.1.1 instalados e verificados com saída real dos comandos.
  Ambiente isolado em `.venv/`.
- `.gitignore`: acrescentada `.sessoes/` — o arquivo de sessão do Instaloader
  equivale a uma senha guardada.
- **T2 (Busca) — código escrito**, parado no gate da conta descartável:
  - `src/config.py` — caminhos do projeto e leitura validada do `config.local.json`
  - `src/ig.py` — Instaloader com `RitmoLento` (intervalo mínimo fixo entre
    requisições) e sessão salva, reaproveitado depois pela coleta
  - `src/buscar.py` — duas fontes de perfis (busca direta + autores dos posts em
    alta da hashtag), filtro por seguidores/privacidade, saída em
    `dados/buscas/<termo>.json`
- **T3 (Coleta) — código escrito**: `src/coletar.py`, retomável (post já baixado
  é pulado), pausa entre posts e entre perfis, `post.json` por post com legenda,
  hashtags, curtidas, comentários, data/hora, tipo, duração e visualizações.
- Estrutura do projeto criada (V1 §13): `src/`, `docs/`, `tasks/`, `dados/`, `saida/`.
- `.gitignore` protegendo `config.local.json`, arquivos de sessão do Instaloader e dados baixados.
- ADR 001 registrada: Instaloader em vez de ScrapeGraphAI.
- T1 (Ambiente) aberta em `tasks/active/`, parada no gate de instalação (V1 §14).
