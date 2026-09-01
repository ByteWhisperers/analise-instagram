"""A assinatura probabilistica da tribo. Nao e dicionario, e distribuicao.

**Por que existe:** saber que `#grau` pertence ao nicho nao diz nada, porque
`#grau` tambem pertence a outras tres comunidades que dividem o territorio
`moto`. O que separa uma tribo da outra nao e a palavra: e o quanto ela e
DESPROPORCIONALMENTE dela.

A conta central e a exclusividade:

    exclusividade(termo, tribo) = P(termo | tribo) / P(termo | fora da tribo)

Um termo que 80% da tribo usa e que 2% de fora usa tem exclusividade 40. Um
termo que todo mundo usa tem exclusividade ~1, por mais frequente que seja
dentro. **Frequencia elege o territorio; exclusividade elege a tribo.**

**O `outros` nao e sobra, e um modelo.** Ao classificar um perfil, ele concorre
com as tribos usando o corpus de fundo como distribuicao. Se o perfil so fala
generico, o fundo ganha, e a resposta e "isto nao e nenhuma das tribos que eu
conheco" — que e diferente de "e a menos improvavel delas". Conhecer as tribos
concorrentes e o universo importa tanto quanto conhecer a tribo.

Tudo aqui e funcao pura: sem rede, sem banco, sem custo.
"""

import math

# Add-k de Jeffreys. **Sem suavizacao a formula estoura**, e o estouro nao e
# raro: numa amostra pequena o denominador zero e o caso comum, e ali a divisao
# mandaria o termo MAIS RARO para o topo dos marcadores identitarios —
# exatamente o oposto do que se quer.
#
# 0.5 e nao 1.0: com 1.0 (Laplace) a suavizacao domina numa tribo de cinco
# perfis, e todo termo converge para exclusividade 1. Meio conta como "meia
# observacao de cada lado", que e o que se sabe antes de olhar.
SUAVIZACAO = 0.5

# Abaixo disto o termo nao entra na assinatura. 1.0 seria "tao comum dentro
# quanto fora"; 1.5 exige meia vez mais dentro para a linha valer a tinta.
EXCLUSIVIDADE_MINIMA = 1.5

# Quantos termos cada secao da assinatura carrega. Assinatura nao e despejo do
# vocabulario: e o retrato curto que da para ler.
TAMANHO_DA_SECAO = 12


def modelo(perfis_por_termo, tribo_do_perfil, kind_do_termo=None):
    """A contagem que todas as contas deste modulo consomem.

    Separado de proposito das funcoes de nota: montar isto varre o dado inteiro
    uma vez, e `exclusividade` e chamada milhares de vezes. Recalcular por
    chamada transformaria a Fase 3 no gargalo.

    Devolve tribos com seus perfis e contagens, e o universo — porque contagem
    sem o universo que a produziu nao vira probabilidade.
    """
    tribo_do_perfil = tribo_do_perfil or {}
    tribos = {}
    for perfil, tribo in tribo_do_perfil.items():
        tribos.setdefault(tribo, {"perfis": set(), "termos": {}})
        tribos[tribo]["perfis"].add(perfil)

    universo = set(tribo_do_perfil)
    total_por_termo = {}

    for termo, perfis in (perfis_por_termo or {}).items():
        conhecidos = set(perfis or ()) & universo
        if not conhecidos:
            continue
        total_por_termo[termo] = len(conhecidos)
        for perfil in conhecidos:
            dados = tribos[tribo_do_perfil[perfil]]
            dados["termos"][termo] = dados["termos"].get(termo, 0) + 1

    return {
        "tribos": tribos,
        "universo": len(universo),
        "total_por_termo": total_por_termo,
        "kind_do_termo": dict(kind_do_termo or {}),
    }


def _dentro_e_fora(mod, termo, tribo):
    """`(n_dentro, N_tribo, n_fora, N_fora)`. A materia-prima das duas contas."""
    dados = mod["tribos"].get(tribo)
    if not dados:
        return 0, 0, 0, 0

    n_tribo = len(dados["perfis"])
    dentro = dados["termos"].get(termo, 0)
    fora = mod["total_por_termo"].get(termo, 0) - dentro
    return dentro, n_tribo, fora, mod["universo"] - n_tribo


