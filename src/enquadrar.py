"""Onde o video fica dentro do quadro. So funcao pura.

**Por que existe:** ate 02/09/2026 o template tinha tres botoes — `topo`,
`altura` e `margem_lateral` — e o video era sempre *encaixado* dentro dessa
caixa. Nao havia como cortar, dar zoom nem deslocar. Com fonte ja em 9:16, que
e o que sai de celular, o `meme-branco` reduzia o video a 51% do quadro e nao
havia botao nenhum para consertar isso.

Tres modos, e o padrao e o comportamento antigo:

    encaixar    o video inteiro cabe na caixa; sobra fundo em volta
    preencher   o video e ampliado ate encher a caixa; as bordas sao cortadas
    desfoque    o video inteiro por cima de uma copia BORRADA dele mesmo,
                esticada ate encher o quadro. Nada some, nada fica vazio

**Por que a conta em Python e nao em expressao do ffmpeg.** O corte com
deslocamento precisa ser preso nos limites da imagem — pedir ao `crop` um
recorte que comeca fora da fonte e erro, nao aviso. Fazer isso com `min`/`max`
dentro do filtro exige escapar virgula, e este projeto ja apanhou de caractere
especial em filtro no Windows (ver a nota do `_bloco_de_texto` sobre o
dois-pontos). Com as dimensoes da fonte em maos, tudo vira inteiro simples — e
inteiro simples se confere sem rodar ffmpeg.

**O par:** o `libx264` exige largura e altura pares. Toda dimensao produzida
aqui passa por `_par()`. Um pixel impar nao da erro bonito: da falha de
codificacao no meio do lote.
"""

ENCAIXAR = "encaixar"
PREENCHER = "preencher"
DESFOQUE = "desfoque"

AJUSTES = (ENCAIXAR, PREENCHER, DESFOQUE)

# Quanto o fundo do modo `desfoque` e borrado. 20 e forte o bastante para o
# fundo nao competir com o video, e fraco o bastante para ainda dar contexto
# de cor. E token de template — este e so o padrao.
SIGMA_PADRAO = 20


class ErroDeEnquadramento(Exception):
    """Pedido impossivel. Mensagem ja pronta para o usuario."""


def _par(numero):
    """Arredonda para baixo ate o par mais proximo, com minimo 2."""
    inteiro = int(numero)
    if inteiro < 2:
        return 2
    return inteiro - (inteiro % 2)


def _preso(valor, minimo, maximo):
    """Prende `valor` na faixa. Faixa invertida devolve o minimo."""
    if maximo < minimo:
        return minimo
    return max(minimo, min(maximo, valor))


