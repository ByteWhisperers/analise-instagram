"""Palavras com tempo -> arquivo .ass de legenda.

O `.ass` e o formato que o ffmpeg queima no video com libass. Ele aceita
posicao, contorno, sombra e troca de cor no meio da frase — que e o que
faz a legenda "acender" palavra por palavra.

O estilo de pagina de meme e simples de proposito: poucas palavras por vez,
grandes, no centro. Nada de animacao — e volume, nao motion design.
"""

CANVAS_LARGURA = 1080
CANVAS_ALTURA = 1920

CABECALHO = """[Script Info]
ScriptType: v4.00+
PlayResX: %(largura)d
PlayResY: %(altura)d
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Padrao,%(fonte)s,%(tamanho)d,%(cor)s,%(cor)s,%(contorno_cor)s,&H80000000,%(negrito)d,0,0,0,100,100,0,0,1,%(contorno)d,%(sombra)d,5,%(margem)d,%(margem)d,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def cor_para_ass(cor_hex, opacidade=0):
    """'#FF0044' -> '&H000044FF'.

    O .ass usa AABBGGRR, ao contrario do CSS. Quem escreve o template escreve
    em hexadecimal normal; a conversao fica aqui.
    """
    texto = (cor_hex or "#FFFFFF").lstrip("#")
    if len(texto) == 3:
        texto = "".join(letra * 2 for letra in texto)
    vermelho, verde, azul = texto[0:2], texto[2:4], texto[4:6]
    return "&H%02X%s%s%s" % (opacidade, azul.upper(), verde.upper(),
                             vermelho.upper())


def _tempo(segundos):
    """0:00:02.40 — o formato que o .ass espera."""
    if segundos < 0:
        segundos = 0
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    resto = segundos % 60
    return "%d:%02d:%05.2f" % (horas, minutos, resto)


def _escapar(texto):
    """No .ass, a chave abre comando e a barra invertida escapa."""
    return (texto.replace("\\", "").replace("{", "(").replace("}", ")")
            .replace("\n", " ").strip())


def agrupar(palavras, por_grupo=3, pausa_que_quebra=0.8):
    """Junta as palavras em blocos curtos, do jeito que se le na tela.

    Quebra tambem quando ha silencio longo: se a pessoa parou de falar, a
    legenda nao deve arrastar a frase anterior por cima do silencio.
    """
    grupos = []
    atual = []

    for palavra in palavras:
        if atual:
            silencio = palavra["inicio"] - atual[-1]["fim"]
            if len(atual) >= por_grupo or silencio > pausa_que_quebra:
                grupos.append(atual)
                atual = []
        atual.append(palavra)

    if atual:
        grupos.append(atual)
    return grupos


def _linha(inicio, fim, texto, posicao_y):
    return "Dialogue: 0,%s,%s,Padrao,,0,0,0,,{\\pos(%d,%d)}%s" % (
        _tempo(inicio), _tempo(fim), CANVAS_LARGURA // 2, posicao_y, texto)


def _grupo_sem_destaque(grupo, posicao_y):
    texto = " ".join(_escapar(p["palavra"]) for p in grupo)
    return [_linha(grupo[0]["inicio"], grupo[-1]["fim"], texto, posicao_y)]


def _grupo_com_destaque(grupo, posicao_y, cor_destaque, cor_normal):
    """Uma linha por palavra: a que esta sendo dita muda de cor.

    E o efeito de "acender". Custa nada em processamento — quem faz o
    trabalho e o libass, na hora de queimar.
    """
    linhas = []
    for indice, palavra in enumerate(grupo):
        partes = []
        for outro_indice, outra in enumerate(grupo):
            limpa = _escapar(outra["palavra"])
            if outro_indice == indice:
                partes.append("{\\c%s}%s{\\c%s}" % (cor_destaque, limpa, cor_normal))
            else:
                partes.append(limpa)

        fim = palavra["fim"]
        if indice + 1 < len(grupo):
            fim = max(fim, grupo[indice + 1]["inicio"])

        linhas.append(_linha(palavra["inicio"], fim, " ".join(partes), posicao_y))
    return linhas


def montar(palavras, estilo):
    """Devolve o conteudo completo do arquivo .ass."""
    cor_normal = cor_para_ass(estilo.get("cor", "#FFFFFF"))
    cor_destaque = cor_para_ass(estilo.get("cor_destaque", "#FFE100"))

    cabecalho = CABECALHO % {
        "largura": CANVAS_LARGURA,
        "altura": CANVAS_ALTURA,
        "fonte": estilo.get("fonte", "Arial"),
        "tamanho": estilo.get("tamanho", 58),
        "cor": cor_normal,
        "contorno_cor": cor_para_ass(estilo.get("cor_contorno", "#000000")),
        "negrito": -1 if estilo.get("negrito", True) else 0,
        "contorno": estilo.get("contorno", 4),
        "sombra": estilo.get("sombra", 0),
        "margem": estilo.get("margem_lateral", 80),
    }

    posicao_y = estilo.get("posicao_y", CANVAS_ALTURA // 2)
    destacar = estilo.get("destacar_palavra", True)
    grupos = agrupar(palavras,
                     estilo.get("palavras_por_grupo", 3),
                     estilo.get("pausa_que_quebra", 0.8))

    linhas = []
    for grupo in grupos:
        if destacar:
            linhas.extend(_grupo_com_destaque(grupo, posicao_y, cor_destaque,
                                              cor_normal))
        else:
            linhas.extend(_grupo_sem_destaque(grupo, posicao_y))

    return cabecalho + "\n".join(linhas) + "\n"


def gravar(palavras, estilo, destino):
    """Escreve o .ass. Devolve o caminho, ou None se nao havia fala."""
    if not palavras:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(montar(palavras, estilo), encoding="utf-8")
    return destino
