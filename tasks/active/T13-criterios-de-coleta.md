# T13 — Critérios de coleta: variáveis, não constantes

**ID:** T13
**Workflow:** BUILD, precedido de INVESTIGATION (sondas pagas contra o Actor)
**Status:** CONCLUÍDA em 30/08/2026
**Origem:** pedido do usuário — *"eu não defini como vc faz as requisições da
Apify, qual critério vc usa pra puxar os dados"*, com a exigência de que
*"essas definições sejam mais dinâmicas: eu posso escolher essas variáveis"*
**Criada:** 2026-08-30

## Objetivo

Trocar critério implícito por critério declarado, e declarado em lugar que o
usuário controla: `config.local.json` com espelho em flag de linha de comando.

## O que as sondas provaram (custo real: US$ 0,0081)

Antes de codar, três hipóteses foram testadas contra o Actor de verdade.
**Duas caíram.**

1. **`onlyPostsNewerThan` funciona, mas vaza.** `"30 days"` virou
   `2026-07-31` (log do run). Ainda assim 2 dos 4 reels devolvidos estavam
   fora da janela — e eram **exatamente os 2 com `isPinned: true`**
   (2024-10-09 com 6,9M views; 2026-04-18 com 3,3M). A correlação foi
   perfeita. Explica o post de abril que destoava no banco.
2. **`searchType: "hashtag"` está morto.** Duas tentativas, as duas
   `no_items — Empty or private data`. Custo zero: item de erro não é cobrado.
3. **Descoberta por hashtag funciona por `directUrls`**, com
   `instagram.com/explore/tags/<tag>/`. Achou `mf.meatfreaks`,
   `kelyc_receitas` e `leonardoriverob` — dois deles jamais viriam pela busca
   por nome. Confirma o viés: **7 dos 9 perfis do banco têm "receitas" no
   username**; descobríamos por nomenclatura, não por desempenho.
4. **A aba da tag ordena por recência, não por desempenho**, e **não traz
   contagem de seguidores** (nem com `addParentData`). Logo, aplicar a banda
   10k–500k a um candidato de hashtag exige uma segunda chamada paga — daí o
   teto de qualificação.
5. `resultsType: "reels"` funciona: 4 de 4 vieram `Video`/`clips`.
6. Custo real medido: ~US$ 2,03/1.000 itens, abaixo dos US$ 2,70 que o código
   assume. A estimativa erra para o lado seguro; fica como está.

## Decisões do usuário (§14)

- Janela de **30 dias** — aprender o que funciona, não monitorar tendência.
- Banda de seguidores **10.000–500.000**.
- A banda vale para **descoberta nova**. Os 9 perfis já coletados ficam como
  estão, mesmo os 6 que a banda reprovaria.
- Vale gastar centavos para conferir a hashtag. *(Gasto e registrado acima.)*
- Teto de qualificação por rodada: **20**, assumido por mim na ausência de
  resposta, e configurável como todo o resto.

## Parte A — as variáveis

- [x] **A1.** `config.descoberta()` — eixos, max_perfis, seguidores_min,
      seguidores_max, somente_publicos, aprovacao_manual, max_qualificar
- [x] **A2.** `config.coleta()` — janela_dias, tipo, posts_por_perfil,
      maturidade_horas, incluir_fixados
- [x] **A3.** `config.local.example.json` com as duas seções; a seção `busca`,
      que ninguém lia, sai
- [x] **A4.** Precedência `flag > config > padrão`, com teste para cada nível

## Parte B — o Actor

- [x] **B1.** `normalizar_post` captura `isPinned` → `fixado`
- [x] **B2.** `descobrir_perfis` aceita eixo `nome` e eixo `hashtag`
- [x] **B3.** `qualificar()` — candidato sem seguidores → `details`, com teto
- [x] **B4.** `coletar_conteudo` passa `onlyPostsNewerThan` e `resultsType`
- [x] **B5.** `na_banda()` — função pura, testável sem rede

## Parte C — o pipeline

- [x] **C1.** `descobrir --eixos --seguidores MIN-MAX --max-qualificar`
- [x] **C2.** `coletar --janela-dias --tipo --sem-fixados`
- [x] **C3.** A banda filtra só o que é novo; perfil já gravado não é tocado
- [x] **C4.** Post fixado é gravado marcado, e fica fora das contas de recência

## Parte D — o banco

- [x] **D1.** Migration 004: `contents.is_pinned`
- [x] **D2.** `v_content_current` expõe `is_pinned` (coluna ao final — é o que
      `CREATE OR REPLACE VIEW` permite)
- [x] **D3.** `contents.salvar()` grava o campo

## Verificação (V1 §10)

**1. 645 conferências, zero falhas**, nos 11 arquivos. Eram 574 na abertura.
As 71 novas cobrem: a banda nos dois extremos e no limite exato, o terceiro
estado (None), a tag normalizada, o dono deduplicado, o `isPinned` nas três
formas, a entrada montada para o Actor em cada eixo, a precedência da config e
a coluna nova no banco.

**2. Rodada real de descoberta por hashtag** — `descobrir "receitas" --eixos
hashtag --max-perfis 10 --max-qualificar 5`:

```
10 achados: 2 gravados (2 novos no nicho, 0 ja existiam), 8 fora da banda.
Custo real: US$ 0.0054 (15 itens)
```

Entraram `mf.meatfreaks` (26.846 seguidores) e `leonardoriverob` (11.895).
**Nenhum dos dois tem "receitas" no nome** — é a prova de que o eixo novo
quebra o viés. Os 8 restantes ficaram de fora: 3 reprovados pela banda depois
de qualificados, 5 sem qualificação por causa do teto.

**3. Os 9 perfis anteriores não foram tocados** — conferido por consulta antes
e depois. Os 5 acima de 500 mil continuam lá, como o usuário decidiu.

**4. Rodada real de coleta** — `coletar --perfis receitasdepai --posts 4
--janela-dias 30 --tipo reels`. O banco depois:

| code | publicado | fixado |
|---|---|---|
| Dclkfh0soGQ | 2026-08-28 | false |
| DceDX2GsVr9 | 2026-08-25 | false |
| Dca3wOTANL2 | 2026-08-24 | **NULL** |
| DcECIWosRUW | 2026-08-15 | **NULL** |
| DXRxN6ujKhd | 2026-04-18 | **true** |
| DA6gDPHSjYt | 2024-10-09 | **true** |

Os dois de fora da janela vieram marcados. Os dois `NULL` são da coleta de
28/08, antes de a coluna existir — e `NULL` ali é o honesto: ninguém sabe se
eram fixados naquele dia.

**5. Nenhum não-fixado furou a janela** — consulta contando não-fixados com
mais de 30 dias devolveu 0.

**Custo total do dia:** US$ 0,0081 nas sondas + US$ 0,0054 na descoberta +
US$ 0,0000 na coleta (a Apify não cobrou a última) = **US$ 0,0135**.

## O que ficou aberto para o usuário

O `config.local.json` **dele** ainda tem a seção `busca`, que agora não existe
mais no código, e não tem as seções `descoberta` e `coleta` novas — então está
rodando nos padrões. Não editei: o arquivo é dele (§14). O bloco pronto para
colar está no `config.local.example.json`.

## Fora de escopo, de propósito

`selecionar.py` (o comando que propõe e espera aprovação) é a T14. Esta task
entrega as variáveis e os filtros; o julgamento humano de perfil é trabalho
separado, e o `is_approved` já existe esperando por ele.
