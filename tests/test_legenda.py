"""Confere o gerador de legenda .ass.

Este arquivo nasceu em 01/09/2026, quando o editor foi religado. Ate ali
`legenda.py` nunca tinha sido conferido — e ele e o modulo do editor com a
maior densidade de jeitos silenciosos de errar:

- **a cor.** O template escreve `#FFE100` como no CSS, que e RGB. O `.ass` le
  `&HAABBGGRR` — canal alfa na frente e os componentes ao contrario. Trocar a
  ordem nao quebra nada: so sai a cor errada, e ninguem percebe lendo o codigo.
- **o tempo.** `0:00:02.40`, com centesimo e nao milesimo. Um digito a mais e
  a legenda dessincroniza.
- **o escape.** Chave abre comando no `.ass`. Uma legenda que fale em "{promo}"
  viraria comando e sumiria da tela.
- **o karaoke.** Uma linha por palavra, cada uma acendendo a sua. Errar o
  indice pinta a palavra errada.

    .venv\\Scripts\\python.exe tests\\test_legenda.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import legenda

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


def palavra(texto, inicio, fim):
    return {"palavra": texto, "inicio": inicio, "fim": fim}


print("=== a cor: o CSS e RGB, o .ass e AABBGGRR ===")

conferir("vermelho puro tem o R no fim, nao no comeco",
         legenda.cor_para_ass("#FF0000"), "&H000000FF")
conferir("azul puro tem o B logo apos o alfa",
         legenda.cor_para_ass("#0000FF"), "&H00FF0000")
conferir("verde fica no meio nos dois formatos",
         legenda.cor_para_ass("#00FF00"), "&H0000FF00")
conferir("o amarelo de destaque do template padrao",
         legenda.cor_para_ass("#FFE100"), "&H0000E1FF")
conferir("branco e igual nos dois sentidos - por isso nao serve de teste",
         legenda.cor_para_ass("#FFFFFF"), "&H00FFFFFF")
conferir("preto idem", legenda.cor_para_ass("#000000"), "&H00000000")

conferir("aceita sem o # na frente",
         legenda.cor_para_ass("FF0000"), "&H000000FF")
conferir("aceita minusculo e devolve maiusculo",
         legenda.cor_para_ass("#ffe100"), "&H0000E1FF")
conferir("atalho de 3 digitos vira 6",
         legenda.cor_para_ass("#F00"), "&H000000FF")
conferir("cor ausente cai em branco",
         legenda.cor_para_ass(None), "&H00FFFFFF")
conferir("a opacidade entra no primeiro par",
         legenda.cor_para_ass("#FF0000", 128), "&H800000FF")


print("\n=== o tempo: centesimo, nao milesimo ===")

conferir("zero", legenda._tempo(0), "0:00:00.00")
conferir("dois segundos e quatro decimos", legenda._tempo(2.4), "0:00:02.40")
conferir("o minuto vira campo proprio", legenda._tempo(61.5), "0:01:01.50")
conferir("a hora tambem", legenda._tempo(3661.25), "1:01:01.25")
conferir("negativo e preso em zero: legenda nao comeca antes do video",
         legenda._tempo(-5), "0:00:00.00")
conferir_que("o campo dos segundos tem sempre 5 caracteres",
             len(legenda._tempo(9.5).split(":")[-1]) == 5)


print("\n=== o escape: o que quebraria o filtro ===")

conferir("chave vira parenteses, senao viraria comando do .ass",
         legenda._escapar("{promo}"), "(promo)")
conferir("barra invertida some", legenda._escapar("a\\b"), "ab")
conferir("quebra de linha vira espaco", legenda._escapar("a\nb"), "a b")
conferir("espaco em volta e aparado", legenda._escapar("  oi  "), "oi")
conferir("acento passa intacto - o .ass e UTF-8",
         legenda._escapar("ação"), "ação")
conferir("emoji passa intacto", legenda._escapar("🔥"), "🔥")


print("\n=== agrupar: quantas palavras cabem na tela de uma vez ===")

quatro = [palavra("um", 0.0, 0.5), palavra("dois", 0.5, 1.0),
          palavra("tres", 1.0, 1.5), palavra("quatro", 1.5, 2.0)]

grupos = legenda.agrupar(quatro, por_grupo=3, pausa_que_quebra=10)
conferir("quatro palavras em grupos de tres dao dois grupos", len(grupos), 2)
conferir("o primeiro leva tres", len(grupos[0]), 3)
conferir("o segundo leva a que sobrou", len(grupos[1]), 1)
conferir("nenhuma palavra se perde no caminho",
         sum(len(g) for g in grupos), 4)

grupos = legenda.agrupar(quatro, por_grupo=99, pausa_que_quebra=10)
conferir("grupo grande demais nao quebra nada", len(grupos), 1)

conferir("lista vazia nao vira grupo vazio", legenda.agrupar([]), [])


print("\n=== agrupar: o silencio tambem quebra ===")

com_pausa = [palavra("frase", 0.0, 0.5), palavra("um", 0.5, 1.0),
             palavra("outra", 3.0, 3.5)]  # 2s de silencio

grupos = legenda.agrupar(com_pausa, por_grupo=99, pausa_que_quebra=0.8)
conferir("a pausa longa quebra mesmo cabendo mais palavra", len(grupos), 2)
conferir("e a quebra cai onde o silencio comecou",
         grupos[1][0]["palavra"], "outra")

grupos = legenda.agrupar(com_pausa, por_grupo=99, pausa_que_quebra=5.0)
conferir("com tolerancia maior que o silencio, nao quebra", len(grupos), 1)

colado = [palavra("a", 0.0, 1.0), palavra("b", 1.0, 2.0)]
conferir("silencio zero nunca quebra",
         len(legenda.agrupar(colado, por_grupo=99, pausa_que_quebra=0.0)), 1)


print("\n=== montar: o arquivo inteiro ===")

ESTILO = {
    "fonte": "Arial", "tamanho": 74, "negrito": True,
    "cor": "#FFFFFF", "cor_destaque": "#FFE100", "cor_contorno": "#000000",
    "contorno": 6, "sombra": 0, "destacar_palavra": True,
    "palavras_por_grupo": 3, "pausa_que_quebra": 0.8,
    "posicao_y": 1050, "margem_lateral": 80,
}

texto = legenda.montar(quatro, ESTILO)

conferir_que("tem o cabecalho que o libass exige",
             "[Script Info]" in texto and "[V4+ Styles]" in texto)
conferir_que("declara o canvas do projeto",
             "PlayResX: 1080" in texto and "PlayResY: 1920" in texto)
conferir_que("tem a secao de eventos", "[Events]" in texto)
conferir_que("o estilo se chama Padrao, que e o citado nas falas",
             "Style: Padrao," in texto)
conferir_que("a fonte do template chegou no estilo", ",Arial,74," in texto)
conferir_que("negrito no .ass e -1, nao 1", ",-1,0,0,0," in texto)
conferir_que("a cor do contorno entrou como preto",
             legenda.cor_para_ass("#000000") in texto)
conferir_que("a posicao vertical do template foi usada",
             "\\pos(540,1050)" in texto)
conferir_que("o x e o centro do canvas, nao a margem", "\\pos(540," in texto)

dialogos = [l for l in texto.splitlines() if l.startswith("Dialogue:")]
conferir("com destaque, sai uma linha por palavra", len(dialogos), 4)
conferir_que("a primeira linha comeca em 0:00:00.00",
             dialogos[0].startswith("Dialogue: 0,0:00:00.00,"))


print("\n=== o karaoke: cada linha acende a sua palavra ===")

destaque = legenda.cor_para_ass("#FFE100")
normal = legenda.cor_para_ass("#FFFFFF")

conferir_que("a linha 1 acende 'um'",
             "{\\c%s}um{\\c%s}" % (destaque, normal) in dialogos[0])
conferir_que("e nao acende 'dois' junto",
             "{\\c%s}dois" % destaque not in dialogos[0])
conferir_que("a linha 2 acende 'dois'",
             "{\\c%s}dois{\\c%s}" % (destaque, normal) in dialogos[1])
conferir_que("as tres palavras do grupo aparecem na mesma linha",
             all(p in dialogos[0] for p in ("um", "dois", "tres")))
conferir_que("a quarta palavra nao vaza para o primeiro grupo",
             "quatro" not in dialogos[0])
conferir_que("e a quarta linha e o grupo dela sozinha",
             "quatro" in dialogos[3] and "um " not in dialogos[3])

conferir_que("cada linha tem exatamente um trecho aceso",
             all(linha.count("{\\c%s}" % destaque) == 1 for linha in dialogos))


print("\n=== o buraco entre palavras nao pode piscar ===")

com_buraco = [palavra("a", 0.0, 0.5), palavra("b", 1.2, 1.8)]
linhas = [l for l in legenda.montar(com_buraco, ESTILO).splitlines()
          if l.startswith("Dialogue:")]
conferir_que("a linha de 'a' estica ate 'b' comecar",
             ",0:00:01.20,Padrao" in linhas[0])
conferir_que("a ultima linha termina no fim da propria palavra",
             ",0:00:01.80,Padrao" in linhas[1])


print("\n=== sem destaque: uma linha por grupo ===")

sem = dict(ESTILO, destacar_palavra=False)
linhas = [l for l in legenda.montar(quatro, sem).splitlines()
          if l.startswith("Dialogue:")]
conferir("dois grupos viram duas linhas", len(linhas), 2)
conferir_que("sem nenhum comando de cor no meio", "{\\c" not in linhas[0])
conferir_que("com as tres palavras juntas",
             "um dois tres" in linhas[0])
conferir_que("a linha cobre do inicio da primeira ao fim da ultima",
             linhas[0].startswith("Dialogue: 0,0:00:00.00,0:00:01.50,"))


print("\n=== gravar ===")

destino = Path(__file__).resolve().parent / "_saida_legenda_teste" / "l.ass"
caminho = legenda.gravar(quatro, ESTILO, destino)
conferir("devolve o caminho gravado", caminho, destino)
conferir_que("o arquivo existe de verdade", destino.is_file())
conferir_que("e esta em UTF-8 legivel",
             "[Events]" in destino.read_text(encoding="utf-8"))

conferir("sem palavra nenhuma, nao grava e devolve None",
         legenda.gravar([], ESTILO, destino.with_name("vazio.ass")), None)
conferir_que("e nao deixa arquivo vazio para tras",
             not destino.with_name("vazio.ass").exists())

destino.unlink()
destino.parent.rmdir()


print("\n=== o template pode nao trazer tudo ===")

texto = legenda.montar(quatro, {})
conferir_que("estilo vazio ainda produz arquivo valido",
             "[Events]" in texto and "Dialogue:" in texto)
conferir_que("caindo no centro do canvas quando nao ha posicao_y",
             "\\pos(540,960)" in texto)


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de legenda passaram.")
