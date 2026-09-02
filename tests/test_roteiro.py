"""Confere a lista de headlines.

Este modulo existe por um motivo so: numa lista de 50 linhas escrita a mao,
alguem vai digitar o nome do arquivo errado. Sem pareamento explicito, o
sintoma seria um video sair sem headline sem ninguem avisar.

Entao a maior parte destas conferencias e sobre os jeitos de errar uma linha,
nao sobre o caso feliz.

    .venv\\Scripts\\python.exe tests\\test_roteiro.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import roteiro

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


print("=== o roteiro que uma pessoa escreve no Bloco de Notas ===")

TEXTO = """# meu roteiro de setembro
abertura.mp4      | Ninguem te contou isso

receita-bolo.mp4  | O segredo esta no ponto da calda
# a linha abaixo ficou para depois
"""

entradas, problemas = roteiro.ler(TEXTO)

conferir("duas linhas viram duas entradas", len(entradas), 2)
conferir("na ordem do arquivo", [nome for nome, _ in entradas],
         ["abertura.mp4", "receita-bolo.mp4"])
conferir("o texto vem sem os espacos de alinhamento", entradas[0][1],
         "Ninguem te contou isso")
conferir("comentario e linha vazia nao viram entrada nem problema", problemas, [])

conferir("texto vazio nao quebra", roteiro.ler(""), ([], []))
conferir("texto None nao quebra", roteiro.ler(None), ([], []))


print("\n=== o separador ===")

entradas, _ = roteiro.ler("video.mp4 | Voce nao vai acreditar | serio")
conferir("so o primeiro | separa: a headline pode conter barra",
         entradas[0][1], "Voce nao vai acreditar | serio")

entradas, problemas = roteiro.ler("video.mp4 Ninguem te contou")
conferir("linha sem separador nao vira entrada", entradas, [])
conferir("e vira problema com o numero da linha", problemas[0][0], 1)
conferir_que("dizendo o que faltou", "|" in problemas[0][2])

_, problemas = roteiro.ler("| so a headline")
conferir("linha sem nome de arquivo e problema", len(problemas), 1)

_, problemas = roteiro.ler("video.mp4 |")
conferir("linha sem headline e problema", len(problemas), 1)
conferir_que("e o motivo fala de headline", "headline" in problemas[0][2])

_, problemas = roteiro.ler("video.mp4 |    ")
conferir("headline so de espaco tambem e problema", len(problemas), 1)


print("\n=== linha repetida: quase sempre e copiar-e-colar esquecido ===")

entradas, problemas = roteiro.ler(
    "a.mp4 | primeira\nb.mp4 | outra\na.mp4 | segunda")
conferir("a repetida nao entra", len(entradas), 2)
conferir("a primeira e a que vale", dict(entradas)["a.mp4"], "primeira")
conferir("e a repeticao e reclamada", len(problemas), 1)
conferir_que("apontando a linha original", "linha 1" in problemas[0][2])

entradas, problemas = roteiro.ler("a.mp4 | primeira\nA.MOV | segunda")
conferir("repeticao vale mesmo mudando caixa e extensao", len(entradas), 1)
conferir("e tambem e reclamada", len(problemas), 1)


print("\n=== pareamento: o roteiro nao sabe como o arquivo esta no disco ===")

arquivos = ["Abertura.MP4", "receita-bolo.mp4", "sobras.mov"]
entradas, _ = roteiro.ler(
    "abertura      | Texto um\n"
    "RECEITA-BOLO.mp4 | Texto dois\n")

pares, sem_headline, sem_video = roteiro.parear(arquivos, entradas)

conferir("casa sem extensao e sem ligar para caixa",
         pares.get("Abertura.MP4"), "Texto um")
conferir("casa com extensao trocada de caixa",
         pares.get("receita-bolo.mp4"), "Texto dois")
conferir("a chave devolvida e o nome COMO ESTA NO DISCO",
         sorted(pares), ["Abertura.MP4", "receita-bolo.mp4"])
conferir("video que ninguem escreveu fica na lista de sem headline",
         sem_headline, ["sobras.mov"])
conferir("e nada sobrou do outro lado", sem_video, [])


print("\n=== o erro que este modulo existe para pegar ===")

entradas, _ = roteiro.ler("abertua.mp4 | Texto com o nome digitado errado")
pares, sem_headline, sem_video = roteiro.parear(["abertura.mp4"], entradas)

conferir("headline com nome errado nao pareia", pares, {})
conferir("o video aparece como sem headline", sem_headline, ["abertura.mp4"])
conferir("e o nome errado aparece do outro lado", sem_video, ["abertua.mp4"])
conferir_que("os dois lados entram no resumo para o usuario ler",
             len(roteiro.resumir_problemas([], sem_video)) == 1)

linhas = roteiro.resumir_problemas([(3, "x y", "falta o '|'")], ["z.mp4"])
conferir("o resumo junta problema de linha e de pareamento", len(linhas), 2)
conferir_que("citando o numero da linha", "linha 3" in linhas[0])
conferir("sem nada a dizer, o resumo e vazio",
         roteiro.resumir_problemas([], []), [])


print("\n=== pasta sem roteiro nenhum ===")

pares, sem_headline, sem_video = roteiro.parear(["a.mp4", "b.mp4"], [])
conferir("sem roteiro, ninguem pareia", pares, {})
conferir("e todos os videos ficam sem headline", sem_headline, ["a.mp4", "b.mp4"])
conferir("roteiro vazio nao inventa video fantasma", sem_video, [])

pares, sem_headline, _ = roteiro.parear([], [("a.mp4", "Texto")])
conferir("pasta vazia nao pareia nada", pares, {})
conferir("nem inventa video sem headline", sem_headline, [])


print("\n=== quem tem cara de video ===")

conferir_que("mp4 e video", roteiro.e_video("a.mp4"))
conferir_que("MOV maiusculo e video", roteiro.e_video("a.MOV"))
conferir_que("webm e video", roteiro.e_video("a.webm"))
conferir_que("o proprio roteiro nao e video", not roteiro.e_video("roteiro.txt"))
conferir_que("o cache de palavras nao e video",
             not roteiro.e_video("a.palavras.json"))
conferir_que("png nao e video", not roteiro.e_video("logo.png"))
conferir_que("nome vazio nao e video", not roteiro.e_video(""))
conferir_que("None nao e video", not roteiro.e_video(None))

conferir("arquivo sem extensao vira a propria chave",
         roteiro._sem_extensao("abertura"), "abertura")
conferir("caminho completo vira so o nome",
         roteiro._sem_extensao("C:/videos/Abertura.MP4"), "abertura")
conferir("caminho com barra normal tambem",
         roteiro._sem_extensao("videos/b.mp4"), "b")
conferir("extensao desconhecida nao e cortada",
         roteiro._sem_extensao("nota.txt"), "nota.txt")


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes do roteiro passaram.")
