# T15 — Consertar o mapeamento: porta única, idioma, ritmo e amostra

**ID:** T15
**Workflow:** BUILD
**Status:** CONCLUÍDA em 30/08/2026
**Origem:** pedido do usuário — *"me descreva melhor como está ocorrendo seu
processo de pesquisa/mapeamento"*. A descrição honesta expôs cinco defeitos;
quatro foram mandados corrigir.
**Depende de:** T14 (o mapeamento), concluída

## Os quatro defeitos, e o que se decidiu

1. **A primeira porta que abre decidia tudo.** `#desastres` rendeu, então
   `#tragedias` nunca era tentada — e `#desastres` é hispanófona. → tentar
   todas as sementes.
2. **Nada percebia idioma**, com `niches.language` vazia desde o primeiro dia.
   → descartar o que for provado de outro idioma. *(O usuário escolheu o filtro
   duro depois de eu apontar o risco. A mitigação: o descartado não some.)*
3. **Ritmo e duração saíam vazios.** → ligar o ritmo, que já estava pago.
4. **Amostra por ordem de chegada**, e a aba da tag vem por recência. → medir e
   expandir por relevância.

- [x] **A.** Todas as sementes na rodada 1
- [x] **B.** `src/idioma.py` + filtro na exploração, no dossiê e no banco
- [x] **C.** `posts.extend()` nas duas chamadas de perfil
- [x] **D.** `mapeador.ranquear_perfis()` no lugar dos dois `[:n]`

## Verificação (V1 §10)

**820 conferências, zero falhas**, em 13 arquivos. Eram 762 na abertura.

**A, C e D funcionaram**, comparando o mesmo tema com o mesmo teto:

| | antes (T14) | depois (T15) |
|---|---|---|
| sementes tentadas | 2 (parou na 1ª que rendeu) | **3** |
| ritmo | `None` | **0,7 dias** |
| mediana de seguidores | 1.435 | **2.293** |
| banda | 404–4.065 | 811–5.647 |

**B funcionou como especificado — e o resultado foi ruim.** `#desastres` (21
perfis) e `#tragedias` (20 perfis), as duas tags mais fortes e mais no tema,
foram descartadas como espanholas. O que sobrou no topo foi ruído: `#esquilo`,
`#greekliterature`, `#chronique`. **O detector não errou:** as legendas dessas
tags são espanholas mesmo. O tema, escrito assim, vive em espanhol no
Instagram.

A mitigação salvou o caso: as 40 descartadas estão no dossiê, com idioma e
votos, e voltam movendo a linha.

## O achado que explica tudo: o acento decide o cluster

`tag_do_termo()` preserva acento desde a T13. Isso tem uma consequência que só
apareceu agora:

| tema digitado | semente | idioma | banda medida |
|---|---|---|---|
| "desastres e tragedias" | `#tragedias` | **es**, descartada | 811–5.647 |
| "tragédias e resgates" | `#tragédias` | **pt**, 13 perfis | 1.484–205.812 |

Com acento vieram `#notícias`, `#acidenteaéreo`,
`#atlasdigitaldedesastresnobrasil`. **`#tragedias` e `#tragédias` são duas
comunidades diferentes, em dois idiomas diferentes** — e a diferença entre
elas, no que o usuário digita, é um acento.

Aparece junto um cluster de tragédia clássica (`#séneca`, `#aristófanes`,
`#teatro`): "tragédia" é polissêmica também em português. É exatamente para
isso que a aprovação é humana.

## Dois defeitos que os próprios testes pegaram

1. **Um dígrafo sozinho decidia o idioma.** `"llama"` virava espanhol com 2
   pontos num limiar de 2 — uma marca com `ll` numa legenda portuguesa bastaria.
   Limiar subiu para 3; só decide sozinho o sinal conclusivo (`ã`, `õ`, `ñ`,
   `¿`, `¡`, `ção`/`ción`).
2. **`que`, `mas` e `como` estavam na lista espanhola** — e são palavras
   portuguesas comuníssimas. `"mas"` contava ponto para o espanhol.

## Custo

US$ 0,0243 + US$ 0,0297 = **US$ 0,054** nas duas rodadas de verificação.

## Fica em aberto, e é decisão sua

O filtro duro é a regra certa para tema bem escrito no idioma alvo, e é a regra
errada para tema cuja comunidade fala outra língua. Três saídas, todas já
disponíveis: `--idioma qualquer` naquela rodada, repescar a linha no dossiê, ou
escrever o tema com o acento certo — que é a mais barata das três.
