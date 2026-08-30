# T14 — Mapeamento de nicho: a fase que falta antes da busca

**ID:** T14
**Workflow:** BUILD, aberto por um ciclo de INVESTIGATION (sonda bloqueante)
**Status:** CONCLUÍDA em 30/08/2026
**Origem:** pedido do usuário — *"a questão da pesquisa não me parece apenas uma
mera requisição de API, existe todo um modo de pesquisar. Antes do input existe
um processo de mapeamento"*
**Criada:** 2026-08-30
**Depende de:** T13 (critérios como variáveis), concluída

## O problema

O sistema tem um regime só: você já sabe o termo, pede, recebe. Assume que o
vocabulário do assunto é conhecido — e funcionou com "receitas" por acidente,
porque o termo é a palavra que as pessoas usam.

Com *"perfis que falam de desastres e tragédias"* isso quebra na primeira
linha. `#desastres` provavelmente não é onde esse conteúdo vive. **O input que
o sistema exige é justamente o output que ainda não se tem.**

E há um erro meu na T13 que só ficou visível agora: eu fiz o usuário escolher
a banda 10k–500k **sem que nenhum de nós dois tivesse medido nada**. Para um
tema novo ninguém sabe a banda certa de antemão. O quantitativo deveria ser
resultado do mapeamento, não pergunta antes dele.

## Os dois regimes

| | MAPEAR (novo) | BUSCAR (existe) |
|---|---|---|
| parte de | um tema em português comum | um nicho mapeado |
| se sabe | quase nada | vocabulário, sementes, números |
| pergunta | "onde isso vive?" | "quem performa agora?" |
| termina | saturação ou teto de gasto | fila vazia |

## Decisões do usuário (30/08/2026)

1. Freio: **teto em US$** (garantia dura) **+ saturação** (economia).
2. Entrega: vocabulário + perfis-semente + **números medidos e propostos**.
3. Aprovação: **tag por tag, perfil por perfil**. Nada entra sozinho.
4. O nicho mapeado mora **no banco**, na tabela `niches`.

## Parte 0 — A sonda bloqueante  ✅ RESPONDIDA

O eixo de expansão por perfil relacionado sustentava metade do laço, e a única
evidência era `relatedProfiles: []` — de `donclipss`, conta com 12 seguidores e
0 posts. Rodada contra `receitasdepai` (3,1M) em 30/08/2026, custo US$ 0,0000:

- **`relatedProfiles` devolveu 15 perfis.** O eixo 2 entra como desenhado. A
  lista vazia anterior era da conta vazia, não do campo.
- **`resultsType: details` traz `latestPosts: 12` com as hashtags juntas.** Um
  item de perfil já entrega vocabulário — o mapeamento sai mais barato do que
  o plano supunha.

Dois achados que mudam detalhe de desenho:

- **O relacionado vem SEM contagem de seguidores** — só `username`,
  `full_name`, `is_private`, `is_verified`, `id`. É candidato indeterminado,
  igual ao da hashtag. O `qualificar()` da T13 já serve aos dois eixos.
- **As hashtags colhidas incluem `publi`, `MercadoLivre`, `PagBank`,
  `AeC440`** — vocabulário de PUBLICIDADE, não do nicho. E vêm acentuadas:
  `receitasfáceis`. Portanto: (a) ranquear por **perfis distintos** é o
  critério primário, não frequência; (b) `tag_do_termo()` **não pode** ser
  aplicado a tag já válida — ele remove acento e produziria outra tag.

- [x] **0.** Sonda de `relatedProfiles` contra perfil real

## Parte A — Banco (migration 005)

- [x] **A1.** `collection_jobs.job_type` aceita `'niche_mapping'` (o CHECK é
      fechado — conferido)
- [x] **A2.** `data_costs.operation` aceita `'niche_mapping'`
- [x] **A3.** `niches.criteria JSONB`
- [x] **A4.** Tabela `niche_terms` — a EVIDÊNCIA do mapeamento, não só o
      resultado, para permitir re-ranquear sem remapear

## Parte B — Coletor

- [x] **B1.** `tags_dos_itens()` — pura: itens → co-ocorrência por tag e por
      perfil distinto
- [x] **B2.** `relacionados_de()` — usa `perfis_relacionados()`, órfão desde
      que nasceu
- [x] **B3.** `mapear_tag()` — uma rodada de tag
- [x] **B4.** `url_da_tag()` deixa de destruir tag já válida (o acento)

## Parte C — `src/mapeador.py`, lógica pura

- [x] **C1.** `ranquear_termos()` — perfis distintos primeiro, posts depois
- [x] **C2.** `saturou()` — menos de 20% de vocabulário inédito
- [x] **C3.** `numeros_do_nicho()` — percentis, duração, ritmo → banda sugerida
      **com a conta que a justifica ao lado**
- [x] **C4.** `montar_dossie()` / `ler_dossie()`

## Parte D — `pipeline.py mapear`

- [x] **D1.** Seco por padrão, como o `limpar` da T12: escreve dossiê, não toca
      no banco
