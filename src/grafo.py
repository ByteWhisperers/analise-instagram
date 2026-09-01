"""A tribo aparece pelo sub-grafo, nunca pela palavra isolada.

**Por que existe:** ate a T15 o mapeamento devolvia uma lista plana de hashtags
ordenada por perfis distintos. Essa forma nao consegue expressar o que se quer
saber.

`[MEDIDO 30/08/2026]` No dossie `tragediaseresgates`, tres tribos dividem uma
palavra e ficam embaralhadas no MESMO nivel do ranking: literatura (`sêneca`,
`aristófanes`, `teatro`), desastre real (`acidenteaéreo`, `br242`, `aviões`) e
drama pessoal (`amor`, `autopiedade`, `autocomiseração`). No dossie
`desastresetragedias`, `esquilo · grecia · greekliterature · literaturagriega ·
littératuregrecque` e um cluster coerente de tragedia grega em quatro idiomas —
e foi lido como ruido. (`esquilo` em espanhol e **Esquilo**, o tragediografo.)

**A decisao central deste modulo: a tribo e um conjunto de PERFIS, nao de
termos.** Duas razoes, e as duas mandam:

1. `P(termo | tribo)` so faz sentido se a tribo for gente. "Que fracao da tribo
   usa esta palavra" e uma pergunta com denominador; "a que tribo esta palavra
   pertence" nao tem resposta unica.
2. Uma palavra vive em varias tribos ao mesmo tempo — `moto` e o territorio
   onde varias comunidades moram, nao a marca de nenhuma. Rotular termo com uma
   tribo so recriaria o dentro/fora que a T16 existe para nao fazer.

Entao: agrupa-se PERFIL pelo vocabulario que ele compartilha, e depois cada
termo ganha uma nota EM CADA tribo (Fase 3). O agrupamento e so o andaime; o
produto e a matriz continua.

Tudo aqui e funcao pura: sem rede, sem banco, sem custo. E deterministico de
proposito — mesmo dado, mesmo agrupamento, sempre. Agrupamento que muda entre
duas rodadas iguais nao serve de evidencia.
"""

import math

# Quantas ligacoes cada perfil guarda: so as `VIZINHOS_POR_NO` mais fortes
# dele. Sem corte o grafo vira uma bola so e a propagacao junta tudo numa
# comunidade unica — que e o mesmo que nao agrupar.
#
# **Vizinhos mais proximos, e nao um limiar. As duas alternativas foram
# medidas e falharam:**
#
# 1. `[MEDIDO 31/08/2026]` **Limiar absoluto (0.06).** As distribuicoes de peso
#    das duas rodadas reais nao tem nada a ver uma com a outra:
#
#        tema             p50      p75      p90      max
#        grau de moto     0.0334   0.0595   0.0940   0.6432
#        tragédias        0.0127   0.0249   0.0470   0.2393
#
#    O mesmo 0.06 e o percentil 75 num e o percentil 93 no outro: "grau de
#    moto" colapsou num bloco de 55 perfis e "tragédias" se estilhacou em 11
#    grupos. A densidade da linguagem muda com o nicho, e nenhum numero
#    absoluto serve aos dois.
#
# 2. **Percentil da distribuicao.** Resolveu o dado real e quebrou o sintetico,
#    e o motivo e de fundo: a fracao certa de arestas depende do TAMANHO das
#    comunidades. Para 3 tribos de 3 perfis o corte certo e o percentil 75;
#    para 10 tribos de 5 entre 58 perfis, o 94. Calibrar o corte exige saber as
#    comunidades, que e o que se esta tentando descobrir. Circular.
#
# Vizinhos mais proximos nao pergunta pela densidade global: cada perfil guarda
# os seus mais parecidos, e pronto. Funciona igual num grafo denso e num ralo.
VIZINHOS_POR_NO = 3

# Nao e tribo quem tem menos que isto. `[MEDIDO 31/08/2026]` Em "tragédias" o
# agrupamento devolveu cinco grupos de UM perfil, e eles nao so poluiam a
# leitura: contavam no total e estragavam a normalizacao da generalidade, que
# divide por `log(total_de_tribos)`.
MINIMO_POR_TRIBO = 3

