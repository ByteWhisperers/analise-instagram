"""O que um post FALA, e nao so as tags que ele carrega.

**Por que existe:** ate a T15 o mapeamento colhia um campo so — `hashtags` — e
jogava a legenda fora depois de olha-la uma vez para votar idioma. Tudo que
distingue uma tribo da outra estava naquele texto descartado: giria, emoji,
abreviacao, expressao de duas palavras, mencao, entidade.

`[MEDIDO 30/08/2026]` A lista plana de hashtags nao consegue separar tribo de
territorio. No dossie `tragediaseresgates`, `#sêneca`, `#aristófanes` e
`#teatro` (literatura) ficaram no MESMO nivel do ranking que `#acidenteaéreo`,
`#br242` e `#aviões` (desastre real) e que `#amor` e `#autopiedade` (drama
pessoal). Tres tribos dividindo uma palavra.

**A premissa deste modulo:** a legenda ja foi paga. Ela chega dentro do mesmo
item que custou dinheiro, e le-la de novo custa CPU, nao centavo. Colher dela
multiplica a base observavel sem uma chamada nova.

**O que este modulo NAO faz:** nao conhece o schema do Actor. Ele recebe texto,
hashtags e mencoes ja extraidos, e devolve termos. Quem sabe onde esses campos
moram dentro do item cru e o `coletor.py` — a mesma divisao que existe entre
`idioma.py` (le texto) e quem vai buscar o texto.
"""

import re

# Os cinco tipos de termo que uma legenda rende. Fechado de proposito: tipo
# novo e mudanca de schema no banco (`term_observations.kind`), entao nao pode
# nascer por descuido no meio de um laco.
KINDS = ("hashtag", "palavra", "bigrama", "emoji", "mencao")

# Tamanho minimo de palavra. DOIS, e nao tres: `fé` tem duas letras e e
# marcador de pertencimento numa das tribos de moto. Quem derruba palavra curta
# inutil e a lista de vazias abaixo, nao o comprimento.
MINIMO_DE_LETRAS = 2

# Palavras que ligam frase e nao nomeiam nada. Portugues e espanhol na mesma
# lista porque o mapeamento cruza os dois o tempo todo, e uma tag hispanofona
# no meio de um dossie portugues nao deve render `el`, `los`, `pero` como
# vocabulario.
#
# **So palavra de FUNCAO.** Artigo, preposicao, pronome, conjuncao, auxiliar.
# Verbo comum (`dar`, `fazer`, `ir`) fica FORA: `dar grau` e a expressao da
# tribo, e uma lista que engolisse `dar` mataria o bigrama que mais identifica.
VAZIAS = frozenset((
    # portugues
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "num", "numa", "por", "pelo",
    "pela", "para", "pra", "pro", "com", "sem", "sob", "sobre", "ate", "até",
    "e", "ou", "mas", "que", "se", "como", "quando", "onde", "porque",
    "eu", "tu", "ele", "ela", "nos", "nós", "vos", "eles", "elas", "voce",
    "você", "voces", "vocês", "me", "te", "lhe", "nos", "seu", "sua", "seus",
    "suas", "meu", "minha", "meus", "minhas", "dele", "dela", "isso", "isto",
    "aquilo", "este", "esta", "esse", "essa", "aquele", "aquela",
    "ser", "sou", "e", "é", "sao", "são", "era", "eram", "foi", "foram",
    "ter", "tem", "tinha", "tenho", "temos", "estar", "esta", "está",
    "estao", "estão", "estava", "ja", "já", "nao", "não", "sim", "mais",
    "menos", "muito", "muita", "muitos", "muitas", "todo", "toda", "todos",
    "todas", "cada", "outro", "outra", "ao", "aos", "à", "às", "dai", "daí",
    # espanhol
    "el", "la", "las", "los", "un", "una", "unos", "unas", "del", "al",
    "en", "con", "sin", "por", "para", "sobre", "hasta", "desde", "entre",
    "y", "o", "pero", "que", "si", "como", "cuando", "donde", "porque",
    "yo", "tu", "él", "ella", "nosotros", "ellos", "ellas", "su", "sus",
    "mi", "mis", "esto", "eso", "este", "esta", "ese", "esa",
    "ser", "soy", "es", "son", "era", "eran", "fue", "fueron", "tener",
    "tiene", "tengo", "estar", "está", "están", "ya", "no", "sí", "más",
    "menos", "mucho", "mucha", "todo", "toda", "todos", "todas", "cada",
    "otro", "otra", "lo", "le", "les", "se", "de", "a",
    # ruido de legenda, nao e idioma
    "http", "https", "www", "com", "br", "link", "bio",
))

# Letras e digitos, sem pontuacao e sem sublinhado. **Digito entra de
# proposito:** `244` E o nome da tribo no caso que originou este modulo, e um
# regex que so aceitasse letras a apagaria.
_PALAVRA = re.compile(r"[^\W_]+", re.UNICODE)

