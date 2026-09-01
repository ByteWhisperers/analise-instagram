# 007 — Assinatura tribal em vez de lista de tags

**Data:** 31/08/2026
**Status:** aceita
**Contexto:** T16

## O problema

O mapeamento devolvia uma **lista plana de hashtags** ordenada por perfis
distintos. Duas rodadas reais mostraram que essa forma não consegue expressar o
que se quer saber.

No dossiê `tragédiaseresgates`, três comunidades diferentes dividiam a mesma
palavra e ficavam embaralhadas no mesmo nível do ranking:

| tribo | termos |
|---|---|
| literatura / teatro | `sêneca`, `aristófanes`, `teatro`, `alfarrabista` |
| desastre real | `acidenteaéreo`, `br242`, `aviões`, `notícias` |
| drama pessoal | `amor`, `autopiedade`, `autocomiseração` |

E no dossiê `desastresetragedias`, o conjunto `esquilo · grecia ·
greekliterature · literaturagriega · littératuregrecque` — tragédia grega
coerente em quatro idiomas — foi lido como ruído, porque nada no sistema podia
ver que aqueles termos andavam juntos.

A frase que resume o diagnóstico é do usuário:

> "`moto` não identifica uma comunidade. É apenas o território onde várias
> comunidades vivem."

## A decisão

O mapeamento passa a produzir **tribos com assinatura probabilística**, e não
uma lista de termos aprovados.

### 1. A tribo é um conjunto de PERFIS, não de termos

Duas razões, e as duas mandam:

- `P(termo | tribo)` só faz sentido se a tribo for gente. *"Que fração da tribo
  usa esta palavra"* tem denominador; *"a que tribo esta palavra pertence"* não
  tem resposta única.
- Uma palavra vive em várias tribos ao mesmo tempo. Rotular termo com uma tribo
  só recriaria o dentro/fora binário que esta decisão existe para não fazer.

O agrupamento de perfis é só o andaime. O produto é a **matriz termo × tribo**:
a mesma palavra com uma nota em cada tribo. Medido no cenário de teste,
`torque` vale >5 na oficina e <1 na quebrada — as duas coisas verdadeiras ao
mesmo tempo.

### 2. Exclusividade, e não frequência

```
exclusividade(termo, tribo) = P(termo | tribo) / P(termo | fora da tribo)
```

**Frequência elege o território; exclusividade elege a tribo.** `moto` dá 0,94
(aparece em todos por igual); `mandrake` dá 12,25.

Isso exige um **corpus de fundo**, e é o que obrigou a migration 006: sem
observações acumuladas entre rodadas, não há denominador. `niche_terms` da 005
tem `UNIQUE (niche_id, term, kind)` — uma linha por termo, sobrescrita a cada
remapeamento. Ela guarda o resultado julgado, não a evidência bruta.

### 3. A resposta é uma distribuição, com um "não sei" que compete

Classificar um perfil devolve `{tribo: probabilidade}`, nunca um rótulo. E
`outros` não é sobra: concorre usando o corpus de fundo como distribuição.
Perfil que só fala genérico faz o fundo ganhar, e a resposta vira *"nenhuma das
tribos que eu conheço"* — diferente de *"a menos improvável delas"*.

É o mesmo princípio do `None` de `idioma.detectar()` e do `None` de
`grafo.generalidade()`: o terceiro estado é o que impede o sistema de afirmar
com confiança o que não sabe.

### 4. A escolha da próxima chamada muda de pergunta

De *"quais as tags mais fortes?"* para *"qual observação mais reduz a incerteza
sobre a identidade dos clusters?"*. A tag mais forte é quase sempre a do
território, e território é onde todas as tribos se parecem.

Um terço da rodada fica reservado para **explorar a fronteira** — os termos
entre tribos. Sem essa fatia o laço vira exploração pura da tribo mais forte,
que é a versão nova do mesmo defeito guloso que a T15 corrigiu nas sementes.

## O que isso custa

**Nada em dinheiro.** A legenda de cada post já vinha dentro do item pago e
estava sendo descartada depois de lida uma vez para votar idioma. Gíria, emoji,
abreviação, bigrama e menção estavam todos ali. Colher isso custa CPU.

**Custa disco:** `term_observations` é append-only e cresce a cada rodada. Numa
máquina com ~900 MB livres isso importa, e por isso guarda-se a observação
tipada e não o JSON cru do item. `apagar_rodada()` existe para descartar uma
rodada que se descobriu envenenada — append-only não é imutável para sempre.

**Custa complexidade:** três módulos novos e uma tabela. A justificativa da §12
é que isso muda uma decisão real: hoje `coletar --so-aprovados` traz o
território inteiro; com assinatura, o filtro passa a ser distância até o
cluster-alvo. É a diferença entre *"todo mundo que usou #moto"* e *"as pessoas
que dão grau"*.

## Alternativas descartadas

**Embeddings.** Resolveriam similaridade semântica melhor. Descartados porque
`pgvector` não está instalado, no Windows exige compilar com MSVC, e o custo
não se paga enquanto a pergunta for "quem anda com quem" — que é co-ocorrência,
não semântica.

**Um LLM classificando as tribos.** Descartado por decisão registrada do
projeto: nenhum LLM entra na conta. E a co-ocorrência tem uma vantagem que o
LLM não tem aqui — ela lê o que a comunidade escreveu, em vez de o que um
modelo acha que aquela comunidade seria.

**`networkx` para o grafo.** Descartado: dezenas de nós não pagam a
dependência, e instalar é ponto de parada obrigatório (V1 §14). A propagação de
rótulos determinística cabe em quarenta linhas.

**Lista negra de termos genéricos** (`#reels`, `#viral`, `#fyp`). Descartada
porque a exclusividade já os afunda sozinha, sem manutenção e sem alguém ter
que adivinhar a lista. Mesmo raciocínio que afundou a tag de patrocínio na T14.

## Como saber se foi errado

O sinal de que esta decisão não se paga: as tribos encontradas não
corresponderem a nada que um humano reconheça ao olhar os perfis. Se o
agrupamento separar por idioma, por país ou por tamanho de conta em vez de
separar por assunto, o grafo está medindo a coisa errada e o limiar de aresta é
o primeiro suspeito.
