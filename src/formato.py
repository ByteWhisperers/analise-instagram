"""Como o video e construido: ritmo de corte, enquadramento, luz e volume.

**Por que existe.** Ate 02/09/2026 o banco sabia muito sobre a LINGUAGEM do
nicho — 27.054 observacoes de termos, tribos com assinatura — e absolutamente
nada sobre o VIDEO. `transcripts` vazia, `content_analyses` vazia. O sistema
conseguia dizer que palavra a tribo usa, e nao conseguia dizer se ela corta a
cada 3 segundos ou a cada 15.

Isso impedia a promessa do projeto inteiro, que e "descobrir **como** os posts
que funcionam sao construidos". Construcao nao esta na legenda.

O ffmpeg le video, nao so escreve. Este modulo pega o texto cru que os
leitores de `midia.py` devolvem e transforma em numero comparavel.

**So funcao pura.** Entra texto, sai dicionario. Nao chama ffmpeg, nao abre
arquivo, nao consulta banco — o que permite conferir o parsing dos casos
chatos (saida vazia, truncada, video mudo) sem ter um mp4 na maquina.

**O que ele NAO faz:** julgar. Ele nao diz que 10 cortes por minuto e bom.
Diz que este video corta 10 vezes por minuto e que a faixa dos medidos vai de
tanto a tanto. Julgamento e de quem le.
"""

import re

# O que o produtor desta analise se chama, para `content_analyses.model`. A
# tabela ja guarda quem produziu — ver o cabecalho de `repos/analyses.py`.
PRODUTOR = "ffmpeg"
VERSAO = "formato-v1"

_CENA = re.compile(r"pts_time:([0-9.]+)")
_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")
_SATAVG = re.compile(r"lavfi\.signalstats\.SATAVG=([0-9.]+)")
_CROP = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
_VOLUME_MEDIO = re.compile(r"mean_volume:\s*(-?[0-9.]+) dB")
_VOLUME_PICO = re.compile(r"max_volume:\s*(-?[0-9.]+) dB")
_LARGURA = re.compile(r"^width=(\d+)", re.M)
_ALTURA = re.compile(r"^height=(\d+)", re.M)
_FPS = re.compile(r"^r_frame_rate=(\d+)/(\d+)", re.M)
_DURACAO = re.compile(r"^duration=([0-9.]+)", re.M)


# --------------------------------------------------------------- utilidades


def _numeros(padrao, texto):
    return [float(m) for m in padrao.findall(texto or "")]


def mediana(valores):
    if not valores:
        return None
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2.0


def quartis(valores):
    """`(q1, mediana, q3)`. Faixa, nao media.

    Media de 15 videos esconde que dois sao fora da curva. A faixa mostra onde
    a maioria vive e deixa o fora da curva visivel em vez de diluido.
    """
    if not valores:
        return (None, None, None)
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    baixo = ordenados[:meio]
    alto = ordenados[meio + 1:] if len(ordenados) % 2 else ordenados[meio:]
    return (mediana(baixo) if baixo else ordenados[0],
            mediana(ordenados),
            mediana(alto) if alto else ordenados[-1])


def _proporcao(largura, altura):
    """'9:16', '16:9', '1:1' ou a razao crua quando nao bate com as conhecidas."""
    if not largura or not altura:
        return None
    razao = largura / float(altura)
    for nome, valor in (("9:16", 0.5625), ("1:1", 1.0), ("4:5", 0.8),
                        ("16:9", 1.7778), ("4:3", 1.3333)):
        if abs(razao - valor) < 0.02:
            return nome
    return "%.3f" % razao


# ------------------------------------------------------------------ leitura


def ficha(texto):
    """Saida do ffprobe -> dimensoes, fps, duracao e proporcao."""
    largura = int(_LARGURA.search(texto).group(1)) if _LARGURA.search(texto) else None
    altura = int(_ALTURA.search(texto).group(1)) if _ALTURA.search(texto) else None
    duracao = float(_DURACAO.search(texto).group(1)) if _DURACAO.search(texto) else None

    fps = None
    achado = _FPS.search(texto or "")
    if achado:
        numerador, denominador = int(achado.group(1)), int(achado.group(2))
        fps = round(numerador / float(denominador), 2) if denominador else None

    return {
        "largura": largura,
        "altura": altura,
        "proporcao": _proporcao(largura, altura),
        "fps": fps,
        "duracao_s": round(duracao, 2) if duracao else None,
    }