def calcular(fonte_l, fonte_a, caixa_l, caixa_a, ajuste=ENCAIXAR, zoom=1.0,
             deslocar_x=0, deslocar_y=0):
    """A geometria inteira, em numeros inteiros.

    Devolve:

        {"escala": (w, h),               tamanho para o qual escalar a fonte
         "corte":  (w, h, x, y) | None,  recorte depois de escalar
         "posicao": (x, y),              onde assentar dentro da CAIXA
         "sobra": (esquerda, cima)}      quanto de fundo sobra, para conferir

    `zoom` multiplica o tamanho depois do encaixe: 1.0 e o natural, 1.3 e 30%
    maior. `deslocar_x`/`deslocar_y` movem em pixels — negativo sobe e vai para
    a esquerda.
    """
    if ajuste not in AJUSTES:
        raise ErroDeEnquadramento(
            "Ajuste '%s' nao existe. Use um destes no template, em video.ajuste:"
            "\n  %s" % (ajuste, ", ".join(AJUSTES)))

    if fonte_l <= 0 or fonte_a <= 0:
        raise ErroDeEnquadramento(
            "O video de entrada mediu %sx%s. Arquivo corrompido ou sem trilha "
            "de video." % (fonte_l, fonte_a))
    if caixa_l <= 0 or caixa_a <= 0:
        raise ErroDeEnquadramento(
            "A area do video no template mediu %sx%s. Confira `video.altura` e "
            "`video.margem_lateral`." % (caixa_l, caixa_a))

    # `zoom or 1.0` estaria errado: zero e falso em Python, e `zoom=0` viraria
    # 1.0 em silencio em vez de reclamar. Foi assim que este teste pegou o bug.
    zoom = 1.0 if zoom is None else float(zoom)
    if zoom <= 0:
        raise ErroDeEnquadramento("O zoom tem que ser maior que zero, veio %s."
                                  % zoom)

    # So `preencher` usa a MAIOR razao — encher a caixa e cortar o que sobra.
    # `encaixar` e `desfoque` usam a MENOR: os dois mostram o video INTEIRO, e
    # a diferenca entre eles esta so no que aparece atras (cor solida ou o
    # proprio video borrado). Cortar no modo desfoque anularia a razao de ele
    # existir — foi o erro que o primeiro ensaio a seco pegou, em 02/09/2026.
    razao_l = caixa_l / float(fonte_l)
    razao_a = caixa_a / float(fonte_a)
    razao = max(razao_l, razao_a) if ajuste == PREENCHER else min(razao_l, razao_a)
    razao *= zoom

    escala_l = _par(round(fonte_l * razao))
    escala_a = _par(round(fonte_a * razao))

    # Sobrou imagem em alguma direcao? Entao ha corte, e o deslocamento escolhe
    # QUAL pedaco fica. Sem sobra, nao ha o que cortar naquela direcao.
    corte = None
    if escala_l > caixa_l or escala_a > caixa_a:
        corte_l = _par(min(escala_l, caixa_l))
        corte_a = _par(min(escala_a, caixa_a))
        corte_x = _preso((escala_l - corte_l) // 2 + int(deslocar_x),
                         0, escala_l - corte_l)
        corte_y = _preso((escala_a - corte_a) // 2 + int(deslocar_y),
                         0, escala_a - corte_a)
        corte = (corte_l, corte_a, corte_x, corte_y)
        largura_final, altura_final = corte_l, corte_a
    else:
        largura_final, altura_final = escala_l, escala_a

    # O que sobra de caixa vira posicao. Quando houve corte, o deslocamento ja
    # foi gasto la — aplicar de novo aqui moveria duas vezes.
    posicao_x = (caixa_l - largura_final) // 2
    posicao_y = (caixa_a - altura_final) // 2
    if corte is None:
        posicao_x = _preso(posicao_x + int(deslocar_x), 0, caixa_l - largura_final)
        posicao_y = _preso(posicao_y + int(deslocar_y), 0, caixa_a - altura_final)

    return {
        "fonte": (int(fonte_l), int(fonte_a)),
        "escala": (escala_l, escala_a),
        "corte": corte,
        "posicao": (posicao_x, posicao_y),
        "tamanho_final": (largura_final, altura_final),
    }


def do_template(template, fonte_l, fonte_a):
    """Le o bloco `video` do template e devolve a geometria.

    A caixa e o canvas menos as duas margens laterais, que e como o template
    sempre foi escrito. Mantido assim de proposito: quem ja tem template nao
    precisa reescrever nada.
    """
    canvas = template["canvas"]
    area = template.get("video", {})

    caixa_l = canvas["largura"] - 2 * area.get("margem_lateral", 60)
    caixa_a = area.get("altura", canvas["altura"])

    return calcular(fonte_l, fonte_a, caixa_l, caixa_a,
                    area.get("ajuste", ENCAIXAR),
                    area.get("zoom", 1.0),
                    area.get("deslocar_x", 0),
                    area.get("deslocar_y", 0))


