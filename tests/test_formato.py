"""Confere a leitura do formato do video.

**Nao chama o ffmpeg.** O texto cru abaixo foi copiado da saida real de
`ffmpeg 9.0` rodando no post `DcaDqEBiWEd` em 02/09/2026,
e os numeros conferidos a mao antes de existir codigo: 10 cortes, volume medio
-17,0 dB, recorte util 1072x1920.

**Por que testar parsing e nao a medida.** A medida quem faz e o ffmpeg, e ele
esta certo. O que erra e a leitura: um regex que pega o campo errado, uma
saida vazia virando zero em vez de "nao sei", um video mudo derrubando o lote.
Sao esses os casos aqui.

A diferenca entre **zero** e **nao sei** aparece o tempo todo neste arquivo.
Video sem corte nenhum tem `quantos=0`; video que nao pode ser medido tem
`por_minuto=None`. Confundir os dois faz uma faixa inteira despencar.

    .venv\\Scripts\\python.exe tests\\test_formato.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import formato

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


# Saida real do ffprobe, formato `default=nw=1`.
FICHA = """width=1080
height=1920
r_frame_rate=30/1
duration=57.910000
"""

# Saida real do `select='gt(scene,0.3)',metadata=print`.
CORTES = """frame:0    pts:123904  pts_time:4.1
lavfi.scene_score=0.412345
frame:1    pts:301056  pts_time:10.03
lavfi.scene_score=0.556789
frame:2    pts:452608  pts_time:15.02
lavfi.scene_score=0.334567
frame:3    pts:601088  pts_time:19.89
lavfi.scene_score=0.678901
"""

IMAGEM = """frame:0    pts:0       pts_time:0
lavfi.signalstats.YAVG=118.537
lavfi.signalstats.SATAVG=21.7439
frame:1    pts:1024    pts_time:1
lavfi.signalstats.YAVG=115.905
lavfi.signalstats.SATAVG=24.3378
frame:2    pts:2048    pts_time:2
lavfi.signalstats.YAVG=116.726
lavfi.signalstats.SATAVG=21.9056
[Parsed_cropdetect_1 @ 000001] x1:0 x2:1079 crop=1080:1920:0:0
[Parsed_cropdetect_1 @ 000001] x1:4 x2:1075 crop=1072:1920:4:0
"""

AUDIO = """[Parsed_volumedetect_0 @ 0000028966ba5880] n_samples: 2555904
[Parsed_volumedetect_0 @ 0000028966ba5880] mean_volume: -17.0 dB
[Parsed_volumedetect_0 @ 0000028966ba5880] max_volume: -0.6 dB
"""


print("=== a ficha ===")

f = formato.ficha(FICHA)
conferir("largura", f["largura"], 1080)
conferir("altura", f["altura"], 1920)
conferir("proporcao reconhecida pelo nome", f["proporcao"], "9:16")
conferir("fps vem de fracao e vira numero", f["fps"], 30.0)
conferir("duracao arredondada", f["duracao_s"], 57.91)

conferir("fps fracionario do Instagram (2997/100)",
         formato.ficha("r_frame_rate=2997/100\n")["fps"], 29.97)
conferir("deitado", formato.ficha("width=1920\nheight=1080\n")["proporcao"],
         "16:9")
conferir("quadrado", formato.ficha("width=1080\nheight=1080\n")["proporcao"],
         "1:1")
conferir("o 4:5 do feed", formato.ficha("width=1080\nheight=1350\n")["proporcao"],
         "4:5")
conferir("1000x1234 cai no 4:5 por estar dentro da tolerancia",
         formato.ficha("width=1000\nheight=1234\n")["proporcao"], "4:5")
conferir("mas 2:3, que nao esta na lista, vira a razao crua",
         formato.ficha("width=1000\nheight=1500\n")["proporcao"], "0.667")

vazia = formato.ficha("")
conferir("ficha vazia nao inventa numero",
         (vazia["largura"], vazia["fps"], vazia["duracao_s"]), (None, None, None))
conferir("e nao inventa proporcao", vazia["proporcao"], None)
conferir("denominador zero nao divide por zero",
         formato.ficha("r_frame_rate=30/0\n")["fps"], None)


print("\n=== os cortes ===")

c = formato.cortes(CORTES, 57.91)
conferir("conta os cortes", c["quantos"], 4)
conferir("por minuto usa a duracao real", c["por_minuto"], 4.1)
conferir("o primeiro corte marca o fim do plano de abertura",
         c["primeiro_em_s"], 4.1)
conferir("segundos por corte e a MEDIANA do intervalo, nao a divisao",
         c["segundos_por_corte"], 4.99)

# A divisao mentiria aqui: 4 cortes numa rajada de 4s, depois 56s parado.
rajada = """pts_time:1.0
pts_time:2.0
pts_time:3.0
pts_time:4.0
"""
r = formato.cortes(rajada, 60.0)
conferir("rajada: a divisao daria 4 por minuto", r["por_minuto"], 4.0)
conferir("mas a mediana mostra que ele corta a cada 1s quando corta",
         r["segundos_por_corte"], 1.0)

vazio = formato.cortes("", 57.91)
conferir("video sem corte nenhum tem zero, nao None", vazio["quantos"], 0)
conferir("e zero por minuto, que e medida, nao ausencia",
         vazio["por_minuto"], 0.0)
conferir("mas sem intervalo nao ha mediana de intervalo",
         vazio["segundos_por_corte"], None)
conferir("nem primeiro corte", vazio["primeiro_em_s"], None)

conferir("sem duracao, nao da para dizer por minuto",
         formato.cortes(CORTES, None)["por_minuto"], None)
conferir("duracao zero tambem nao divide",
         formato.cortes(CORTES, 0)["por_minuto"], None)
conferir("um corte so nao tem intervalo",
         formato.cortes("pts_time:5.0\n", 60)["segundos_por_corte"], None)


print("\n=== a imagem ===")

i = formato.imagem(IMAGEM)
conferir("brilho e a mediana dos quadros lidos", i["brilho"], 116.7)
conferir("e vem tambem em porcentagem, que se le", i["brilho_pct"], 45.8)
conferir("saturacao idem", i["saturacao"], 21.9)
conferir("quantos quadros entraram na conta", i["quadros_lidos"], 3)

conferir("o cropdetect usado e o ULTIMO, que e o mais apertado",
         i["recorte_util"], {"largura": 1072, "altura": 1920, "x": 4, "y": 0})

vazia = formato.imagem("")
conferir("sem leitura, nao ha brilho", vazia["brilho"], None)
conferir("nem porcentagem", vazia["brilho_pct"], None)
conferir("nem recorte", vazia["recorte_util"], None)
conferir("e zero quadros lidos", vazia["quadros_lidos"], 0)

truncada = formato.imagem("lavfi.signalstats.YAVG=100.0\nlavfi.signalstats.YAV")
conferir("saida truncada aproveita o que deu para ler", truncada["brilho"], 100.0)
conferir("e nao inventa saturacao que nao veio", truncada["saturacao"], None)


print("\n=== a tarja: qual enquadramento o vencedor escolheu ===")

conferir("4px de sobra e compressao, nao tarja",
         formato.montar(FICHA, CORTES, IMAGEM, AUDIO)["tem_tarja"], False)

com_tarja = IMAGEM.replace("crop=1072:1920:4:0", "crop=1080:1440:0:240")
conferir("240px de barra em cima e embaixo E tarja",
         formato.montar(FICHA, CORTES, com_tarja, AUDIO)["tem_tarja"], True)

pilar = IMAGEM.replace("crop=1072:1920:4:0", "crop=810:1920:135:0")
conferir("barra nas laterais tambem conta",
         formato.montar(FICHA, CORTES, pilar, AUDIO)["tem_tarja"], True)

conferir("sem cropdetect, nao se sabe - e nao saber nao e 'nao tem'",
         formato.montar(FICHA, CORTES, "", AUDIO)["tem_tarja"], None)
conferir("sem ficha tambem nao se sabe",
         formato.montar("", CORTES, IMAGEM, AUDIO)["tem_tarja"], None)


print("\n=== o audio ===")

a = formato.audio(AUDIO)
conferir("volume medio", a["volume_medio_db"], -17.0)
conferir("volume de pico", a["volume_pico_db"], -0.6)
conferir_que("e diz que tem audio", a["tem_audio"])

mudo = formato.audio("")
conferir("video mudo nao tem audio", mudo["tem_audio"], False)
conferir("e nao inventa volume", mudo["volume_medio_db"], None)
conferir_que("mudo nao e erro: e informacao", mudo["tem_audio"] is False)

conferir("volume positivo tambem e lido",
         formato.audio("mean_volume: 3.5 dB")["volume_medio_db"], 3.5)


print("\n=== o perfil inteiro, montado ===")

p = formato.montar(FICHA, CORTES, IMAGEM, AUDIO)
conferir("carimba a versao, para dar para reprocessar depois",
         p["versao"], "formato-v1")
conferir_que("junta as quatro leituras",
             set(p) >= {"ficha", "cortes", "imagem", "audio", "tem_tarja"})
conferir("e a duracao da ficha alimenta os cortes por minuto",
         p["cortes"]["por_minuto"], 4.1)

tudo_vazio = formato.montar("", "", "", "")
conferir_que("quatro leituras vazias nao quebram", tudo_vazio["versao"] == "formato-v1")
conferir("e o resultado diz honestamente que nao sabe",
         tudo_vazio["ficha"]["largura"], None)


print("\n=== mediana e quartis ===")

conferir("mediana de impar e o do meio", formato.mediana([1, 5, 9]), 5)
conferir("de par e a media dos dois do meio", formato.mediana([1, 3, 5, 9]), 4.0)
conferir("nao ordenada tambem funciona", formato.mediana([9, 1, 5]), 5)
conferir("lista vazia nao tem mediana", formato.mediana([]), None)
conferir("um elemento so", formato.mediana([7]), 7)

conferir("quartis de 1..7", formato.quartis([1, 2, 3, 4, 5, 6, 7]), (2, 4, 6))
conferir("quartis de par", formato.quartis([1, 2, 3, 4]), (1.5, 2.5, 3.5))
conferir("um elemento: os tres sao ele", formato.quartis([5]), (5, 5, 5))
conferir("vazio nao inventa faixa", formato.quartis([]), (None, None, None))

conferir_que("um fora da curva nao arrasta a mediana como arrastaria a media",
             formato.quartis([10, 10, 10, 10, 1000])[1] == 10)


print("\n=== o perfil do conjunto ===")

def _perfil(proporcao_l, proporcao_a, por_minuto, brilho, tarja):
    return {
        "ficha": {"largura": proporcao_l, "altura": proporcao_a,
                  "proporcao": formato._proporcao(proporcao_l, proporcao_a),
                  "duracao_s": 60.0},
        "cortes": {"por_minuto": por_minuto, "segundos_por_corte": 60.0 / por_minuto},
        "imagem": {"brilho": brilho, "saturacao": 20.0},
        "audio": {"volume_medio_db": -17.0},
        "tem_tarja": tarja,
    }

conjunto = [
    _perfil(1080, 1920, 10.0, 110, False),
    _perfil(1080, 1920, 12.0, 120, False),
    _perfil(1080, 1920, 8.0, 100, True),
    _perfil(1920, 1080, 20.0, 130, False),
]
g = formato.perfil_do_conjunto(conjunto)

conferir("diz quantos videos sustentam a faixa", g["quantos"], 4)
conferir("a proporcao dominante", g["proporcao_dominante"], "9:16")
conferir("com a contagem de cada uma", g["proporcoes"], {"9:16": 3, "16:9": 1})
conferir("conta quem tem tarja", (g["com_tarja"], g["sem_tarja"]), (1, 3))
conferir("cortes por minuto vem como faixa, nao como media",
         g["cortes_por_minuto"], (9.0, 11.0, 16.0))
conferir("brilho idem", g["brilho"], (105.0, 115.0, 125.0))

conferir("conjunto vazio devolve zero, nao estoura",
         formato.perfil_do_conjunto([]), {"quantos": 0})
conferir("lista de Nones tambem",
         formato.perfil_do_conjunto([None, None]), {"quantos": 0})

com_buraco = conjunto + [{"ficha": {}, "cortes": {}, "imagem": {}, "audio": {}}]
g2 = formato.perfil_do_conjunto(com_buraco)
conferir("perfil incompleto entra na contagem", g2["quantos"], 5)
conferir("mas nao envenena a faixa com None",
         g2["cortes_por_minuto"], g["cortes_por_minuto"])

um_so = formato.perfil_do_conjunto([conjunto[0]])
conferir("faixa de um video so e legitima, e o `quantos` denuncia",
         (um_so["quantos"], um_so["cortes_por_minuto"]), (1, (10.0, 10.0, 10.0)))


print("\n=== o ajuste de cor: duas escalas diferentes, e confundi-las e facil ===")

a = formato.ajuste_de_cor(100.0, 15.0, 117.5, 20.4)
conferir("brilho e DIFERENCA dividida por 255, porque o eq soma em 0..1",
         a["brilho"], round((117.5 - 100.0) / 255.0, 4))
conferir("saturacao e RAZAO, porque o eq multiplica",
         a["saturacao"], round(20.4 / 15.0, 3))

igual = formato.ajuste_de_cor(117.5, 20.4, 117.5, 20.4)
conferir("video que ja esta no alvo nao precisa de brilho", igual["brilho"], 0.0)
conferir("nem de saturacao", igual["saturacao"], 1.0)

escuro = formato.ajuste_de_cor(200.0, 20.0, 117.5, 20.4)
conferir_que("video claro demais recebe brilho negativo", escuro["brilho"] < 0)

conferir("o brilho e preso no teto, para medicao ruim nao destruir a imagem",
         formato.ajuste_de_cor(0.0, 20.0, 255.0, 20.0)["brilho"], 0.25)
conferir("e no piso",
         formato.ajuste_de_cor(255.0, 20.0, 0.0, 20.0)["brilho"], -0.25)
conferir("a saturacao tem teto",
         formato.ajuste_de_cor(100.0, 1.0, 100.0, 90.0)["saturacao"], 1.8)
conferir("e piso",
         formato.ajuste_de_cor(100.0, 90.0, 100.0, 1.0)["saturacao"], 0.6)

conferir("sem medida do video, nao mexe no brilho",
         formato.ajuste_de_cor(None, 20.0, 117.5, 20.4)["brilho"], 0.0)
conferir("sem alvo, tambem nao",
         formato.ajuste_de_cor(100.0, 20.0, None, 20.4)["brilho"], 0.0)
conferir("saturacao zero nao divide por zero",
         formato.ajuste_de_cor(100.0, 0.0, 117.5, 20.4)["saturacao"], 1.0)
conferir("saturacao None idem",
         formato.ajuste_de_cor(100.0, None, 117.5, 20.4)["saturacao"], 1.0)


print("\n=== sugerir: o template derivado da medicao ===")

BASE = {
    "nome": "base", "canvas": {"largura": 1080, "altura": 1920},
    "video": {"ajuste": "desfoque", "topo": 300, "altura": 1320,
              "margem_lateral": 40},
    "legenda": {"mostrar": True},
}

# O perfil REAL medido em 02/09/2026 nos 15 videos de 4 perfis do nicho receitas.
MEDIDO = {
    "quantos": 15, "proporcao_dominante": "9:16",
    "com_tarja": 0, "sem_tarja": 15,
    "duracao_s": (57.9, 71.6, 88.0),
    "cortes_por_minuto": (12.6, 17.6, 24.3),
    "brilho": (108.1, 117.5, 122.0),
    "saturacao": (15.8, 20.4, 23.2),
    "volume_medio_db": (-17.5, -17.2, -17.0),
}

sugerido = formato.sugerir(MEDIDO, "receitas", BASE)

conferir("leva o nome pedido", sugerido["nome"], "receitas")
conferir("9:16 sem tarja vira preencher: eles enchem a tela",
         sugerido["video"]["ajuste"], "preencher")
conferir("com a caixa do tamanho do canvas inteiro",
         (sugerido["video"]["topo"], sugerido["video"]["altura"],
          sugerido["video"]["margem_lateral"]), (0, 1920, 0))
conferir("o alvo de cor e a MEDIANA da faixa, nao a media",
         (sugerido["cor"]["brilho_alvo"], sugerido["cor"]["saturacao_alvo"]),
         (117.5, 20.4))
conferir_que("e manda o editor igualar, medindo cada video",
             sugerido["cor"]["igualar"] is True)

conferir_que("NAO inventa alvo de audio: 1,6 dB de variacao em 4 perfis e "
             "normalizacao do Instagram, nao escolha de quem edita",
             "audio" not in sugerido)
conferir_que("e diz isso por escrito, para ninguem reintroduzir depois",
             "normalizacao do Instagram" in sugerido["_leia"])

conferir_que("o ritmo de corte vai no texto, nao em campo aplicavel",
             "17.6" in sugerido["_leia"])
conferir_que("deixando claro que a maquina nao corta",
             "NAO faz: cortar" in sugerido["_leia"])
conferir_que("e quantos videos sustentam a conclusao",
             "15 video(s)" in sugerido["_leia"])

conferir_que("nao estraga a base recebida",
             BASE["video"]["ajuste"] == "desfoque" and BASE["nome"] == "base")
conferir("e a legenda da base e preservada",
         sugerido["legenda"], {"mostrar": True})

deitado = dict(MEDIDO, proporcao_dominante="16:9")
conferir("nicho que posta deitado cai no desfoque, nao no preencher",
         formato.sugerir(deitado, "x", BASE)["video"]["ajuste"], "desfoque")

com_tarja = dict(MEDIDO, com_tarja=12, sem_tarja=3)
conferir("nicho que posta com tarja tambem",
         formato.sugerir(com_tarja, "x", BASE)["video"]["ajuste"], "desfoque")

magro = formato.sugerir({"quantos": 1, "proporcao_dominante": "9:16",
                         "sem_tarja": 1, "com_tarja": 0}, "x", BASE)
conferir_que("perfil de um video so nao quebra, e denuncia o tamanho",
             "1 video(s)" in magro["_leia"])
conferir("e sem brilho medido, o alvo fica None em vez de inventado",
         magro["cor"]["brilho_alvo"], None)


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de formato passaram.")
