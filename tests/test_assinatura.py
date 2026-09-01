"""Confere a assinatura probabilistica: exclusividade e classificacao.

O modulo existe porque saber que `#grau` pertence ao nicho nao diz nada —
`#grau` tambem pertence as outras comunidades que dividem o territorio `moto`.
Frequencia elege o territorio; exclusividade elege a tribo.

Os testes que mais importam aqui sao os que quebram a matematica: denominador
zero, tribo unica no universo, termo que ninguem de fora usa, e o perfil com
muitos termos que faria a distribuicao virar degrau.

    .venv\\Scripts\\python.exe tests\\test_assinatura.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import console
console.preparar()

import assinatura
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

por_termo = grafo.inverter({p: set(t) for p, t in MOTO.items()})
tribos = grafo.tribos_de_perfis(por_termo)
quantas = len(grafo.agrupar(tribos))
kinds = {t: ("bigrama" if " " in t else "hashtag") for t in por_termo}
mod = assinatura.modelo(por_termo, tribos, kind_do_termo=kinds)
geral = {t: grafo.generalidade(grafo.espalhamento(por_termo[t], tribos),
                               quantas) for t in por_termo}

FAMILIA, OFICINA, QUEBRADA = tribos["a1"], tribos["b1"], tribos["c1"]


print("=== o modelo: contagem com o universo junto ===")

conferir("o universo e todo perfil com tribo", mod["universo"], 9)
conferir("cada tribo guarda seus perfis",
         len(mod["tribos"][QUEBRADA]["perfis"]), 3)
conferir("`moto` foi visto nos nove", mod["total_por_termo"]["moto"], 9)
conferir("modelo sem perfil nenhum nao estoura",
         assinatura.modelo({}, {})["universo"], 0)

# Perfil que o agrupamento nao conhece nao pode entrar na conta pela porta dos
# fundos: ele inflaria o denominador sem pertencer a tribo nenhuma.
sem_tribo = assinatura.modelo({"x": {"fantasma", "a1"}}, {"a1": "t1"})
conferir("perfil sem tribo fica de fora do universo", sem_tribo["universo"], 1)
conferir("e nao conta para o termo", sem_tribo["total_por_termo"]["x"], 1)


print("\n=== probabilidade: fracao de PERFIS, nao de posts ===")

# Perfil que repete `#grau` quarenta vezes nao torna `#grau` mais
# caracteristico da tribo — torna aquele perfil repetitivo.
conferir("termo em todos os perfis da tribo chega perto de 1",
         assinatura.probabilidade(mod, "quebrada", QUEBRADA) > 0.85, True)
conferir("termo que ninguem da tribo usa fica perto de 0",
         assinatura.probabilidade(mod, "torque", QUEBRADA) < 0.15, True)
conferir("tribo inexistente devolve 0, e nao estoura",
         assinatura.probabilidade(mod, "moto", "nao_existe"), 0.0)


print("\n=== exclusividade: o que separa tribo de territorio ===")

conferir_que("`moto` e territorio: exclusividade perto de 1",
             0.8 < assinatura.exclusividade(mod, "moto", QUEBRADA) < 1.2)
conferir_que("`mandrake` e marcador: exclusividade bem acima de 1",
             assinatura.exclusividade(mod, "mandrake", QUEBRADA) > 5)
conferir_que("`torque` na quebrada fica ABAIXO de 1 — e da tribo vizinha",
             assinatura.exclusividade(mod, "torque", QUEBRADA) < 1)
conferir_que("o mesmo `torque` e marcador na oficina",
             assinatura.exclusividade(mod, "torque", OFICINA) > 5)

# A mesma palavra com nota diferente em cada tribo: e a matriz continua que o
# desenho pede, e nao o dentro/fora binario.
conferir_que("`grau` tem nota diferente em cada tribo",
             len({assinatura.exclusividade(mod, "grau", t)
                  for t in (FAMILIA, OFICINA, QUEBRADA)}) == 3)


print("\n=== a suavizacao, e por que ela nao e detalhe ===")

# Sem add-k, `P(termo | fora)` = 0 para todo marcador puro, e a divisao
# estoura. Pior que estourar: com o limite, o termo MAIS RARO iria para o topo
# dos marcadores, que e o oposto do que se quer.
so_um = assinatura.exclusividade(mod, "stage", OFICINA)      # 2 de 3 perfis
todos = assinatura.exclusividade(mod, "torque", OFICINA)     # 3 de 3 perfis
conferir_que("nenhum marcador puro estoura", so_um is not None
             and todos is not None)
conferir_que("e o termo de TODA a tribo vence o de parte dela",
             todos > so_um)

# Universo de uma tribo so: nao ha fora, e qualquer numero seria invencao. E o
# mesmo `None` de `grafo.generalidade`.
sozinha = assinatura.modelo({"x": {"p1", "p2"}}, {"p1": "t1", "p2": "t1"})
conferir("sem tribo de fora, a exclusividade e None",
         assinatura.exclusividade(sozinha, "x", "t1"), None)
conferir("termo que ninguem viu nao estoura",
         assinatura.exclusividade(mod, "inexistente", QUEBRADA) is not None,
         True)


print("\n=== a assinatura: nucleo e marcador respondem coisas diferentes ===")

assinaturas = assinatura.montar_todas(mod, geral)
conferir("uma assinatura por tribo", len(assinaturas), 3)

quebrada = [a for a in assinaturas if a["tribo"] == QUEBRADA][0]
conferir_que("o nucleo comeca pelo territorio",
             quebrada["semantic_core"][0] == "moto")
conferir_que("e o territorio NAO aparece entre os marcadores",
             "moto" not in quebrada["identity_markers"])
conferir_que("os marcadores sao a giria da tribo",
             {"mandrake", "quebrada", "menor"}
             <= set(quebrada["identity_markers"]))
conferir_que("os perfis da tribo vao junto, para conferencia",
             quebrada["perfis"] == ["c1", "c2", "c3"])
conferir_que("cada marcador vem com a evidencia que o sustenta",
             all("exclusividade" in linha for linha in quebrada["_evidencia"]))

familia = [a for a in assinaturas if a["tribo"] == FAMILIA][0]
conferir("o bigrama vai para cooccurrence_patterns",
         familia["cooccurrence_patterns"],
         ["hoje foi", "mandou bem", "sem cao"])
conferir("sem emoji no dado, a secao fica vazia e nao inventa",
         familia["emoji_patterns"], [])
conferir("tribo inexistente devolve None", assinatura.montar(mod, "nada"),
         None)


print("\n=== ortografia: tres detectores explicitos, nada inferido ===")

achados = assinatura.padroes_ortograficos(
    ["graaau", "vc", "br242", "moto", "244", "pq"])
conferir("alongamento", achados["alongamento"], ["graaau"])
conferir("abreviacao", achados["abreviacao"], ["pq", "vc"])
conferir("alfanumerico", achados["alfanumerico"], ["244", "br242"])
conferir_que("palavra comum nao exibe padrao nenhum",
             all("moto" not in lista for lista in achados.values()))
conferir("sem termos nao estoura", assinatura.padroes_ortograficos([]), {})


print("\n=== classificar: distribuicao, nunca rotulo unico ===")

da_quebrada = assinatura.classificar(
    mod, ["moto", "grau", "mandrake", "quebrada", "menor"])
conferir_que("a quebrada ganha", max(da_quebrada, key=da_quebrada.get)
             == QUEBRADA)
conferir_que("a distribuicao soma 1",
             abs(sum(da_quebrada.values()) - 1.0) < 0.001)
conferir_que("`outros` e sempre um competidor presente",
             "outros" in da_quebrada)

da_oficina = assinatura.classificar(mod, ["moto", "setup", "torque", "dyno"])
conferir_que("a oficina ganha com o vocabulario dela",
             max(da_oficina, key=da_oficina.get) == OFICINA)

# `outros` nao e sobra: e o modelo de fundo. Perfil que so fala generico faz o
# fundo ganhar, e a resposta vira "nenhuma das que eu conheco".
so_generico = assinatura.classificar(mod, ["moto"])
conferir_que("perfil que so fala o territorio nao e dado a tribo nenhuma",
             max(so_generico, key=so_generico.get) == "outros")
conferir_que("e as tres tribos empatam entre si",
             len({so_generico[t] for t in (FAMILIA, OFICINA, QUEBRADA)}) == 1)

conferir("perfil sem termo conhecido devolve vazio",
         assinatura.classificar(mod, ["termo_que_ninguem_viu"]), {})
conferir("lista vazia devolve vazio", assinatura.classificar(mod, []), {})
conferir("None devolve vazio", assinatura.classificar(mod, None), {})

# Sem dividir pelo numero de termos, o produto de dezenas de probabilidades
# separa tanto as hipoteses que a distribuicao vira degrau — uma afirmacao de
# certeza que a amostra nao sustenta.
muitos = assinatura.classificar(mod, MOTO["c1"] * 12)
conferir_que("perfil com muitos termos NAO vira certeza de 100%",
             max(muitos.values()) < 0.99)
conferir_que("mas continua acertando a tribo",
             max(muitos, key=muitos.get) == QUEBRADA)


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de assinatura passaram.")