# `@fulano` e `#tag` na legenda. O Actor devolve campos proprios para os dois,
# mas nem sempre preenchidos — o regex e o plano B, nunca o principal.
_MENCAO = re.compile(r"@([A-Za-z0-9._]{2,30})")
_TAG_NO_TEXTO = re.compile(r"#([^\W_]{2,})", re.UNICODE)

# O que sai do texto ANTES de virar palavra. URL, arroba e cerquilha ja tem
# `kind` proprio; deixa-los no fluxo de palavras contaria a mesma coisa duas
# vezes com nomes diferentes.
#
# `[MEDIDO 30/08/2026]` `@fulano_mt` rendia as palavras `fulano` e `mt` — o
# sublinhado nao e letra para o regex de palavra, entao a mencao se partia em
# duas. E legenda de Instagram termina em muralha de hashtag: sem tirar,
# trinta tags no fim do post afogariam o vocabulario real da legenda.
_LIXO_DE_PALAVRA = re.compile(
    r"(https?://\S+|www\.\S+|[@#][^\s#@]+)", re.UNICODE)

# Faixas de emoji, por ponto de codigo. Sem `emoji` do PyPI: instalar
# dependencia e ponto de parada obrigatorio (V1 §14), e reconhecer emoji e
# comparacao de intervalo — cabe em regra explicita, que ainda tem a vantagem
# de dar para ler quando erra.
_FAIXAS = (
    (0x1F300, 0x1F5FF),   # simbolos e pictogramas
    (0x1F600, 0x1F64F),   # rostos
    (0x1F680, 0x1F6FF),   # transporte e mapa (a moto mora aqui)
    (0x1F900, 0x1F9FF),   # suplementares
    (0x1FA70, 0x1FAFF),   # estendidos A
    (0x1F1E6, 0x1F1FF),   # indicadores regionais (bandeiras)
    (0x2600,  0x26FF),    # simbolos diversos
    (0x2700,  0x27BF),    # dingbats
)

# Caracteres que GRUDAM num emoji e nao valem sozinhos: seletor de variacao,
# juntador de largura zero e os cinco tons de pele. Sem trata-los, a familia
# com ZWJ viraria quatro emojis soltos e o tom de pele viraria termo proprio.
_COLADOS = frozenset(
    [0xFE0F, 0x200D, 0x20E3] + list(range(0x1F3FB, 0x1F400))
)


def e_emoji(caractere):
    """Este caractere abre um emoji?"""
    ponto = ord(caractere)
    return any(inicio <= ponto <= fim for inicio, fim in _FAIXAS)


def emojis_do_texto(texto):
    """Os emojis, na ordem, com sequencia ZWJ contada como UM.

    Bandeira e familia sao varios pontos de codigo colados. Devolver cada
    pedaco separado inventaria termos que ninguem digitou.
    """
    texto = str(texto or "")
    achados, i = [], 0
    while i < len(texto):
        if not e_emoji(texto[i]):
            i += 1
            continue
        fim = i + 1
        while fim < len(texto) and (ord(texto[fim]) in _COLADOS
                                    or (fim > 0
                                        and ord(texto[fim - 1]) == 0x200D
                                        and e_emoji(texto[fim]))
                                    or (e_emoji(texto[fim])
                                        and 0x1F1E6 <= ord(texto[i]) <= 0x1F1FF
                                        and 0x1F1E6 <= ord(texto[fim]) <= 0x1F1FF)):
            fim += 1
        achados.append(texto[i:fim])
        i = fim
    return achados


def _normalizar(palavra):
    """Minuscula, sem pontuacao, **com acento**.

    Delega ao `coletor.tag_do_termo`, que ja e idempotente e ja preserva
    acento — e preservar acento nao e detalhe: `#tragedias` e `#tragédias` sao
    duas comunidades diferentes, medido em 30/08/2026.

    Import tardio para nao fechar ciclo: o `coletor` importa este modulo.
    """
    from coletor import tag_do_termo

    return tag_do_termo(palavra)


def _so_prosa(texto):
    """A legenda sem URL, sem `@fulano` e sem `#tag`. Emoji fica."""
    return _LIXO_DE_PALAVRA.sub(" ", str(texto or ""))


def palavras_do_texto(texto):
    """As palavras que valem, ja normalizadas e sem as vazias."""
    achadas = []
    for cru in _PALAVRA.findall(_so_prosa(texto)):
        palavra = _normalizar(cru)
        if len(palavra) < MINIMO_DE_LETRAS or palavra in VAZIAS:
            continue
        achadas.append(palavra)
    return achadas


