"""As contas da analise, isoladas.

Tudo aqui e funcao pura: entra texto ou numero, sai numero ou dicionario.
Nada le arquivo, nada acessa a rede. E o que permite conferir cada conta a mao.
"""

import re

SEGUNDOS_DO_GANCHO = 3.0

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF"   # simbolos, pictogramas, emoticons
    "\U0001F1E6-\U0001F1FF"    # bandeiras
    "☀-➿"            # simbolos diversos e dingbats
    "⬀-⯿"            # setas e formas
    "←-⇿]"           # setas
)

_PALAVRA = re.compile(r"\b[\w'-]+\b", re.UNICODE)

# Expressoes de chamada para acao, agrupadas pelo que pedem ao espectador.
CHAMADAS_PARA_ACAO = {
    "clicar": ["link na bio", "link da bio", "link na minha bio", "clica no link",
               "link nos comentarios", "acessa o link", "arrasta pra cima"],
    "comentar": ["comenta ai", "comenta aqui", "comente", "comenta que eu",
                 "escreve nos comentarios", "responde nos comentarios"],
    "salvar": ["salva esse", "salva ai", "salva esse post", "salva pra depois",
               "guarda esse"],
    "seguir": ["me segue", "segue la", "segue o perfil", "me sigam", "siga",
               "ativa o sininho"],
    "compartilhar": ["compartilha", "manda pra", "marca um amigo", "marca alguem",
                     "envia pro"],
    "cadastrar": ["se cadastra", "cadastra ai", "faz seu cadastro", "usa meu cupom",
                  "cupom", "codigo promocional"],
}


def _achatar(texto):
    """Minusculo e sem acento, so para procurar expressao."""
    import unicodedata
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    return "".join(letra for letra in normalizado if not unicodedata.combining(letra))


def contar_palavras(texto):
    return len(_PALAVRA.findall(texto or ""))


def palavras_por_minuto(texto, duracao_segundos):
    """O ritmo da fala. Reels rapido costuma passar de 180."""
    if not duracao_segundos:
        return None
    return round(contar_palavras(texto) / (duracao_segundos / 60), 1)


def contar_emojis(texto):
    return len(_EMOJI.findall(texto or ""))


def primeira_linha(legenda):
    """A unica linha que o Instagram mostra antes do 'mais'. E o gancho escrito."""
    for linha in (legenda or "").splitlines():
        if linha.strip():
            return linha.strip()
    return ""


def analisar_legenda(legenda):
    legenda = legenda or ""
    linhas = [linha for linha in legenda.splitlines() if linha.strip()]
    return {
        "primeira_linha": primeira_linha(legenda),
        "caracteres": len(legenda),
        "palavras": contar_palavras(legenda),
        "linhas": len(linhas),
        "emojis": contar_emojis(legenda),
        "tem_paragrafos": "\n\n" in legenda,
        "termina_com_pergunta": legenda.strip().endswith("?"),
    }


def detectar_chamadas(texto):
    """Devolve {tipo: [expressoes achadas]}. Procura sem acento e sem maiuscula."""
    achatado = _achatar(texto or "")
    achadas = {}
    for tipo, expressoes in CHAMADAS_PARA_ACAO.items():
        encontradas = [expressao for expressao in expressoes if expressao in achatado]
        if encontradas:
            achadas[tipo] = encontradas
    return achadas


def taxa_de_engajamento(curtidas, comentarios, seguidores):
    """(curtidas + comentarios) / seguidores, em porcentagem."""
    if not seguidores:
        return None
    return round(((curtidas or 0) + (comentarios or 0)) / seguidores * 100, 3)


def gancho_falado(segmentos, ate_segundos=SEGUNDOS_DO_GANCHO):
    """O que e dito nos primeiros segundos - onde a pessoa decide se fica."""
    trechos = [s["texto"] for s in (segmentos or []) if s["inicio"] < ate_segundos]
    return " ".join(trechos).strip()


def blocos_no_tempo(segmentos, quantos=6):
    """Os primeiros trechos com seu segundo de inicio - o esqueleto do video."""
    return [
        {"segundo": s["inicio"], "texto": s["texto"]}
        for s in (segmentos or [])[:quantos]
    ]


def media(valores):
    limpos = [v for v in valores if v is not None]
    if not limpos:
        return None
    return round(sum(limpos) / len(limpos), 2)


def contar_ocorrencias(listas):
    """Achata varias listas e conta quantas vezes cada item aparece."""
    contagem = {}
    for lista in listas:
        for item in lista or []:
            contagem[item] = contagem.get(item, 0) + 1
    return dict(sorted(contagem.items(), key=lambda par: par[1], reverse=True))