def probabilidade(mod, termo, tribo, suavizacao=SUAVIZACAO):
    """`P(termo | tribo)`: que fracao da tribo usa este termo.

    Fracao de PERFIS e nao de posts. Um perfil que repete `#grau` quarenta
    vezes nao torna `#grau` mais caracteristico da tribo — torna aquele perfil
    repetitivo. E a mesma razao pela qual `ranquear_termos` conta perfis
    distintos desde a T14.
    """
    dentro, n_tribo, _, _ = _dentro_e_fora(mod, termo, tribo)
    if not n_tribo:
        return 0.0
    return (dentro + suavizacao) / (n_tribo + 2 * suavizacao)


def exclusividade(mod, termo, tribo, suavizacao=SUAVIZACAO):
    """`P(termo | tribo) / P(termo | fora)`. Acima de 1 e desproporcional.

    Devolve `None` quando nao ha fora nenhum — universo de uma tribo so. Ali a
    razao seria uma divisao por si mesma, e qualquer numero devolvido seria
    invencao. E o mesmo `None` de `grafo.generalidade`.
    """
    dentro, n_tribo, fora, n_fora = _dentro_e_fora(mod, termo, tribo)
    if not n_tribo or not n_fora:
        return None

    p_dentro = (dentro + suavizacao) / (n_tribo + 2 * suavizacao)
    p_fora = (fora + suavizacao) / (n_fora + 2 * suavizacao)
    return round(p_dentro / p_fora, 4)


# ---------------------------------------------------------------- ortografia


def _alongada(termo):
    """`graaau`: a mesma letra tres vezes seguidas."""
    seguidas, anterior = 1, None
    for letra in termo:
        seguidas = seguidas + 1 if letra == anterior else 1
        if seguidas >= 3:
            return True
        anterior = letra
    return False


def _abreviada(termo):
    """`vc`, `pq`, `blz`: curta e quase sem vogal."""
    if not (2 <= len(termo) <= 4) or not termo.isalpha():
        return False
    vogais = sum(1 for letra in termo if letra in "aeiouáéíóúâêôãõà")
    return vogais <= len(termo) // 3


def _alfanumerica(termo):
    """`br242`, `244`, `93play`: numero misturado com letra, ou numero puro."""
    return any(c.isdigit() for c in termo)


PADROES = (("alongamento", _alongada),
           ("abreviacao", _abreviada),
           ("alfanumerico", _alfanumerica))


def padroes_ortograficos(termos):
    """`{padrao: [termos que o exibem]}`, so com os padroes que apareceram.

    Tres detectores explicitos, e nada de "estilo" inferido. Cada linha aponta
    para os termos concretos que a sustentam: padrao que nao da para conferir
    no dado nao serve de evidencia.
    """
    achado = {}
    for termo in (termos or ()):
        for nome, detector in PADROES:
            if detector(termo):
                achado.setdefault(nome, []).append(termo)
    return {nome: sorted(set(lista)) for nome, lista in achado.items()}


# ----------------------------------------------------------- a assinatura


def _por_kind(mod, termos, kind):
    return [t for t in termos if mod["kind_do_termo"].get(t) == kind]