- [x] **D2.** `mapear aplicar` grava só o aprovado
- [x] **D3.** Teto de USD como freio duro do laço

## Parte E — A busca lê o nicho

- [x] **E1.** Precedência `flag > nicho (banco) > global (config) > padrão`
- [x] **E2.** O eixo hashtag usa as tags **aprovadas**, e não a derivada do
      nome do nicho

## Verificação (V1 §10)

**1. 762 conferências, zero falhas**, em 12 arquivos. Eram 645 na abertura da
task. A suíte nova `test_mapeador.py` tem 62 e não toca em rede, banco nem
dólar.

**2. O teto interrompe de verdade** — `--teto-usd 0.06 --itens-por-tag 10`:

```
Rodada 1: #desastresetragedias, #desastres, #tragedias
  #desastresetragedias       1 itens,   0 termos no total
  #desastres                20 itens,  64 termos no total
Rodada 2: #emergencias, #perú
Parou por: teto. Custo estimado US$ 0.0540 (teto US$ 0.06)
```

A rodada 2 foi **planejada e não paga**. É o teto agindo, não avisando.

**3. Mapeamento real de "desastres e tragedias"** — `--teto-usd 0.30
--itens-por-tag 20`: **292 termos, 40 perfis**, custo real US$ 0,0270. As mais
fortes, por perfis distintos:

| tag | perfis | posts |
|---|---|---|
| #emergencias | 24 | 24 |
| #desastres | 20 | 23 |
| #bomberos | 4 | 4 |
| #prevención | 4 | 4 |
| #gestióndelriesgo | 3 | 4 |

Banda medida: **404 a 4.065 seguidores** (p25–p75 de 15 perfis medidos,
mediana 1.435).

**4. `mapear` sem `--aplicar` não escreveu nada.** Antes e depois de quatro
rodadas: `niches` 1, `niche_terms` 0, `profiles` 11. O que ele grava sempre é
o job e o custo — US$ 0,0405 em `data_costs`, porque dinheiro gasto se anota
mesmo quando o resultado é descartado.

**5. `--aplicar` gravou só o marcado:** 6 tags aprovadas, 34 registradas como
reprovadas, 2 perfis aprovados e ligados ao nicho. `niches.criteria` recebeu a
banda com a origem (`"mapeamento de 2026-08-30T01:39:39"`).

**6. A busca passou a usar o vocabulário aprovado:**

```
  tags do nicho      #emergencias, #desastres, #bomberos
  banda vem de       nicho mapeado
  seguidores         404 a 4065
```

Não `#desastresetragedias`, e não a banda global 10k–500k. A precedência
`flag > nicho > global > padrão` aparece na tela.

## O que o mapeamento descobriu, e que ninguém sabia

**O tema em português não é uma hashtag.** `#desastresetragedias` devolveu
**1 item e zero termos**. A cascata de sementes (`#desastres`, `#tragedias`)
foi escrita por causa dessa falha, não antes dela.

**E o vocabulário voltou em espanhol.** `#emergencias`, `#bomberos`,
`#prevención`, `#gestióndelriesgo`, `#perú`, `#inscripcionesabiertas` — um
cluster de **defesa civil e cursos de formação** hispano-americano, não de
notícia de tragédia brasileira. Nenhum de nós dois teria adivinhado isso, e é
exatamente o que o mapeamento existe para mostrar. Se o alvo for conteúdo
brasileiro, o tema precisa de outra semente — e agora dá para saber disso por
US$ 0,03 em vez de descobrir depois de uma coleta inteira.

## Três defeitos encontrados durante a execução

1. **As migrations 004 e 005 não se registravam** em `schema_migrations` —
   defeito herdado da T13. O DDL era idempotente, então não houve estrago, mas
   elas rodavam de novo a cada `migrar.py aplicar` e o `status` mentiria para
   sempre. Consertadas, e há teste para as duas.
2. **`costs.NIVEL` não conhecia `niche_mapping`.** O CHECK do banco foi aberto
   na migration e o mapa do Python não — o comando rodava, gastava, e estourava
   na hora de registrar o que gastou.
3. **A medição ficava sem orçamento.** O laço gastava US$ 0,324 de 0,35
   explorando e a banda saía de 6 perfis quaisquer. Agora a exploração roda com
   uma chamada de reserva no bolso: explorar mais vale menos que saber de quem
   se está falando.

## Custo total da task

US$ 0,0405 em mapeamento + US$ 0,0297 em descoberta = **US$ 0,0702
registrados**. A conta da Apify segue marcando US$ 0,0000 no ciclo — ou o plano
grátis não cobra estas chamadas, ou o painel atrasa. O projeto registra pela
estimativa e pelo que o Actor devolve, e não pelo painel.

## Fora de escopo

`selecionar.py` continua separado: o mapeamento aprova **vocabulário**, não
perfil. Nenhum LLM. Nenhuma moderação automática — `niche_terms` com
`kind = termo_proibido` é o instrumento para cortar o que não se quer ver.