def filtros(geometria, template, cor_do_fundo, rotulo_saida="base",
            ajuste_de_cor=None):
    """A geometria vira corrente de filtros. Devolve (lista, rotulo_final).

    Entra sempre por `[0:v]` e sai no rotulo pedido, para o resto de
    `montar_filtros` continuar encadeando por cima sem saber de nada disto.
    """
    canvas = template["canvas"]
    area = template.get("video", {})
    ajuste = area.get("ajuste", ENCAIXAR)

    topo = area.get("topo", 0)
    margem = area.get("margem_lateral", 60)
    escala_l, escala_a = geometria["escala"]
    posicao_x, posicao_y = geometria["posicao"]

    # Onde o video assenta no CANVAS: a posicao dentro da caixa mais o canto
    # da propria caixa.
    x = margem + posicao_x
    y = topo + posicao_y

    corrente = []

    if ajuste == DESFOQUE:
        # O fundo e o proprio video, esticado ate encher o CANVAS inteiro (nao
        # a caixa) e borrado. Nao ha `color=`: quando o fundo e imagem, cor
        # solida nao aparece em lugar nenhum, e deixar as duas seria mentir
        # sobre o que o template controla.
        fundo = _encher_o_canvas(geometria, canvas)
        corrente.append("[0:v]split=2[paraofundo][parafrente]")

        # Fonte que ja tem a proporcao exata do canvas enche sem sobrar nada, e
        # ai nao ha o que cortar. Pedir `crop` mesmo assim funcionaria, mas
        # deixa na corrente um filtro que nao faz nada — e um filtro que nao
        # faz nada e o tipo de coisa que confunde quem le o comando depois.
        recorte = ""
        if fundo["corte"]:
            recorte = ",crop=%d:%d:%d:%d" % fundo["corte"]

        corrente.append(
            "[paraofundo]scale=%d:%d%s,gblur=sigma=%s%s[fundo]"
            % (fundo["escala"][0], fundo["escala"][1], recorte,
               area.get("desfoque_sigma", SIGMA_PADRAO),
               _escurecer(area.get("desfoque_escurecer", 0))))
        entrada_da_frente = "parafrente"
    else:
        corrente.append("color=c=%s:s=%dx%d:r=%d[fundo]"
                        % (cor_do_fundo, canvas["largura"], canvas["altura"],
                           canvas.get("fps", 30)))
        entrada_da_frente = "0:v"

    escalado = "[%s]scale=%d:%d" % (entrada_da_frente, escala_l, escala_a)
    if geometria["corte"]:
        corte_l, corte_a, corte_x, corte_y = geometria["corte"]
        escalado += ",crop=%d:%d:%d:%d" % (corte_l, corte_a, corte_x, corte_y)

    # A correcao de cor vai na FRENTE, nunca no fundo desfocado: igualar a luz
    # do fundo ao nicho nao faz sentido, e mexer nele duas vezes (ja levou o
    # `escurecer`) empilharia dois ajustes na mesma imagem.
    cor = filtro_de_cor(ajuste_de_cor)
    if cor:
        escalado += "," + cor

    corrente.append(escalado + "[video]")

    # `shortest` so importa quando o fundo e `color=`, que e infinito. No modo
    # desfoque as duas pontas vem do mesmo arquivo e acabam juntas.
    fim = ":shortest=1" if ajuste != DESFOQUE else ""
    corrente.append("[fundo][video]overlay=%d:%d%s[%s]"
                    % (x, y, fim, rotulo_saida))

    return corrente, rotulo_saida


def _encher_o_canvas(geometria, canvas):
    """A geometria do fundo desfocado: encher o CANVAS inteiro.

    Reaproveita `calcular` em vez de repetir a conta — o fundo e o mesmo
    problema de `preencher`, so que contra o canvas e sempre no centro. Ele
    **nao herda zoom nem deslocamento**: quem se move e o video da frente, e
    mover o fundo junto anularia o efeito na tela.
    """
    fonte_l, fonte_a = geometria["fonte"]
    return calcular(fonte_l, fonte_a, canvas["largura"], canvas["altura"],
                    PREENCHER)


def filtro_de_cor(ajuste):
    """`{"brilho": 0.04, "saturacao": 1.1}` -> `eq=...`, ou "" se nao mexe.

    Devolve vazio quando o ajuste e neutro. Um `eq` que nao muda nada custa
    uma passada de processamento por quadro para nada.
    """
    if not ajuste:
        return ""
    brilho = float(ajuste.get("brilho") or 0)
    saturacao = float(ajuste.get("saturacao") or 1.0)
    if abs(brilho) < 0.005 and abs(saturacao - 1.0) < 0.02:
        return ""
    return "eq=brightness=%.4f:saturation=%.3f" % (brilho, saturacao)


def _escurecer(quanto):
    """Escurece o fundo desfocado. 0 nao acrescenta filtro nenhum."""
    if not quanto:
        return ""
    return ",eq=brightness=%.3f" % (-abs(float(quanto)))
