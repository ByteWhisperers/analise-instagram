"""Confere as contas de metricas.py.

Roda sem instalar nada:
    .venv\\Scripts\\python.exe tests\\test_metricas.py

Nao usa pytest de proposito - seria mais uma dependencia para um projeto que
so precisa conferir umas contas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import metricas

falhas = []


def conferir(descricao, obtido, esperado):
    if obtido == esperado:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
              % (descricao, esperado, obtido))
        falhas.append(descricao)


print("contar_palavras")
conferir("frase simples", metricas.contar_palavras("um dois tres"), 3)
conferir("texto vazio", metricas.contar_palavras(""), 0)
conferir("None nao quebra", metricas.contar_palavras(None), 0)
conferir("pontuacao nao conta", metricas.contar_palavras("Para! Com. Isso?"), 3)

print("\npalavras_por_minuto")
conferir("60 palavras em 60s = 60", metricas.palavras_por_minuto(" ".join(["a"] * 60), 60), 60.0)
conferir("30 palavras em 15s = 120", metricas.palavras_por_minuto(" ".join(["a"] * 30), 15), 120.0)
conferir("duracao zero devolve None", metricas.palavras_por_minuto("a b", 0), None)
conferir("duracao None devolve None", metricas.palavras_por_minuto("a b", None), None)

print("\ncontar_emojis")
conferir("tres emojis", metricas.contar_emojis("massa 🔥🔥 demais 🚀"), 3)
conferir("sem emoji", metricas.contar_emojis("texto puro"), 0)

print("\nprimeira_linha")
conferir("pula linha em branco",
         metricas.primeira_linha("\n\n  O gancho aqui  \nresto"), "O gancho aqui")
conferir("legenda vazia", metricas.primeira_linha(""), "")

print("\nanalisar_legenda")
legenda = "Voce sabia disso?\n\nEntao presta atencao 🔥\n#apostas #bet"
resultado = metricas.analisar_legenda(legenda)
conferir("primeira linha", resultado["primeira_linha"], "Voce sabia disso?")
conferir("linhas nao vazias", resultado["linhas"], 3)
conferir("emojis", resultado["emojis"], 1)
conferir("tem paragrafos", resultado["tem_paragrafos"], True)
conferir("nao termina com pergunta", resultado["termina_com_pergunta"], False)
conferir("termina com pergunta",
         metricas.analisar_legenda("E ai, curtiu?")["termina_com_pergunta"], True)

print("\ndetectar_chamadas")
conferir("acha link na bio",
         metricas.detectar_chamadas("o LINK NA BIO ta la"), {"clicar": ["link na bio"]})
conferir("acha sem acento no texto com acento",
         "comentar" in metricas.detectar_chamadas("comenta aí embaixo"), True)
conferir("varios tipos ao mesmo tempo",
         sorted(metricas.detectar_chamadas("me segue e salva esse post").keys()),
         ["salvar", "seguir"])
conferir("texto sem chamada", metricas.detectar_chamadas("bom dia"), {})

print("\ntaxa_de_engajamento")
conferir("1000+200 em 10000 = 12%",
         metricas.taxa_de_engajamento(1000, 200, 10000), 12.0)
conferir("sem seguidores devolve None",
         metricas.taxa_de_engajamento(10, 2, 0), None)
conferir("comentarios None conta como zero",
         metricas.taxa_de_engajamento(100, None, 1000), 10.0)

print("\ngancho_falado")
segmentos = [
    {"inicio": 0.0, "fim": 1.5, "texto": "Para com isso"},
    {"inicio": 1.6, "fim": 2.9, "texto": "agora"},
    {"inicio": 3.5, "fim": 5.0, "texto": "isso ja e depois"},
]
conferir("so os 3 primeiros segundos",
         metricas.gancho_falado(segmentos), "Para com isso agora")
conferir("lista vazia", metricas.gancho_falado([]), "")
conferir("None nao quebra", metricas.gancho_falado(None), "")

print("\nmedia")
conferir("media simples", metricas.media([2, 4, 6]), 4.0)
conferir("ignora None", metricas.media([2, None, 4]), 3.0)
conferir("tudo None devolve None", metricas.media([None, None]), None)
conferir("lista vazia devolve None", metricas.media([]), None)

print("\ncontar_ocorrencias")
conferir("conta e ordena do maior",
         metricas.contar_ocorrencias([["a", "b"], ["a"], ["a", "b"]]),
         {"a": 3, "b": 2})
conferir("listas vazias", metricas.contar_ocorrencias([[], None]), {})

print("\n" + "=" * 50)
if falhas:
    print("%d TESTE(S) FALHARAM: %s" % (len(falhas), ", ".join(falhas)))
    sys.exit(1)
print("Todos os testes passaram.")