# Quantas passadas a propagacao de rotulos tenta antes de desistir. Ela quase
# sempre estabiliza em menos de cinco; o teto existe para o caso patologico de
# dois rotulos trocando de lugar para sempre.
RODADAS_MAXIMAS = 30


def jaccard(a, b, pesos=None):
    """Jaccard, opcionalmente **ponderado por raridade**.

        sem pesos:  |a ∩ b| / |a ∪ b|
        com pesos:  Σ w(t) para t em a∩b  /  Σ w(t) para t em a∪b

    Jaccard e nao contagem crua de compartilhados: sem normalizar, o perfil que
    posta muito se liga forte a todo mundo e vira o centro de gravidade do
    grafo inteiro.

    **`pesos` conserta um defeito medido, e e a parte que importa.**
    `[MEDIDO 31/08/2026]` Numa rodada real do tema "grau de moto", `#grau`,
    `#moto` e `#graudemoto` apareciam em quase todos os 68 perfis. Dois perfis
    que dividiam SO o territorio ja ficavam com Jaccard alto, e o agrupamento
    colapsou tudo numa tribo unica — o territorio dissolveu as tribos, que e
    exatamente o que este modulo existe para impedir.

    Com `pesos = idf`, `#moto` (60 de 68 perfis) vale 0,12 e `#grauderua` (6 de
    68) vale 2,42: a similaridade passa a ser dominada pelo que e raro, que e o
    que de fato distingue duas contas.
    """
    a, b = set(a or ()), set(b or ())
    if not a or not b:
        return 0.0

    if pesos is None:
        uniao = len(a | b)
        return len(a & b) / uniao if uniao else 0.0

    peso_da_uniao = sum(pesos.get(t, 1.0) for t in a | b)
    if peso_da_uniao <= 0:
        return 0.0
    return sum(pesos.get(t, 1.0) for t in a & b) / peso_da_uniao


def idf(conjuntos):
    """`{item: log(N / quantos_o_contem)}`. A raridade de cada item.

    N e o numero de conjuntos (perfis, no grafo social). Item presente em todos
    da 0 e some da conta de similaridade; item presente em um da o maximo.

    **E o mesmo principio da exclusividade da Fase 3**, aplicado uma camada
    antes: la ele decide o que E a tribo, aqui decide QUEM esta junto. Aplicar
    so na pontuacao e tarde — o agrupamento ja teria misturado todo mundo.
    """
    total = len(conjuntos or {})
    if not total:
        return {}

    quantos = {}
    for itens in conjuntos.values():
        for item in set(itens or ()):
            quantos[item] = quantos.get(item, 0) + 1

    return {item: math.log(total / n) for item, n in quantos.items()}


def mais_proximos(todas, quantos=VIZINHOS_POR_NO):
    """So as `quantos` ligacoes mais fortes DE CADA no. Uniao dos dois lados.

    Uniao e nao interseccao: se A escolheu B mas B nao escolheu A, a aresta
    fica. O perfil pequeno costuma ser vizinho do grande sem ser recíproco, e
    exigir reciprocidade deixaria a periferia inteira de fora do mapa.

    Deterministico: empate de peso e desfeito pelo nome do vizinho.
    """
    escolhidas = {}
    for no, ligacoes in vizinhos(todas).items():
        ordem = sorted(ligacoes.items(), key=lambda par: (-par[1], par[0]))
        for vizinho, peso in ordem[:quantos]:
            escolhidas[tuple(sorted((no, vizinho)))] = peso
    return escolhidas


