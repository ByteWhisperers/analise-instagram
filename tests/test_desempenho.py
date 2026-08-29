"""Confere as contas de desempenho: engajamento, velocidade, score, crescimento.

So funcao pura, entao nao ha banco nem pasta temporaria aqui.

    .venv\\Scripts\\python.exe tests\\test_desempenho.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import desempenho as d

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


AGORA = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def post(post_id, horas_atras, views=None, curtidas=0, comentarios=0,
         perfil="casa_verde", **extra):
    return {
        "id": post_id, "perfil": perfil,
        "data_utc": (AGORA - timedelta(hours=horas_atras)).isoformat(),
        "visualizacoes": views, "curtidas": curtidas,
        "comentarios": comentarios, "legenda": "post " + post_id,
        **extra,
    }


print("=== mediana aguenta o viral; a media nao ===")
conferir("mediana de lista impar", d.mediana([1, 100, 5]), 5.0)
conferir("mediana de lista par", d.mediana([1, 3, 5, 7]), 4.0)
conferir("ignora ausentes", d.mediana([None, 4, None, 6]), 5.0)
conferir("tudo ausente devolve None", d.mediana([None, None]), None)
conferir("lista vazia devolve None", d.mediana([]), None)
conferir_que("um viral nao desloca a mediana",
             d.mediana([10, 12, 11, 1000000]) == 11.5)

print("\n=== percentil dentro do grupo ===")
conferir("o maior fica perto de 1", d.percentil_no_grupo(100, [1, 2, 3, 4]), 1.0)
conferir("o menor fica em 0.125",
         d.percentil_no_grupo(1, [1, 2, 3, 4]), 0.125)
conferir("grupo todo igual devolve 0.5, nao 1.0",
         d.percentil_no_grupo(5, [5, 5, 5, 5]), 0.5)
conferir("grupo de um so devolve 0.5", d.percentil_no_grupo(9, [3]), 0.5)
conferir("valor ausente devolve None", d.percentil_no_grupo(None, [1, 2]), None)
conferir("grupo vazio devolve None", d.percentil_no_grupo(5, []), None)

print("\n=== razao para a mediana e o numero que se le em voz alta ===")
conferir("o dobro da mediana", d.razao_para_mediana(20, [5, 10, 15]), 2.0)
conferir("mediana zero nao divide por zero",
         d.razao_para_mediana(20, [0, 0, 0]), None)

print("\n=== horas desde a publicacao ===")
conferir("3 horas atras", d.horas_desde(
    (AGORA - timedelta(hours=3)).isoformat(), AGORA), 3.0)
conferir("data no futuro nao vira negativo", d.horas_desde(
    (AGORA + timedelta(hours=5)).isoformat(), AGORA), 0.0)
conferir("data invalida devolve None", d.horas_desde("nao e data", AGORA), None)
conferir("sem data devolve None", d.horas_desde(None, AGORA), None)
conferir_que("sufixo Z do Instagram e aceito",
             d.horas_desde("2026-08-27T09:00:00.000Z", AGORA) == 3.0)

print("\n=== velocidade, com piso de 1h ===")
conferir("300 views em 3h", d.por_hora(300, 3), 100.0)
conferir("post de 6 minutos nao vira foguete: piso de 1h",
         d.por_hora(200, 0.1), 200.0)
conferir("sem valor devolve None", d.por_hora(None, 5), None)

print("\n=== engajamento e A BASE que ele usou ===")
taxa, base = d.taxa_de_engajamento(500, 100, visualizacoes=10000)
conferir("taxa sobre views", round(taxa, 4), 0.06)
conferir("base declarada como views", base, "visualizacoes")

taxa, base = d.taxa_de_engajamento(500, 100, visualizacoes=None, seguidores=20000)
conferir("sem views, cai para seguidores", round(taxa, 4), 0.03)
conferir("e a base muda junto", base, "seguidores")

taxa, base = d.taxa_de_engajamento(500, 100, visualizacoes=0, seguidores=20000)
conferir_que("views zero tambem cai para seguidores", base == "seguidores")

taxa, base = d.taxa_de_engajamento(500, 100)
conferir("sem base nenhuma, devolve None em vez de inventar", taxa, None)

taxa, _ = d.taxa_de_engajamento(500, 100, visualizacoes=10000,
                                compartilhamentos=200, salvamentos=200)
conferir("share e save entram se existirem", round(taxa, 4), 0.1)

taxa, _ = d.taxa_de_engajamento(None, None, visualizacoes=10000)
conferir("sem curtida nem comentario devolve None", taxa, None)

print("\n=== recencia decai por meia-vida ===")
conferir("recem-publicado vale 1.0", d.recencia(0), 1.0)
conferir("48h vale metade", d.recencia(48), 0.5)
conferir("96h vale um quarto", d.recencia(96), 0.25)
conferir_que("nunca fica negativo", d.recencia(10000) >= 0)
conferir("sem hora devolve None", d.recencia(None), None)

print("\n=== sinais crus de um post ===")
s = d.sinais_do_post(post("A", 4, views=40000, curtidas=2000, comentarios=400),
                     agora=AGORA)
conferir("velocidade de views", s["velocidade"], 10000.0)
conferir("velocidade de curtidas", s["velocidade_curtidas"], 500.0)
conferir("engajamento", round(s["engajamento"], 4), 0.06)
conferir("taxa de comentario e sinal proprio", round(s["comentario"], 4), 0.01)

print("\n=== score de oportunidade ===")
# O grupo: quatro posts mornos e um que estourou rapido.
grupo = [
    post("m1", 72, views=10000, curtidas=300, comentarios=20),
    post("m2", 96, views=12000, curtidas=350, comentarios=25),
    post("m3", 120, views=9000, curtidas=280, comentarios=18),
    post("m4", 48, views=11000, curtidas=320, comentarios=22),
]
foguete = post("F", 3, views=90000, curtidas=8000, comentarios=1200)
morno = grupo[0]
todos = grupo + [foguete]

r_foguete = d.score_de_oportunidade(foguete, todos, agora=AGORA)
r_morno = d.score_de_oportunidade(morno, todos, agora=AGORA)

conferir_que("o foguete pontua alto", r_foguete["score"] > 85)
conferir_que("o morno pontua baixo", r_morno["score"] < 50)
conferir_que("e o foguete ganha do morno", r_foguete["score"] > r_morno["score"])
conferir("score em escala 0-100",
         all(0 <= v <= 100 for v in (r_foguete["score"], r_morno["score"])), True)
conferir("os cinco componentes aparecem", sorted(r_foguete["componentes"]),
         ["comentario", "engajamento", "recencia", "velocidade", "visualizacao"])
conferir("o grupo exclui o proprio post", r_foguete["tamanho_do_grupo"], 4)
conferir_que("os sinais crus vem junto, para o numero ser auditavel",
             "sinais" in r_foguete and r_foguete["sinais"]["velocidade"] > 0)

print("\n=== dado ausente nao vira nota baixa ===")
sem_views = [post("s%d" % i, 50 + i, views=None, curtidas=100 * i,
                  comentarios=10 * i) for i in range(1, 5)]
r = d.score_de_oportunidade(sem_views[3], sem_views, agora=AGORA,
                            seguidores=1000,
                            seguidores_do_grupo={"casa_verde": 1000})
conferir_que("ainda pontua sem visualizacoes", r["score"] is not None)
conferir_que("e o peso de visualizacao sai da conta",
             "visualizacao" not in r["componentes"])
conferir_que("mas a velocidade SOBREVIVE, caindo para curtidas/hora",
             "velocidade" in r["componentes"])
conferir("a base da velocidade fica declarada",
         r["sinais"]["base_da_velocidade"], "curtidas")
conferir_que("os pesos restantes foram renormalizados (1.0 - 0.15)",
             abs(sum(r["pesos_usados"].values()) - 0.85) < 1e-9)
conferir("o engajamento caiu para seguidores",
         r["sinais"]["base_do_engajamento"], "seguidores")

print("\n=== sem dado nenhum, o score se recusa a inventar ===")
r = d.score_de_oportunidade({"id": "X", "perfil": "y"}, [], agora=AGORA)
conferir("score None", r["score"], None)
conferir_que("com motivo escrito", "motivo" in r)

print("\n=== mudar o peso re-ranqueia sem recoletar ===")
so_recencia = {"velocidade": 0, "engajamento": 0, "comentario": 0,
               "visualizacao": 0, "recencia": 1}
antigo = d.score_de_oportunidade(morno, todos, agora=AGORA)["score"]
novo = d.score_de_oportunidade(morno, todos, pesos=so_recencia,
                               agora=AGORA)["score"]
conferir_que("o mesmo post muda de nota com pesos diferentes", antigo != novo)

print("\n=== ranquear ordena do melhor para o pior ===")
ranking = d.ranquear(todos, agora=AGORA)
conferir("o foguete e o primeiro", ranking[0]["id"], "F")
conferir("todos entraram", len(ranking), 5)
conferir_que("em ordem decrescente",
             all(ranking[i]["score"] >= ranking[i + 1]["score"]
                 for i in range(len(ranking) - 1)))

print("\n=== crescimento exige duas leituras ===")
uma = [{"medido_em": "2026-08-20T10:00:00", "seguidores": 1000}]
r = d.crescimento(uma)
conferir("com uma leitura, absoluto e None", r["absoluto"], None)
conferir_que("e diz por que", "duas leituras" in r["motivo"])

duas = [
    {"medido_em": "2026-08-20T12:00:00", "seguidores": 1000},
    {"medido_em": "2026-08-27T12:00:00", "seguidores": 1140},
]
r = d.crescimento(duas)
conferir("ganho absoluto", r["absoluto"], 140)
conferir("percentual", round(r["percentual"], 1), 14.0)
conferir("por dia", round(r["por_dia"], 1), 20.0)
conferir("dias entre as leituras", r["dias"], 7.0)

r = d.crescimento(list(reversed(duas)))
conferir("ordem de entrada nao importa", r["absoluto"], 140)

r = d.crescimento([{"medido_em": "2026-08-20T12:00:00", "seguidores": None},
                   {"medido_em": "2026-08-27T12:00:00", "seguidores": 5}])
conferir("leitura sem numero nao conta", r["absoluto"], None)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de desempenho passaram.")
