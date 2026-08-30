"""Que idioma e este texto? Heuristica, sem instalar nada.

**Por que existe:** em 30/08/2026 o mapeamento de "desastres e tragedias"
voltou inteiro em espanhol — `#emergencias`, `#bomberos`, `#gestióndelriesgo`,
`#perú` — e nada no sistema levantou a mao. A tag-semente `#desastres` e
hispanofona, e o laco guloso aprofundou nesse cluster por tres rodadas pagas.

**Por que heuristica e nao biblioteca:** instalar dependencia e ponto de parada
obrigatorio (V1 §14), e para separar portugues de espanhol num texto de legenda
de Instagram o problema e pequeno o suficiente para caber em regra explicita.
Regra explicita tem uma vantagem que biblioteca nao tem aqui: quando ela erra,
da para ler por que.

**O que este modulo NAO faz:** nao entende o texto. Ele conta sinais. Um post
com tres palavras pode nao ter sinal nenhum, e ai a resposta e `None` — que
significa "nao sei", e e diferente de "nao e portugues". A diferenca entre as
duas e o que impede o filtro de matar tag legitima calado.
"""

import re
import unicodedata

# Sinais que praticamente so aparecem num dos dois idiomas. Peso 3: quando um
# destes aparece, dificilmente e coincidencia.
LETRAS = {
    "pt": ("ã", "õ"),
    "es": ("ñ", "¿", "¡"),
}

# Peso 2. `ç` e portugues (e frances, que nao esperamos aqui); `lh`/`nh` sao
# portugues; `ll` e espanhol.
DIGRAFOS = {
    "pt": ("ç", "lh", "nh"),
    "es": ("ll",),
}

# Peso 3: sufixo que praticamente nao existe no outro idioma. `ção` e `ción`
# sao o mesmo sufixo latino em duas grafias — quem escreve um nao escreve o
# outro.
SUFIXOS_FORTES = {
    "pt": ("ção", "ções"),
    "es": ("ción", "ciones"),
}

# Peso 1: indicio, nao prova. `inho` aparece em nome proprio espanhol e `dad`
# aparece em ingles.
SUFIXOS_FRACOS = {
    "pt": ("agem", "inho", "inha"),
    "es": ("dad", "miento"),
}

# Peso 1 cada. So palavras que NAO existem no outro idioma com o mesmo sentido
# e a mesma grafia — `para`, `com`/`con` e `mais`/`más` ficam de fora de
# proposito, porque a diferenca entre elas e justamente o acento, e legenda de
# Instagram e escrita sem acento o tempo todo.
PALAVRAS = {
    "pt": frozenset((
        "nao", "não", "voce", "você", "voces", "vocês", "entao", "então",
        "isso", "hoje", "gente", "muito", "muita", "seu", "sua", "dos", "das",
        "ele", "ela", "eles", "sao", "são", "pra", "pro",
        "tambem", "também", "obrigado", "obrigada", "receita", "dica",
        "melhor", "trabalho", "coisa", "fazer", "agora",
    )),
    "es": frozenset((
        "el", "los", "las", "una", "pero", "tambien", "también",
        "muy", "más", "del", "al", "sus", "ellos", "nosotros",
        "hoy", "aquí", "gracias", "hola", "año", "años",
        "niños", "salud", "seguridad", "emergencia", "emergencias", "trabajo",
        "mejor", "ahora", "hacer",
    )),
}

# Palavra que aparece nas duas listas nao decide nada: some das duas.
_AMBIGUAS = PALAVRAS["pt"] & PALAVRAS["es"]

# Quantos pontos de vantagem um idioma precisa ter para a resposta valer.
#
# **Tres, e nao dois.** Com dois, um digrafo solto decidia sozinho: `"llama"`
# virava espanhol, e uma marca com `ll` no meio de uma legenda portuguesa
# bastava para votar espanhol. Agora so decide sozinho o sinal conclusivo —
# `ã`, `õ`, `ñ`, `¿`, `¡` e os sufixos `ção`/`ción`. Digrafo precisa de
# companhia.
#
# Isto importa mais que o normal porque o usuario escolheu o filtro DURO: tag
# provada de outro idioma e descartada. Falso positivo aqui joga fora
# vocabulario legitimo.
VANTAGEM_MINIMA = 3

_PALAVRA = re.compile(r"[^\W\d_]+", re.UNICODE)


def _normalizar(texto):
    return unicodedata.normalize("NFC", str(texto or "")).lower()


def pontuar(texto):
    """Quantos pontos cada idioma marcou. Util para depurar o veredito."""
    texto = _normalizar(texto)
    if not texto.strip():
        return {"pt": 0, "es": 0}

    palavras = set(_PALAVRA.findall(texto))
    pontos = {}

    for lingua in ("pt", "es"):
        total = 0
        total += 3 * sum(texto.count(letra) > 0 for letra in LETRAS[lingua])
        total += 2 * sum(digrafo in texto for digrafo in DIGRAFOS[lingua])
        total += 3 * sum(any(p.endswith(s) for p in palavras)
                         for s in SUFIXOS_FORTES[lingua])
        total += 1 * sum(any(p.endswith(s) for p in palavras)
                         for s in SUFIXOS_FRACOS[lingua])
        total += len(palavras & (PALAVRAS[lingua] - _AMBIGUAS))
        pontos[lingua] = total

    return pontos


def detectar(texto):
    """`"pt"`, `"es"` ou **`None` para "nao da para saber"**.

    O terceiro estado nao e detalhe: legenda de Instagram e curta, e muita nao
    tem sinal nenhum. Devolver "es" por ausencia de sinal portugues faria o
    filtro descartar a tag de um post que so dizia "olha isso 🔥".
    """
    pontos = pontuar(texto)
    pt, es = pontos["pt"], pontos["es"]

    if pt - es >= VANTAGEM_MINIMA:
        return "pt"
    if es - pt >= VANTAGEM_MINIMA:
        return "es"
    return None


def votar(textos):
    """Varios textos -> `(idioma, votos)`, pela maioria dos que opinaram.

    Os `None` sao contados mas nao votam: uma tag usada em dez posts, nove sem
    sinal e um em espanhol, e uma tag sobre a qual se sabe pouco — e o pouco
    que se sabe diz espanhol.
    """
    votos = {"pt": 0, "es": 0, "?": 0}
    for texto in (textos or []):
        veredito = detectar(texto)
        votos["?" if veredito is None else veredito] += 1

    if votos["pt"] == votos["es"]:
        return None, votos
    return ("pt" if votos["pt"] > votos["es"] else "es"), votos