def arestas(conjuntos, limiar=None, pesos=None, vizinhos_por_no=VIZINHOS_POR_NO):
    """`{chave: conjunto}` -> `{(a, b): peso}`, com `a < b`.

    Uma funcao para os DOIS grafos que o desenho pede, porque sao a mesma
    operacao com a entrada trocada:

    - grafo linguistico: `{termo: perfis que o usam}`
    - grafo social:      `{perfil: termos que ele usa}`

    O par vem sempre ordenado para a aresta ter uma chave so — `(a, b)` e
    `(b, a)` sao a mesma ligacao, e guardar as duas dobraria o peso de tudo na
    hora de somar.

    `limiar=None` (o normal) corta por vizinhos mais proximos. Um numero
    absoluto so serve quando quem chama sabe a escala — e o teste sabe; o
    mapeamento de um tema novo nao.
    """
    chaves = sorted(conjuntos or {})
    todas = {}

    for i, a in enumerate(chaves):
        for b in chaves[i + 1:]:
            peso = jaccard(conjuntos[a], conjuntos[b], pesos)
            if peso > 0:
                todas[(a, b)] = peso

    if limiar is not None:
        return {par: peso for par, peso in todas.items() if peso >= limiar}
    return mais_proximos(todas, vizinhos_por_no)


def vizinhos(arestas_do_grafo):
    """`{no: {vizinho: peso}}`. Os dois lados de cada aresta."""
    mapa = {}
    for (a, b), peso in (arestas_do_grafo or {}).items():
        mapa.setdefault(a, {})[b] = peso
        mapa.setdefault(b, {})[a] = peso
    return mapa


def comunidades(arestas_do_grafo, nos=(), rodadas=RODADAS_MAXIMAS):
    """Propagacao de rotulos **deterministica**. `{no: rotulo}`.

    Escrita a mao, sem `networkx`: o grafo tem dezenas de nos e a dependencia
    nao se paga (V1 §12, e instalar e ponto de parada em §14).

    A propagacao classica sorteia a ordem dos nos e desempata no acaso — e por
    isso devolve agrupamento diferente a cada execucao. Aqui as duas fontes de
    aleatoriedade sao fechadas:

    - a ordem dos nos e alfabetica, sempre;
    - o empate entre rotulos e resolvido pelo menor rotulo.

    O preco e conhecido: um agrupamento deterministico e um pouco pior que a
    media de varios sorteios. Vale a troca, porque agrupamento que muda entre
    duas rodadas iguais nao pode ser usado como evidencia.

    O no isolado fica com o proprio nome de rotulo — comunidade de um. Isso e
    resposta honesta, e nao falha: perfil que nao divide vocabulario com
    ninguem ainda nao tem tribo conhecida.
    """
    ligacoes = vizinhos(arestas_do_grafo)
    todos = sorted(set(ligacoes) | set(nos or ()))
    rotulo = {no: no for no in todos}

    for _ in range(rodadas):
        mudou = False
        for no in todos:
            peso_por_rotulo = {}
            for vizinho, peso in ligacoes.get(no, {}).items():
                alvo = rotulo[vizinho]
                peso_por_rotulo[alvo] = peso_por_rotulo.get(alvo, 0.0) + peso
            if not peso_por_rotulo:
                continue

            # Maior peso; empate pelo menor rotulo. O `-peso` inverte a ordem
            # sem precisar de `reverse`, que estragaria o desempate.
            melhor = min(peso_por_rotulo.items(), key=lambda par: (-par[1],
                                                                   par[0]))[0]
            if melhor != rotulo[no]:
                rotulo[no] = melhor
                mudou = True
        if not mudou:
            break

    return rotulo


def agrupar(rotulos):
    """`{no: rotulo}` -> `{rotulo: [nos ordenados]}`, os maiores primeiro."""
    grupos = {}
    for no, marca in (rotulos or {}).items():
        grupos.setdefault(marca, []).append(no)

    ordenados = sorted(grupos.items(), key=lambda par: (-len(par[1]), par[0]))
    return {marca: sorted(membros) for marca, membros in ordenados}


def inverter(mapa):
    """`{termo: perfis}` <-> `{perfil: termos}`. A mesma funcao nos dois lados."""
    saida = {}
    for chave, valores in (mapa or {}).items():
        for valor in (valores or ()):
            saida.setdefault(valor, set()).add(chave)
    return saida


# ------------------------------------------------- o eixo territorio <-> tribo


def espalhamento(perfis_do_termo, tribo_do_perfil):
    """`{tribo: quantos perfis daquela tribo usam o termo}`.

    E a linha do termo na matriz que a Fase 3 vai normalizar. Perfil sem tribo
    conhecida nao entra: contar como se fosse uma tribo propria inflaria a
    dispersao de todo termo raro.
    """
    contagem = {}
    for perfil in (perfis_do_termo or ()):
        tribo = (tribo_do_perfil or {}).get(perfil)
        if tribo is None:
            continue
        contagem[tribo] = contagem.get(tribo, 0) + 1
    return contagem


