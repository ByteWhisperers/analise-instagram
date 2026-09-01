"""Confere o grafo: co-ocorrencia, comunidades e o eixo territorio<->tribo.

O modulo existe porque a lista plana de hashtags nao consegue separar tribo de
territorio. `[MEDIDO 30/08/2026]` No dossie `tragediaseresgates`, literatura
(`sêneca`, `aristófanes`, `teatro`), desastre real (`acidenteaéreo`, `br242`,
`aviões`) e drama pessoal (`amor`, `autopiedade`) ficaram no MESMO nivel do
ranking.

Dois testes aqui sao o criterio de aceitacao da Fase 2 e podem falhar de
verdade: o cenario das tres tribos de moto e o cenario `tragédias`. Se o
agrupamento parar de separa-los, e aqui que tem de doer.

    .venv\\Scripts\\python.exe tests\\test_grafo.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import console
console.preparar()

import grafo

falhas = []


def conferir(descricao, obtido, esperado):
    if obtido == esperado:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
              % (descricao, esperado, obtido))
        falhas.append(descricao)


def conferir_que(descricao, condicao):
    if condicao:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s" % descricao)
        falhas.append(descricao)


def tribo_de(perfis):
    """`{perfil: [termos]}` -> `(por_termo, tribo_do_perfil, quantas_tribos)`."""
    por_termo = grafo.inverter({p: set(t) for p, t in perfis.items()})
    tribos = grafo.tribos_de_perfis(por_termo)
    return por_termo, tribos, len(grafo.agrupar(tribos))


print("=== jaccard: normalizado, e nao contagem crua ===")

conferir("conjuntos iguais dao 1", grafo.jaccard({"a", "b"}, {"a", "b"}), 1.0)
conferir("sem interseccao da 0", grafo.jaccard({"a"}, {"b"}), 0.0)
conferir("metade em comum", grafo.jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
conferir("conjunto vazio nao estoura", grafo.jaccard(set(), {"a"}), 0.0)
conferir("None nao estoura", grafo.jaccard(None, None), 0.0)

# Sem normalizar, o perfil que posta muito se liga forte a todo mundo e vira o
# centro de gravidade do grafo inteiro.
grande = set("abcdefghij")
conferir_que("o conjunto grande NAO domina so por ser grande",
             grafo.jaccard(grande, {"a"}) < grafo.jaccard({"a", "b"},
                                                          {"a", "c"}))


print("\n=== arestas: uma chave por ligacao, com corte ===")

conjuntos = {"x": {"1", "2"}, "y": {"1", "2"}, "z": {"9"}}
ligacoes = grafo.arestas(conjuntos, limiar=0.0)
conferir("o par vem ordenado, uma chave so", sorted(ligacoes), [("x", "y")])
conferir_que("e nao existe a chave invertida", ("y", "x") not in ligacoes)
conferir("quem nao compartilha nada nao vira aresta",
         [p for p in ligacoes if "z" in p], [])
conferir("o limiar corta a ligacao fraca",
         grafo.arestas({"a": {"1", "2", "3", "4"}, "b": {"1", "9", "8", "7"}},
                       limiar=0.5), {})
conferir("sem conjuntos nao estoura", grafo.arestas(None), {})


print("\n=== comunidades: deterministicas, sempre ===")

# A propagacao classica sorteia a ordem e desempata no acaso. Agrupamento que
# muda entre duas rodadas iguais nao pode ser usado como evidencia.
entrada = {("a", "b"): 0.9, ("b", "c"): 0.8, ("d", "e"): 0.7}
primeira = grafo.comunidades(entrada)
conferir("duas execucoes dao o mesmo resultado",
         grafo.comunidades(entrada), primeira)
conferir("os ligados caem juntos", primeira["a"], primeira["c"])
conferir_que("e os desligados ficam separados", primeira["a"] != primeira["d"])

sozinho = grafo.comunidades({}, nos=["ninguem"])
conferir("no isolado fica com o proprio nome — comunidade de um",
         sozinho["ninguem"], "ninguem")
conferir("sem arestas e sem nos nao estoura", grafo.comunidades({}), {})

conferir("agrupar poe os maiores primeiro",
         list(grafo.agrupar({"a": "g1", "b": "g1", "c": "g2"})), ["g1", "g2"])


print("\n=== inverter: a mesma funcao nos dois lados do grafo ===")

conferir("termo->perfis vira perfil->termos",
         grafo.inverter({"moto": {"a", "b"}, "grau": {"a"}}),
         {"a": {"moto", "grau"}, "b": {"moto"}})
conferir("e a volta reconstroi o original",
         grafo.inverter(grafo.inverter({"moto": {"a", "b"}})),
         {"moto": {"a", "b"}})
conferir("None nao estoura", grafo.inverter(None), {})


print("\n=== CRITERIO DE ACEITACAO 1: as tres tribos de moto ===")

# O cenario que o usuario desenhou: `moto` e o territorio onde tres
# comunidades vivem. A tribo A fala de fe e familia, a B de preparacao de
# maquina, a C e a da quebrada. Algumas palavras aparecem nas tres — o que
# muda e a estrutura de co-ocorrencia.
MOTO = {
    "a1": ["moto", "grau", "fe", "familia", "sem cao", "mandou bem", "role"],
    "a2": ["moto", "grau", "fe", "familia", "sem cao", "hoje foi"],
    "a3": ["moto", "fe", "familia", "mandou bem", "hoje foi"],
    "b1": ["moto", "setup", "stage", "dyno", "acerto", "torque"],
    "b2": ["moto", "setup", "dyno", "acerto", "torque", "grau"],
    "b3": ["moto", "setup", "stage", "acerto", "torque"],
    "c1": ["moto", "grau", "role", "mandrake", "quebrada", "menor"],
    "c2": ["moto", "grau", "mandrake", "quebrada", "menor"],
    "c3": ["moto", "role", "mandrake", "quebrada", "menor", "grau"],
}
por_termo, tribos, quantas = tribo_de(MOTO)

conferir("acha exatamente tres tribos", quantas, 3)
conferir_que("a familia fica junta",
             tribos["a1"] == tribos["a2"] == tribos["a3"])
conferir_que("a oficina fica junta",
             tribos["b1"] == tribos["b2"] == tribos["b3"])
conferir_que("a quebrada fica junta",
             tribos["c1"] == tribos["c2"] == tribos["c3"])
conferir_que("e as tres sao diferentes entre si",
             len({tribos["a1"], tribos["b1"], tribos["c1"]}) == 3)


def geral(termo):
    return grafo.generalidade(grafo.espalhamento(por_termo[termo], tribos),
                              quantas)


# "moto" nao identifica uma comunidade. E apenas o territorio onde varias
# comunidades vivem.
conferir("`moto` e territorio puro: aparece nas tres por igual", geral("moto"),
         1.0)
conferir("`mandrake` e marcador: mora numa tribo so", geral("mandrake"), 0.0)
conferir("`torque` e marcador da oficina", geral("torque"), 0.0)
conferir("`familia` e marcador da primeira", geral("familia"), 0.0)
conferir_que("`grau` fica no meio, puxando para uma tribo",
             0.5 < geral("grau") < 1.0)
conferir_que("`role` esta em duas de tres, e fica abaixo de `grau`",
             geral("role") < geral("grau"))


print("\n=== CRITERIO DE ACEITACAO 2: `tragédias` sao tres tribos ===")

# Os termos sao os que apareceram DE VERDADE no dossie de 30/08/2026. O
# agrupamento tem de separar literatura de desastre real — se nao separar, a
# Fase 2 falhou.
TRAGEDIAS = {
    "lit1": ["tragédias", "sêneca", "teatro", "aristófanes", "alfarrabista"],
    "lit2": ["tragédias", "sêneca", "teatro", "bookstagram", "aristófanes"],
    "lit3": ["tragédias", "teatro", "aristófanes", "bookstagram"],
    "des1": ["tragédias", "acidenteaéreo", "aviões", "br242", "notícias"],
    "des2": ["tragédias", "acidenteaéreo", "br242", "notícias",
             "atlasdigitaldedesastresnobrasil"],
    "des3": ["tragédias", "aviões", "br242", "notícias"],
    "dra1": ["tragédias", "amor", "autopiedade", "autocomiseração"],
    "dra2": ["tragédias", "amor", "autopiedade", "caráterdedeus"],
    "dra3": ["tragédias", "autopiedade", "autocomiseração", "caráterdedeus"],
}
t_termo, t_tribos, t_quantas = tribo_de(TRAGEDIAS)

conferir_que("literatura e desastre NAO caem na mesma tribo",
             t_tribos["lit1"] != t_tribos["des1"])
conferir_que("drama pessoal tambem se separa dos dois",
             t_tribos["dra1"] not in (t_tribos["lit1"], t_tribos["des1"]))
conferir_que("os tres perfis de literatura ficam juntos",
             t_tribos["lit1"] == t_tribos["lit2"] == t_tribos["lit3"])
conferir_que("os tres de desastre ficam juntos",
             t_tribos["des1"] == t_tribos["des2"] == t_tribos["des3"])
conferir("e sao tres tribos, nao uma so", t_quantas, 3)

conferir("`tragédias` e o territorio, e nao a tribo",
         grafo.generalidade(grafo.espalhamento(t_termo["tragédias"], t_tribos),
                            t_quantas), 1.0)
conferir("`sêneca` e marcador de uma tribo so",
         grafo.generalidade(grafo.espalhamento(t_termo["sêneca"], t_tribos),
                            t_quantas), 0.0)
conferir("`acidenteaéreo` idem, na outra ponta",
         grafo.generalidade(grafo.espalhamento(t_termo["acidenteaéreo"],
                                               t_tribos), t_quantas), 0.0)


print("\n=== espalhamento e generalidade: os casos de borda ===")

conferir("perfil sem tribo conhecida nao entra na conta",
         grafo.espalhamento({"a", "fantasma"}, {"a": "t1"}), {"t1": 1})
conferir("sem perfis nao estoura", grafo.espalhamento(None, {}), {})

conferir("universo de uma tribo so devolve None — nao ha dispersao",
         grafo.generalidade({"t1": 5}, 1), None)
conferir("contagem vazia devolve None", grafo.generalidade({}, 3), None)
conferir("total ausente devolve None", grafo.generalidade({"t1": 2}, None),
         None)
conferir("tribo com zero perfis e ignorada",
         grafo.generalidade({"t1": 3, "t2": 0}, 2), 0.0)

# A correcao de um erro real: normalizar pelo numero de tribos EM QUE O TERMO
# APARECE fazia 2-de-3 quase empatar com 3-de-3, e mandava o marcador puro
# para None, sumindo do eixo.
em_duas = grafo.generalidade({"t1": 1, "t2": 1}, 3)
em_tres = grafo.generalidade({"t1": 1, "t2": 1, "t3": 1}, 3)
conferir_que("presente em 2 de 3 fica NITIDAMENTE abaixo de 3 de 3",
             em_tres - em_duas > 0.3)
conferir("e presente nas tres por igual da exatamente 1.0", em_tres, 1.0)
conferir_que("a nota nunca passa de 1.0",
             grafo.generalidade({"t1": 1, "t2": 1, "t3": 1, "t4": 1}, 2) <= 1.0)


print("\n=== o perfil magro nao pode casar por acaso ===")

# Um perfil com dois termos casa com qualquer outro: o Jaccard fica alto
# porque o denominador e minusculo, nao porque as contas falem parecido.
magros = {"m1": ["moto", "grau"], "m2": ["moto", "grau"],
          "cheio": ["moto", "grau", "setup", "torque", "dyno", "acerto"]}
por_termo_m = grafo.inverter({p: set(t) for p, t in magros.items()})
conferir_que("com o corte, o perfil magro nao entra no agrupamento",
             "m1" not in grafo.tribos_de_perfis(por_termo_m,
                                                minimo_de_termos=3))
conferir_que("sem o corte, ele entra",
             "m1" in grafo.tribos_de_perfis(por_termo_m, minimo_de_termos=1))


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de grafo passaram.")
