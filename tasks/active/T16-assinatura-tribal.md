# T16 — A assinatura tribal: do dicionário para o sistema probabilístico

**ID:** T16
**Workflow:** BUILD
**Status:** EM VERIFICAÇÃO — código pronto, falta a prova em dado real pago
**Origem:** conversa com o usuário em 31/08/2026, a partir da pergunta
*"a desconstrução do termo é puramente sintática, ou uma tentativa de prever
hashtags relacionadas?"*. A resposta honesta (é 100% sintática) abriu o
desenho inteiro.
**Depende de:** T14 e T15, concluídas

## A tese, nas palavras dele

> "Palavras são sistemas. A estrutura e suas relações podem revelar muito mais
> do que apenas a coletânea de termos. Não tratar isso como um dicionário, mas
> como uma assinatura probabilística."

> "`moto` não identifica uma comunidade. É apenas o território onde várias
> comunidades vivem."

> "Em vez de pensar *quais palavras devo pesquisar*, pense *quais observações
> reduzem mais minha incerteza sobre a identidade do cluster*."

## O que estava errado, medido nos dossiês de 30/08

1. **O cluster coerente virou ruído.** Em `desastresetragedias`,
   `esquilo · grecia · greekliterature · literaturagriega ·
   littératuregrecque · federicogamboa` é tragédia grega em quatro idiomas.
   (`esquilo` em espanhol é **Ésquilo**, o tragediógrafo — não o roedor.)
2. **Três tribos dividindo uma palavra.** Em `tragédiaseresgates`, literatura
   (`sêneca`, `aristófanes`, `teatro`), desastre real (`acidenteaéreo`,
   `br242`, `aviões`) e drama pessoal (`amor`, `autopiedade`) ficaram no mesmo
   nível do ranking.
3. **O ranking estava raso porque a amostra estava rasa.** Abaixo da semente, o
   máximo era 2 perfis. Ordenar por perfis distintos sobre isso é quase ordem
   alfabética.
4. **A legenda estava sendo jogada fora** depois de lida uma vez para votar
   idioma. Toda a gíria, emoji e expressão estavam ali, já pagas.

- [x] **Fase 1A.** `src/lexico.py` — cinco *kinds* a partir da legenda paga
- [x] **Fase 1B.** `migrations/006` + `repos/observacoes.py` — append-only
- [x] **Fase 2.** `src/grafo.py` — Jaccard, comunidades, eixo território↔tribo
- [x] **Fase 3.** `src/assinatura.py` — exclusividade, assinatura, distribuição
- [x] **Fase 4.** `mapeador.proximos_alvos()` — *active discovery*
- [ ] **Prova real** — uma rodada paga, teto US$ 0,10, no tema `tragédias`

## As decisões que a construção obrigou

**A tribo é um conjunto de PERFIS, não de termos.** `P(termo | tribo)` só tem
denominador se a tribo for gente. E uma palavra vive em várias tribos ao mesmo
tempo — rotular termo com uma tribo recriaria o dentro/fora que a T16 existe
para não fazer.

**Suavização add-k (Jeffreys, k=0,5), e não é detalhe.** Sem ela a divisão
estoura, e em amostra pequena denominador zero é o caso comum. No limite, o
termo *mais raro* iria ao topo dos marcadores — o oposto do que se quer. k=0,5
e não 1,0 porque Laplace domina uma tribo de cinco perfis.

**`outros` é um competidor, não sobra.** Concorre com as tribos usando o corpus
de fundo por distribuição. Perfil que só fala genérico faz o fundo ganhar, e a
resposta vira *"nenhuma das tribos que eu conheço"* — diferente de *"a menos
improvável delas"*.

**Média geométrica em vez de produto** na verossimilhança. Sem dividir pelo
número de termos, um perfil com sessenta termos devolveria `{tribo: 1.0}`
sempre — degrau, que é afirmar certeza que a amostra não sustenta.

**Determinismo é requisito.** A propagação de rótulos clássica sorteia ordem e
desempata no acaso. Agrupamento que muda entre duas rodadas iguais não serve de
evidência. Ordem alfabética, empate pelo menor rótulo, teste que roda duas
vezes e compara.

## Um erro corrigido durante a construção

`generalidade()` normalizava pelo número de tribos **em que o termo aparece**.
Com isso um termo presente em 2 de 3 tribos dava 0,9183 contra 1,0 de um
presente nas 3 — quase empate, quando um é claramente mais espalhado. Pior: o
marcador puro caía em `None` e sumia do eixo, sendo o caso que mais interessa.
Normalizando pelo universo, marcador vira 0,0 e entra na conta. Há teste para
os dois.

## Verificação (V1 §10)

**1.013 conferências, zero falhas**, em 16 arquivos. Eram 820 na abertura.

| arquivo | conferências |
|---|---|
| `test_lexico.py` | 41 (novo) |
| `test_grafo.py` | 50 (novo) |
| `test_assinatura.py` | 43 (novo) |
| `test_repos_observacoes.py` | 33 (novo) |
| `test_mapeador.py` | 88 → **114** |

**Os dois critérios de aceitação passam**, e os dois podem falhar de verdade:

1. As três tribos de moto do desenho dele (família / oficina / quebrada) são
   separadas, com `moto` em generalidade 1,0 e `mandrake`, `torque`, `familia`
   em 0,0. `torque` vale >5 na oficina e <1 na quebrada — a mesma palavra, duas
   notas, as duas verdadeiras.
2. `tragédias`, com os termos **reais** do dossiê de 30/08, separa literatura
   de desastre de drama pessoal em três tribos.

**O que ainda não foi provado:** nada disso rodou contra dado novo pago. Os
dois critérios usam dado real de 30/08 remontado à mão, e o cenário de moto é
sintético. A prova pendente é uma rodada com teto US$ 0,10.

**O que explicitamente não foi medido:** se a ordem do *active discovery* é
melhor que a gulosa. Os pesos de `ganho_do_termo` são a primeira aposta, e está
escrito assim no docstring.

## Escopo que ficou de fora, de propósito

- Nenhum LLM e nenhuma dependência nova.
- Nenhum embedding — `pgvector` não está instalado e nada aqui precisa dele.
- `coletar --so-aprovados` continua filtrando por lista de tags aprovadas. Usar
  distância até a assinatura no lugar disso é o passo seguinte, e é outra task.