def generalidade(contagem_por_tribo, total_de_tribos):
    """**0.0 = marcador de pertencimento; 1.0 = territorio.** Ou `None`.

    Entropia de Shannon normalizada sobre a distribuicao do termo entre as
    tribos. Este e o eixo que o desenho pede: `mandrake` mora numa tribo so e
    fica em 0; `moto` se espalha por todas e chega a 1.

    **Entropia e nao "em quantas tribos aparece"**, porque a contagem simples
    mente: um termo com 40 perfis numa tribo e 1 em outra apareceria em "duas
    tribos" e seria chamado de territorio, quando e marcador com uma sobra. A
    entropia enxerga a concentracao; a contagem so ve presenca.

    **`total_de_tribos` e obrigatorio, e e a correcao de um erro real.** A
    primeira versao normalizava pelo numero de tribos em que o termo aparece, e
    com isso um termo presente em 2 de 3 tribos dava 0.9183 contra 1.0 de um
    presente nas 3 — quase empate, quando um e claramente mais espalhado que o
    outro. Pior: o marcador puro caia em `None` e sumia do eixo, sendo que ele
    e o caso que mais interessa. Normalizando pelo universo, marcador vira 0.0
    e entra na conta.

    `None` fica so para quando o universo tem uma tribo so: ali nao ha
    dispersao possivel, e afirmar "marcador" sobre isso seria inventar.
    """
    contagem = {k: v for k, v in (contagem_por_tribo or {}).items() if v > 0}
    if not contagem or not total_de_tribos or total_de_tribos < 2:
        return None
    if len(contagem) == 1:
        return 0.0

    total = sum(contagem.values())
    entropia = -sum((n / total) * math.log(n / total)
                    for n in contagem.values())
    return round(min(entropia / math.log(total_de_tribos), 1.0), 4)


def tribos_de_perfis(perfis_por_termo, limiar=None, minimo_de_termos=1,
                     minimo_por_tribo=MINIMO_POR_TRIBO, ponderar=True,
                     vizinhos_por_no=VIZINHOS_POR_NO):
    """O caminho inteiro: `{termo: perfis}` -> `{perfil: tribo}`.

    O atalho que o pipeline usa. Inverte para o grafo social, mede similaridade
    ponderada por raridade entre vocabularios, propaga rotulos.

    `minimo_de_termos` descarta o perfil sobre o qual quase nao se observou
    nada. Um perfil com dois termos casa por acaso com qualquer outro: o
    Jaccard fica alto porque o denominador e minusculo, nao porque as duas
    contas falem parecido.

    `minimo_por_tribo` decide o que E uma tribo. `[MEDIDO 31/08/2026]` Numa
    rodada real do tema "tragédias" o agrupamento devolveu 11 grupos, e CINCO
    deles tinham um perfil so. Grupo de um nao e tribo — e um perfil que nao
    agrupou. Pior: contando como tribo, ele inflava o total e estragava a
    normalizacao da generalidade, que divide por `log(total_de_tribos)`.
    Quem nao alcanca o minimo sai do mapa (`None`), e sair e resposta honesta.

    `ponderar=False` volta ao Jaccard cru. Existe para o teste poder mostrar a
    diferenca, nao para uso normal.
    """
    por_perfil = {perfil: termos
                  for perfil, termos in inverter(perfis_por_termo).items()
                  if len(termos) >= minimo_de_termos}

    pesos = idf(por_perfil) if ponderar else None
    rotulos = comunidades(
        arestas(por_perfil, limiar=limiar, pesos=pesos,
                vizinhos_por_no=vizinhos_por_no),
        nos=por_perfil)

    if minimo_por_tribo > 1:
        tamanho = {}
        for marca in rotulos.values():
            tamanho[marca] = tamanho.get(marca, 0) + 1
        rotulos = {perfil: marca for perfil, marca in rotulos.items()
                   if tamanho[marca] >= minimo_por_tribo}
    return rotulos
