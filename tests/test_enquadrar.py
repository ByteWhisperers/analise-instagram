"""Confere a geometria do enquadramento.

**Este e o modulo que erra calado.** Um enquadramento errado nao levanta
excecao: ele produz um video torto 50 segundos depois, e so quem assiste
descobre. Por isso a conta e inteira, em Python, e conferida aqui sem ffmpeg.

Os cinco jeitos de errar que estas conferencias cobrem:

- **usar a razao errada.** So `preencher` usa a MAIOR razao. `encaixar` e
  `desfoque` usam a MENOR: os dois mostram o video INTEIRO, e a diferenca
  entre eles e so o que aparece atras. Trocar as duas nao quebra nada — so
  inverte o resultado. **Foi exatamente o erro cometido na primeira versao**,
  em 02/09/2026: o modo desfoque cortava a frente, anulando a razao de ele
  existir. Pegou-se num ensaio a seco, nao nestes testes — por isso o bloco
  abaixo passou a conferir os tres modos e nao dois.
- **corte fora da imagem.** Deslocar demais pediria ao `crop` um recorte que
  comeca fora da fonte, e isso e erro do ffmpeg no meio do lote.
- **deslocar duas vezes.** Quando ha corte, o deslocamento ja foi gasto la;
  aplicar de novo na posicao moveria o dobro.
- **dimensao impar.** O libx264 exige largura e altura pares. Um pixel impar
  nao da erro bonito: da falha de codificacao.
- **o fundo desfocado herdando zoom.** Se o fundo se mover junto com a frente,
  o deslocamento some visualmente.

    .venv\\Scripts\\python.exe tests\\test_enquadrar.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import enquadrar

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


# A caixa do meme-branco: 1080 de canvas menos 2x60 de margem, altura 980.
CAIXA_MEME = (960, 980)
EM_PE = (1080, 1920)
DEITADO = (1920, 1080)
QUADRADO = (1080, 1080)


print("=== encaixar: cabe inteiro, sobra fundo (o comportamento antigo) ===")

g = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR)
conferir("video em pe encolhe ate a ALTURA da caixa", g["escala"], (550, 980))
conferir("nao ha corte: nada sobrou para cortar", g["corte"], None)
conferir("e ele fica centrado na sobra horizontal", g["posicao"], (205, 0))
conferir_que("largura final menor que a caixa, que e a queixa dele",
             g["tamanho_final"][0] < CAIXA_MEME[0])

g = enquadrar.calcular(*DEITADO, *CAIXA_MEME, enquadrar.ENCAIXAR)
conferir("video deitado encolhe ate a LARGURA da caixa", g["escala"], (960, 540))
conferir("e sobra em cima e embaixo", g["posicao"], (0, 220))

g = enquadrar.calcular(*QUADRADO, *CAIXA_MEME, enquadrar.ENCAIXAR)
conferir("quadrado cabe pela menor dimensao", g["escala"], (960, 960))
conferir("centrado na sobra vertical", g["posicao"], (0, 10))


print("\n=== preencher: enche a caixa e corta o que sobra ===")

g = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER)
conferir("video em pe cresce ate a LARGURA da caixa", g["escala"], (960, 1706))
conferir_que("e o excesso vertical e cortado",
             g["corte"] is not None and g["corte"][:2] == (960, 980))
conferir("o corte fica no meio da altura", g["corte"][2:], (0, 363))
conferir("e o resultado enche a caixa exatamente",
         g["tamanho_final"], CAIXA_MEME)
conferir("entao nao sobra posicao nenhuma", g["posicao"], (0, 0))

g = enquadrar.calcular(*DEITADO, *CAIXA_MEME, enquadrar.PREENCHER)
conferir("video deitado cresce ate a ALTURA", g["escala"], (1742, 980))
conferir("e perde as laterais", g["corte"][:3], (960, 980, 391))


print("\n=== a diferenca entre os dois modos e so a razao ===")

encaixado = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR)
preenchido = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER)
conferir_que("preencher sempre resulta em imagem maior que encaixar",
             preenchido["escala"][0] > encaixado["escala"][0])
conferir_que("encaixar nunca corta", encaixado["corte"] is None)
conferir_que("preencher corta quando a proporcao difere",
             preenchido["corte"] is not None)

# Fonte com a proporcao EXATA da caixa: os dois modos coincidem.
mesma_proporcao = enquadrar.calcular(960, 980, 960, 980, enquadrar.PREENCHER)
conferir("proporcao identica nao sobra nada para cortar",
         mesma_proporcao["corte"], None)
conferir("e enche a caixa", mesma_proporcao["tamanho_final"], (960, 980))


print("\n=== zoom ===")

natural = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR, zoom=1.0)
maior = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR, zoom=1.5)
conferir("zoom 1.0 e o natural", natural["escala"], (550, 980))
conferir("zoom 1.5 amplia meio a meio", maior["escala"], (826, 1470))
conferir_que("e ao passar da caixa, o zoom passa a cortar",
             maior["corte"] is not None)
conferir("cortando de volta para o tamanho da caixa",
         maior["corte"][:2], (826, 980))

menor = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR, zoom=0.5)
conferir("zoom 0.5 reduz pela metade", menor["escala"], (276, 490))
conferir("e sobra mais fundo em volta", menor["posicao"], (342, 245))

encolhido = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER, zoom=0.7)
conferir_que("zoom pequeno em preencher deixa de encher a LARGURA",
             encolhido["tamanho_final"][0] < CAIXA_MEME[0])
conferir_que("mas ainda corta a altura, porque a fonte e muito mais alta",
             encolhido["corte"] is not None)
conferir("e ai sobra fundo nas laterais", encolhido["posicao"], (144, 0))


print("\n=== deslocamento ===")

centro = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER)
acima = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                           deslocar_y=-200)
conferir("deslocar_y negativo sobe o recorte", acima["corte"][3],
         centro["corte"][3] - 200)
conferir("sem mudar o tamanho do recorte", acima["corte"][:2],
         centro["corte"][:2])

abaixo = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                            deslocar_y=200)
conferir("e positivo desce", abaixo["corte"][3], centro["corte"][3] + 200)

# Sem corte, o deslocamento move a POSICAO dentro da caixa.
sem_corte = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR)
movido = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR,
                            deslocar_x=-100)
conferir("sem corte, o deslocamento move a posicao", movido["posicao"][0],
         sem_corte["posicao"][0] - 100)
conferir("e o corte continua inexistente", movido["corte"], None)


print("\n=== o deslocamento e preso nos limites ===")

exagero = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                             deslocar_y=99999)
conferir_que("deslocar alem do fim para no fim, sem estourar",
             exagero["corte"][3] == exagero["escala"][1] - exagero["corte"][1])
conferir_que("e nunca fica negativo", exagero["corte"][3] >= 0)

exagero = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                             deslocar_y=-99999)
conferir("deslocar alem do comeco para em zero", exagero["corte"][3], 0)

exagero = enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR,
                             deslocar_x=99999)
conferir_que("na posicao vale a mesma regra",
             exagero["posicao"][0] <= CAIXA_MEME[0] - exagero["tamanho_final"][0])
conferir_que("e o recorte cabe sempre dentro da imagem escalada",
             all(enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                                    deslocar_x=d, deslocar_y=d)["corte"][2]
                 + enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.PREENCHER,
                                      deslocar_x=d, deslocar_y=d)["corte"][0]
                 <= enquadrar.calcular(*EM_PE, *CAIXA_MEME,
                                       enquadrar.PREENCHER)["escala"][0]
                 for d in (-5000, -100, 0, 100, 5000)))


print("\n=== toda dimensao sai par, senao o libx264 falha ===")

for fonte in [(1080, 1920), (1079, 1921), (333, 777), (1920, 1080), (101, 99)]:
    for modo in enquadrar.AJUSTES:
        for z in (1.0, 1.37, 0.63):
            g = enquadrar.calcular(*fonte, *CAIXA_MEME, modo, zoom=z)
            impares = [n for n in g["escala"] if n % 2]
            if g["corte"]:
                impares += [n for n in g["corte"][:2] if n % 2]
            if impares:
                conferir("par em %s %s zoom=%s" % (fonte, modo, z), impares, [])
                break
conferir_que("nenhuma dimensao impar em 45 combinacoes de fonte, modo e zoom",
             not [d for d in falhas if d.startswith("par em")])

conferir("dimensao minima nunca vai abaixo de 2",
         enquadrar.calcular(1080, 1920, 960, 980, enquadrar.ENCAIXAR,
                            zoom=0.0001)["escala"], (2, 2))


print("\n=== pedido impossivel reclama, e reclama util ===")

for chamada, esperado in [
    (lambda: enquadrar.calcular(0, 1920, 960, 980), "0x1920"),
    (lambda: enquadrar.calcular(1080, 0, 960, 980), "1080x0"),
    (lambda: enquadrar.calcular(-5, 100, 960, 980), "-5x100"),
    (lambda: enquadrar.calcular(1080, 1920, 0, 980), "video.altura"),
    (lambda: enquadrar.calcular(1080, 1920, 960, 0), "video.altura"),
]:
    try:
        chamada()
        conferir_que("reclama de %s" % esperado, False)
    except enquadrar.ErroDeEnquadramento as erro:
        conferir_que("reclama de %s, citando o valor" % esperado,
                     esperado in str(erro))

try:
    enquadrar.calcular(*EM_PE, *CAIXA_MEME, "esticar")
    conferir_que("ajuste inventado reclama", False)
except enquadrar.ErroDeEnquadramento as erro:
    conferir_que("ajuste inventado reclama", True)
    conferir_que("listando os que existem",
                 all(a in str(erro) for a in enquadrar.AJUSTES))

try:
    enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR, zoom=0)
    conferir_que("zoom zero reclama", False)
except enquadrar.ErroDeEnquadramento:
    conferir_que("zoom zero reclama", True)

try:
    enquadrar.calcular(*EM_PE, *CAIXA_MEME, enquadrar.ENCAIXAR, zoom=-2)
    conferir_que("zoom negativo reclama", False)
except enquadrar.ErroDeEnquadramento:
    conferir_que("zoom negativo reclama", True)


print("\n=== ler do template ===")

TEMPLATE = {
    "canvas": {"largura": 1080, "altura": 1920, "fundo": "#FFFFFF", "fps": 30},
    "video": {"topo": 560, "altura": 980, "margem_lateral": 60},
}

g = enquadrar.do_template(TEMPLATE, *EM_PE)
conferir("a caixa e o canvas menos as duas margens", g["escala"], (550, 980))
conferir("template sem `ajuste` cai em encaixar, como sempre foi",
         g["corte"], None)

com_modo = {"canvas": TEMPLATE["canvas"],
            "video": dict(TEMPLATE["video"], ajuste="preencher", zoom=1.2,
                          deslocar_y=-50)}
g = enquadrar.do_template(com_modo, *EM_PE)
conferir_que("o template manda no modo", g["corte"] is not None)
conferir_que("e no zoom", g["escala"][0] > 960)

sem_video = enquadrar.do_template({"canvas": TEMPLATE["canvas"]}, *EM_PE)
conferir("template sem bloco `video` cai nos padroes: margem 60, altura cheia",
         sem_video["escala"], (960, 1706))
conferir("e encaixa sem cortar, centrado na sobra vertical",
         (sem_video["corte"], sem_video["posicao"]), (None, (0, 107)))


print("\n=== a corrente de filtros ===")

g = enquadrar.do_template(TEMPLATE, *EM_PE)
corrente, rotulo = enquadrar.filtros(g, TEMPLATE, "0xFFFFFF")

conferir("encaixar produz tres filtros", len(corrente), 3)
conferir("e sai no rotulo pedido", rotulo, "base")
conferir_que("comeca pelo fundo de cor solida",
             corrente[0] == "color=c=0xFFFFFF:s=1080x1920:r=30[fundo]")
conferir_que("escala sem cortar", corrente[1] == "[0:v]scale=550:980[video]")
conferir_que("e assenta somando a margem e o topo do template",
             corrente[2] == "[fundo][video]overlay=265:560:shortest=1[base]")
conferir_que("com shortest, porque o fundo color e infinito",
             "shortest=1" in corrente[2])

preencher = {"canvas": TEMPLATE["canvas"],
             "video": dict(TEMPLATE["video"], ajuste="preencher")}
corrente, _ = enquadrar.filtros(enquadrar.do_template(preencher, *EM_PE),
                                preencher, "0xFFFFFF")
conferir_que("preencher junta scale e crop no mesmo filtro",
             "scale=960:1706,crop=960:980:0:363" in corrente[1])
conferir_que("e continua com fundo de cor", corrente[0].startswith("color="))


print("\n=== o modo desfoque ===")

desfoque = {"canvas": TEMPLATE["canvas"],
            "video": dict(TEMPLATE["video"], ajuste="desfoque")}
corrente, rotulo = enquadrar.filtros(enquadrar.do_template(desfoque, *EM_PE),
                                     desfoque, "0xFFFFFF")

conferir("desfoque produz quatro filtros", len(corrente), 4)
conferir("comeca dividindo a entrada em duas",
         corrente[0], "[0:v]split=2[paraofundo][parafrente]")
conferir_que("nao ha fundo de cor solida: o fundo e o proprio video",
             not any(f.startswith("color=") for f in corrente))
conferir_que("o fundo enche o CANVAS, nao a caixa",
             "scale=1080:1920" in corrente[1])
conferir_que("e e borrado", "gblur=sigma=20" in corrente[1])
conferir_que("a frente sai da outra ponta do split",
             corrente[2].startswith("[parafrente]scale="))
conferir_que("sem shortest: as duas pontas vem do mesmo arquivo",
             "shortest" not in corrente[3])

conferir_que("fonte ja 9:16 nao ganha crop inutil no fundo",
             "crop=" not in corrente[1])

deitado = enquadrar.filtros(enquadrar.do_template(desfoque, *DEITADO),
                            desfoque, "0xFFFFFF")[0]
conferir_que("fonte deitada ganha crop no fundo, porque sobra imagem",
             "crop=" in deitado[1])

sigma = {"canvas": TEMPLATE["canvas"],
         "video": dict(TEMPLATE["video"], ajuste="desfoque",
                       desfoque_sigma=40, desfoque_escurecer=0.25)}
corrente, _ = enquadrar.filtros(enquadrar.do_template(sigma, *EM_PE), sigma,
                                "0xFFFFFF")
conferir_que("o sigma vem do template", "gblur=sigma=40" in corrente[1])
conferir_que("e escurecer vira eq negativo",
             "eq=brightness=-0.250" in corrente[1])
conferir_que("escurecer zero nao acrescenta filtro nenhum",
             "eq=" not in enquadrar.filtros(
                 enquadrar.do_template(desfoque, *EM_PE), desfoque,
                 "0xFFFFFF")[0][1])


print("\n=== o fundo desfocado nao herda zoom nem deslocamento ===")

com_zoom = {"canvas": TEMPLATE["canvas"],
            "video": dict(TEMPLATE["video"], ajuste="desfoque", zoom=1.8,
                          deslocar_y=-300)}
com, _ = enquadrar.filtros(enquadrar.do_template(com_zoom, *EM_PE), com_zoom,
                           "0xFFFFFF")
sem, _ = enquadrar.filtros(enquadrar.do_template(desfoque, *EM_PE), desfoque,
                           "0xFFFFFF")
conferir("o filtro do fundo e identico com e sem zoom na frente",
         com[1], sem[1])
conferir_que("mas o da frente muda", com[2] != sem[2])


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de enquadramento passaram.")
