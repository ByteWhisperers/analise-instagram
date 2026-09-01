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

# Abaixo disto a aresta nao existe. Sem corte, o grafo vira uma bola so: dois
# perfis que dividem apenas `#reels` ficariam ligados, e a propagacao juntaria
# tudo numa comunidade unica — que e o mesmo que nao agrupar.
#
# **Este numero e uma aposta ate ser medido contra dado real.** O criterio de
# aceitacao da Fase 2 e concreto: no tema `tragédias`, o agrupamento tem de
# separar `sêneca`/`aristófanes`/`teatro` de `acidenteaéreo`/`br242`/`aviões`.
# Se nao separar, e este limiar o primeiro suspeito.
LIMIAR_DE_ARESTA = 0.06

# Quantas passadas a propagacao de rotulos tenta antes de desistir. Ela quase
# sempre estabiliza em menos de cinco; o teto existe para o caso patologico de
# dois rotulos trocando de lugar para sempre.
RODADAS_MAXIMAS = 30


def jaccard(a, b):
    """|a ∩ b| / |a ∪ b|.

    Jaccard e nao contagem crua de compartilhados: sem normalizar, o perfil que
    posta muito se liga forte a todo mundo e vira o centro de gravidade do
    grafo inteiro. O mesmo vale do outro lado — o termo do territorio (`moto`)
    dissolveria as tribos por aparecer em toda parte.
    """
    a, b = set(a or ()), set(b or ())
    if not a or not b:
        return 0.0
    uniao = len(a | b)
    return len(a & b) / uniao if uniao else 0.0


def arestas(conjuntos, limiar=LIMIAR_DE_ARESTA):
    """`{chave: conjunto}` -> `{(a, b): peso}`, com `a < b`.

    Uma funcao para os DOIS grafos que o desenho pede, porque sao a mesma
    operacao com a entrada trocada:

    - grafo linguistico: `{termo: perfis que o usam}`
    - grafo social:      `{perfil: termos que ele usa}`

    O par vem sempre ordenado para a aresta ter uma chave so — `(a, b)` e
    `(b, a)` sao a mesma ligacao, e guardar as duas dobraria o peso de tudo na
    hora de somar.
    """
    chaves = sorted(conjuntos or {})
    achadas = {}

    for i, a in enumerate(chaves):
        for b in chaves[i + 1:]:
            peso = jaccard(conjuntos[a], conjuntos[b])
            if peso >= limiar and peso > 0:
                achadas[(a, b)] = peso
    return achadas


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


def tribos_de_perfis(perfis_por_termo, limiar=LIMIAR_DE_ARESTA,
                     minimo_de_termos=1):
    """O caminho inteiro: `{termo: perfis}` -> `{perfil: tribo}`.

    O atalho que o pipeline usa. Inverte para o grafo social, mede Jaccard
    entre vocabularios, propaga rotulos.

    `minimo_de_termos` descarta o perfil sobre o qual quase nao se observou
    nada. Um perfil com dois termos casa por acaso com qualquer outro: o
    Jaccard fica alto porque o denominador e minusculo, nao porque as duas
    contas falem parecido.
    """
    por_perfil = {perfil: termos
                  for perfil, termos in inverter(perfis_por_termo).items()
                  if len(termos) >= minimo_de_termos}
    return comunidades(arestas(por_perfil, limiar=limiar), nos=por_perfil)