def cortes(texto, duracao_s=None):
    """Saida do `select=scene` -> quantos cortes, com que frequencia.

    `segundos_por_corte` e a **mediana do intervalo** entre cortes, nao a
    duracao dividida pelo numero. A divisao mente quando o video tem uma
    rajada de cortes no comeco e depois fica parado — e isso e comum em
    receita, justamente onde a rajada e o gancho.
    """
    tempos = _numeros(_CENA, texto)
    intervalos = [b - a for a, b in zip(tempos, tempos[1:])]

    por_minuto = None
    if duracao_s and duracao_s > 0:
        por_minuto = round(len(tempos) * 60.0 / duracao_s, 1)

    return {
        "quantos": len(tempos),
        "por_minuto": por_minuto,
        "segundos_por_corte": round(mediana(intervalos), 2) if intervalos else None,
        "primeiro_em_s": round(tempos[0], 2) if tempos else None,
    }


def imagem(texto):
    """Saida do `signalstats`+`cropdetect` -> luz, cor e tarja.

    `YAVG` vai de 0 a 255 e e a luminancia media; `SATAVG` e a saturacao. Os
    dois sao devolvidos crus **e** em porcentagem, porque 117 nao diz nada a
    quem le e 46% diz.
    """
    luz = _numeros(_YAVG, texto)
    cor = _numeros(_SATAVG, texto)

    tarja = None
    achados = _CROP.findall(texto or "")
    if achados:
        # O ultimo e o mais confiavel: o cropdetect vai apertando o recorte
        # conforme ve mais quadros.
        largura, altura, x, y = (int(n) for n in achados[-1])
        tarja = {"largura": largura, "altura": altura, "x": x, "y": y}

    return {
        "brilho": round(mediana(luz), 1) if luz else None,
        "brilho_pct": round(100 * mediana(luz) / 255.0, 1) if luz else None,
        "saturacao": round(mediana(cor), 1) if cor else None,
        "quadros_lidos": len(luz),
        "recorte_util": tarja,
    }


def audio(texto):
    """Saida do `volumedetect` -> volume medio e de pico, em dB.

    Texto vazio significa video mudo, e mudo nao e erro: e informacao.
    """
    medio = _numeros(_VOLUME_MEDIO, texto)
    pico = _numeros(_VOLUME_PICO, texto)
    return {
        "tem_audio": bool(medio or pico),
        "volume_medio_db": medio[0] if medio else None,
        "volume_pico_db": pico[0] if pico else None,
    }


def montar(texto_da_ficha, texto_dos_cortes, texto_da_imagem, texto_do_audio):
    """As quatro leituras cruas viram um perfil so, pronto para o JSONB."""
    dados = ficha(texto_da_ficha)
    perfil = {
        "versao": VERSAO,
        "ficha": dados,
        "cortes": cortes(texto_dos_cortes, dados.get("duracao_s")),
        "imagem": imagem(texto_da_imagem),
        "audio": audio(texto_do_audio),
    }
    perfil["tem_tarja"] = _tem_tarja(dados, perfil["imagem"].get("recorte_util"))
    return perfil


def _tem_tarja(ficha_, recorte):
    """O video tem barra preta em volta? Tolerancia de 8px para compressao.

    Importa porque diz qual enquadramento o vencedor escolheu: quem posta com
    tarja encaixou; quem posta sem, preencheu ou gravou ja na proporcao.
    """
    if not recorte or not ficha_.get("largura"):
        return None
    perdeu_l = ficha_["largura"] - recorte["largura"]
    perdeu_a = ficha_["altura"] - recorte["altura"]
    return bool(perdeu_l > 8 or perdeu_a > 8)


# ------------------------------------------------------------- o conjunto


def ajuste_de_cor(brilho_atual, saturacao_atual, brilho_alvo, saturacao_alvo,
                  teto_brilho=0.25, faixa_saturacao=(0.6, 1.8)):
    """Quanto mexer na cor para o video parecer com a faixa medida.

    O `eq` do ffmpeg trabalha em duas escalas diferentes, e confundi-las e
    facil: `brightness` e **somado** ao pixel ja normalizado em 0..1, entao a
    diferenca medida em 0..255 precisa ser dividida por 255. `saturation` e
    **multiplicado**, entao vira razao e nao diferenca.

    Os dois vem presos numa faixa de proposito. Uma medicao ruim — video quase
    todo preto, por exemplo — pediria uma correcao gigante e destruiria a
    imagem. Preso, o pior caso e uma correcao insuficiente, que e um erro que
    da para ver e desfazer.
    """
    if brilho_atual is None or brilho_alvo is None:
        brilho = 0.0
    else:
        bruto = (brilho_alvo - brilho_atual) / 255.0
        brilho = max(-teto_brilho, min(teto_brilho, bruto))

    if not saturacao_atual or saturacao_alvo is None:
        saturacao = 1.0
    else:
        bruto = saturacao_alvo / float(saturacao_atual)
        saturacao = max(faixa_saturacao[0], min(faixa_saturacao[1], bruto))

    return {"brilho": round(brilho, 4), "saturacao": round(saturacao, 3)}