def montar(mod, tribo, generalidade_do_termo=None, tamanho=TAMANHO_DA_SECAO,
           exclusividade_minima=EXCLUSIVIDADE_MINIMA):
    """O retrato de uma tribo, pronto para ler e para conferir.

    `semantic_core` e `identity_markers` respondem perguntas diferentes e sao
    escolhidos por criterios diferentes, e essa e a ideia inteira:

    - **nucleo semantico** — o que a tribo mais usa E que e do territorio.
      Responde "de que assunto isto aqui e".
    - **marcadores de pertencimento** — o que ela usa desproporcionalmente.
      Responde "quem sao estes, e nao os vizinhos".

    Sem `generalidade_do_termo`, o nucleo cai para "o mais frequente da tribo"
    — util, mas nao sabe separar territorio de marca. O eixo vem do
    `grafo.generalidade` e passa por aqui de fora para este modulo nao precisar
    do grafo inteiro.
    """
    dados = mod["tribos"].get(tribo)
    if not dados:
        return None

    geral = generalidade_do_termo or {}
    notas = []
    for termo in dados["termos"]:
        notas.append({
            "termo": termo,
            "kind": mod["kind_do_termo"].get(termo),
            "perfis": dados["termos"][termo],
            "p_na_tribo": round(probabilidade(mod, termo, tribo), 4),
            "exclusividade": exclusividade(mod, termo, tribo),
            "generalidade": geral.get(termo),
        })

    # Nucleo: frequente na tribo e espalhado pelo universo. Desempate pela
    # generalidade alta — entre dois igualmente frequentes, o mais territorial
    # descreve melhor onde a tribo mora.
    nucleo = sorted(notas, key=lambda l: (-l["p_na_tribo"],
                                          -(l["generalidade"] or 0),
                                          l["termo"]))

    # Marcadores: desproporcionais. Exclusividade None (universo de uma tribo)
    # nao vira zero — sai da lista, porque nao ha o que afirmar.
    marcadores = sorted(
        (l for l in notas
         if l["exclusividade"] is not None
         and l["exclusividade"] >= exclusividade_minima),
        key=lambda l: (-l["exclusividade"], -l["perfis"], l["termo"]))

    nomes_dos_marcadores = [l["termo"] for l in marcadores[:tamanho]]

    return {
        "tribo": tribo,
        "perfis": sorted(dados["perfis"]),
        "semantic_core": [l["termo"] for l in nucleo[:tamanho]],
        "identity_markers": nomes_dos_marcadores,
        "hashtag_patterns": _por_kind(mod, nomes_dos_marcadores, "hashtag"),
        "emoji_patterns": _por_kind(mod, nomes_dos_marcadores, "emoji"),
        "cooccurrence_patterns": _por_kind(mod, nomes_dos_marcadores,
                                           "bigrama"),
        "contextual_entities": _por_kind(mod, nomes_dos_marcadores, "mencao"),
        "orthographic_patterns": padroes_ortograficos(nomes_dos_marcadores),
        "_evidencia": marcadores[:tamanho],
    }


def montar_todas(mod, generalidade_do_termo=None, **kwargs):
    """Uma assinatura por tribo, da maior para a menor."""
    ordem = sorted(mod["tribos"],
                   key=lambda t: (-len(mod["tribos"][t]["perfis"]), t))
    return [montar(mod, tribo, generalidade_do_termo, **kwargs)
            for tribo in ordem]


# -------------------------------------------------------------- classificar


def classificar(mod, termos, suavizacao=SUAVIZACAO):
    """Termos de um perfil -> `{tribo: probabilidade}`, somando 1.

    Nunca um rotulo unico. A resposta e uma distribuicao porque a pergunta
    admite duvida, e esconder a duvida atras do argmax e o jeito mais rapido de
    o sistema mentir com confianca.

    **`outros` e um competidor de verdade**, com o corpus de fundo por
    distribuicao. Perfil que so fala generico faz o fundo ganhar, e a resposta
    vira "nenhuma das tribos que eu conheco" — diferente de "a menos improvavel
    delas".

    **A verossimilhanca e dividida pelo numero de termos** (media geometrica em
    vez de produto). Sem isso, um perfil com sessenta termos devolveria
    `{tribo: 1.0}` sempre: o produto de sessenta probabilidades separa tanto as
    hipoteses que a distribuicao vira degrau. O degrau seria uma afirmacao de
    certeza que a amostra nao sustenta.
    """
    termos = [t for t in (termos or ()) if t in mod["total_por_termo"]]
    if not termos or not mod["tribos"]:
        return {}

    universo = mod["universo"] or 1
    pontos = {}

    for tribo in mod["tribos"]:
        soma = sum(math.log(probabilidade(mod, termo, tribo, suavizacao))
                   for termo in termos)
        pontos[tribo] = soma / len(termos)

    fundo = sum(math.log((mod["total_por_termo"][termo] + suavizacao)
                         / (universo + 2 * suavizacao))
                for termo in termos)
    pontos["outros"] = fundo / len(termos)

    maior = max(pontos.values())
    pesos = {nome: math.exp(valor - maior) for nome, valor in pontos.items()}
    total = sum(pesos.values())
    return {nome: round(peso / total, 4)
            for nome, peso in sorted(pesos.items(),
                                     key=lambda par: (-par[1], par[0]))}