def bigramas_do_texto(texto):
    """Pares adjacentes de palavras, montados ANTES de tirar as vazias.

    A ordem importa. Tirando as vazias primeiro, `dar grau` sobreviveria mas
    `sem caô` viraria `caô` — e a expressao inteira e que e o marcador.

    Descarta so o par em que AS DUAS sao vazias (`de que`, `para o`). Par com
    uma vazia sobrevive e vira ruido, sim — e ruido aqui e barato: quem afunda
    o generico e a exclusividade da Fase 3, nao uma lista negra escrita a mao.
    """
    cruas = [_normalizar(p) for p in _PALAVRA.findall(_so_prosa(texto))]
    cruas = [p for p in cruas if len(p) >= MINIMO_DE_LETRAS]

    pares = []
    for esquerda, direita in zip(cruas, cruas[1:]):
        if esquerda in VAZIAS and direita in VAZIAS:
            continue
        pares.append("%s %s" % (esquerda, direita))
    return pares


def mencoes_do_texto(texto):
    """Os `@fulano` da legenda. Plano B de quando o campo do Actor vem vazio."""
    return [_normalizar(nome) for nome in _MENCAO.findall(str(texto or ""))
            if _normalizar(nome)]


def hashtags_do_texto(texto):
    """As `#tag` da legenda. Plano B de quando o campo do Actor vem vazio."""
    return [_normalizar(tag) for tag in _TAG_NO_TEXTO.findall(str(texto or ""))
            if _normalizar(tag)]


def termos_do_texto(texto, com_bigramas=True):
    """Texto -> `[(termo, kind)]` do que SO existe na prosa.

    Palavra, bigrama e emoji. Hashtag e mencao ficam de fora aqui de proposito:
    elas tem campo proprio no item do Actor, e quem decide entre o campo e o
    plano B do regex e `observacoes()`. Colher nos dois lugares contaria a
    mesma tag duas vezes.

    Uma OCORRENCIA por termo, sem deduplicar. Quem conta e `contar()`, e ela
    precisa da frequencia real: termo repetido tres vezes na mesma legenda e um
    sinal diferente de termo dito uma vez.
    """
    achados = [(p, "palavra") for p in palavras_do_texto(texto)]
    if com_bigramas:
        achados += [(b, "bigrama") for b in bigramas_do_texto(texto)]
    achados += [(e, "emoji") for e in emojis_do_texto(texto)]
    return achados


def observacoes(texto=None, hashtags=None, mencoes=None, perfil=None,
                post=None, fonte=None, voto="?", com_bigramas=True):
    """Um post -> a lista de observacoes que ele produziu.

    Cada observacao e uma linha: `{termo, kind, perfil, post, idioma, fonte}`.
    E o formato que vai para `term_observations` sem traducao no meio.

    `voto` e o idioma do POST, detectado uma vez la fora e repassado aqui: a
    legenda e a mesma para todos os termos dela, e detectar de novo por termo
    seria gastar CPU para chegar na mesma resposta.

    **Campo primeiro, regex depois.** Para hashtag e mencao o campo que o Actor
    devolve manda; o regex sobre a legenda so entra quando o campo vem vazio.
    Somar os dois contaria a mesma tag duas vezes, e a contagem de posts e o
    que sustenta todo o ranqueamento.
    """
    achados = list(termos_do_texto(texto, com_bigramas=com_bigramas))

    tags = [t for t in (hashtags or []) if isinstance(t, str) and t.strip()]
    for tag in (tags if tags else hashtags_do_texto(texto)):
        chave = _normalizar(str(tag).lstrip("#"))
        if chave:
            achados.append((chave, "hashtag"))

    nomes = [m for m in (mencoes or []) if isinstance(m, str) and m.strip()]
    for nome in (nomes if nomes else mencoes_do_texto(texto)):
        chave = _normalizar(str(nome).lstrip("@"))
        if chave:
            achados.append((chave, "mencao"))

    return [{"termo": termo, "kind": kind, "perfil": perfil, "post": post,
             "idioma": voto if voto in ("pt", "es") else "?", "fonte": fonte}
            for termo, kind in achados]


def contar(lista, kinds=None):
    """Observacoes -> `{termo: {posts, perfis, idiomas, fonte}}`.

    E de proposito a MESMA forma que `coletor.tags_dos_itens` sempre devolveu,
    para `mapeador.fundir_contagens` e `mapeador.ranquear_termos` continuarem
    valendo sem uma linha de traducao.

    `kinds=None` conta tudo. Passar `("hashtag",)` reproduz o comportamento
    antigo, termo a termo.

    **Perfis distintos e o que manda, nao posts** — a razao esta em
    `ranquear_termos`: tag de patrocinio aparece muito, mas num perfil so.
    Aqui a contagem so guarda os dois; quem decide e o ranqueamento.
    """
    achado = {}
    for obs in (lista or []):
        if kinds is not None and obs["kind"] not in kinds:
            continue
        chave = obs["termo"]
        linha = achado.setdefault(chave, {
            "posts": 0, "perfis": [],
            "idiomas": {"pt": 0, "es": 0, "?": 0},
            "fonte": obs.get("fonte"), "kind": obs["kind"],
        })
        linha["posts"] += 1
        linha["idiomas"][obs["idioma"]] = linha["idiomas"].get(
            obs["idioma"], 0) + 1
        dono = obs.get("perfil")
        if dono and dono not in linha["perfis"]:
            linha["perfis"].append(dono)
    return achado