def sugerir(perfil, nome, base):
    """Perfil medido -> um template, a partir de `base`.

    **So entra no template o que foi medido e tem variacao.** O volume ficou de
    fora de proposito: nos 15 videos medidos em 02/09/2026 ele variou 1,6 dB no
    total, com os picos dentro de 0,9 dB — isso e a normalizacao de sonoridade
    do proprio Instagram, nao escolha de quem edita. Derivar um alvo de audio
    dali seria lavar um artefato de plataforma como se fosse padrao do nicho.

    O ritmo de corte tambem nao entra: o editor aplica moldura, ele nao remonta
    o video. O numero vai no `_leia`, para ser lido por gente.
    """
    import copy
    novo = copy.deepcopy(base)
    novo["nome"] = nome

    quantos = perfil.get("quantos") or 0
    dominante = perfil.get("proporcao_dominante")
    sem_tarja = perfil.get("sem_tarja") or 0
    com_tarja = perfil.get("com_tarja") or 0

    # Proporcao: se os medidos postam em 9:16 e sem tarja, eles preenchem a
    # tela. O molde e esse.
    video = novo.setdefault("video", {})
    if dominante == "9:16" and sem_tarja > com_tarja:
        video["ajuste"] = PREENCHER_SUGERIDO
        video["topo"] = 0
        video["altura"] = novo["canvas"]["altura"]
        video["margem_lateral"] = 0
    else:
        video["ajuste"] = "desfoque"

    brilho = (perfil.get("brilho") or (None, None, None))[1]
    saturacao = (perfil.get("saturacao") or (None, None, None))[1]
    novo["cor"] = {
        "_leia": "Alvo medido no nicho. O editor mede o SEU video e calcula a "
                 "diferenca sozinho — estes numeros sao o destino, nao o ajuste.",
        "igualar": True,
        "brilho_alvo": brilho,
        "saturacao_alvo": saturacao,
    }

    corte = (perfil.get("cortes_por_minuto") or (None, None, None))
    duracao = (perfil.get("duracao_s") or (None, None, None))
    novo["_leia"] = (
        "Gerado por `pipeline.py medir --sugerir` a partir de %d video(s) "
        "medido(s). O que a maquina NAO faz: cortar. Os medidos cortam %s vezes "
        "por minuto (de %s a %s) e duram %ss na mediana — isso e para voce "
        "gravar diferente, nao para o editor aplicar. O volume ficou de fora "
        "porque nos medidos ele variou so 1,6 dB no total, o que e a "
        "normalizacao do Instagram e nao escolha de quem edita."
        % (quantos, corte[1], corte[0], corte[2], duracao[1]))

    return novo


PREENCHER_SUGERIDO = "preencher"


def perfil_do_conjunto(perfis):
    """Varios videos -> a faixa em que eles vivem.

    Devolve quartis, nao media. E devolve `quantos` junto, sempre: uma faixa
    tirada de 3 videos e uma faixa tirada de 300 se leem de um jeito muito
    diferente, e omitir o tamanho da amostra e o jeito mais facil de fazer
    numero pequeno parecer conclusao.
    """
    validos = [p for p in perfis if p]
    if not validos:
        return {"quantos": 0}

    def colher(caminho):
        valores = []
        for perfil in validos:
            no = perfil
            for chave in caminho:
                no = (no or {}).get(chave)
            if isinstance(no, (int, float)):
                valores.append(float(no))
        return valores

    proporcoes = {}
    for perfil in validos:
        nome = (perfil.get("ficha") or {}).get("proporcao")
        if nome:
            proporcoes[nome] = proporcoes.get(nome, 0) + 1

    com_tarja = [p.get("tem_tarja") for p in validos if p.get("tem_tarja") is not None]

    return {
        "quantos": len(validos),
        "proporcoes": dict(sorted(proporcoes.items(), key=lambda p: -p[1])),
        "proporcao_dominante": max(proporcoes, key=proporcoes.get) if proporcoes else None,
        "com_tarja": sum(1 for t in com_tarja if t),
        "sem_tarja": sum(1 for t in com_tarja if not t),
        "duracao_s": quartis(colher(("ficha", "duracao_s"))),
        "cortes_por_minuto": quartis(colher(("cortes", "por_minuto"))),
        "segundos_por_corte": quartis(colher(("cortes", "segundos_por_corte"))),
        "brilho": quartis(colher(("imagem", "brilho"))),
        "saturacao": quartis(colher(("imagem", "saturacao"))),
        "volume_medio_db": quartis(colher(("audio", "volume_medio_db"))),
    }
