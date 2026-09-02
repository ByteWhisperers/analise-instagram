"""A lista de headlines: qual texto vai em cima de qual video.

**Por que existe:** editar 50 videos com a mesma headline nao serve, e passar
50 vezes `--headline` na linha de comando tambem nao. O roteiro e um arquivo
de texto que se escreve no Bloco de Notas, uma linha por video:

    # linha que comeca com # e comentario
    abertura.mp4      | Ninguem te contou isso
    receita-bolo.mp4  | O segredo esta no ponto da calda

**O que este modulo NAO faz:** nao le disco e nao edita nada. Recebe o texto do
roteiro e a lista de nomes de arquivo que alguem ja encontrou, e devolve o
pareamento. E funcao pura — da para conferir os 20 jeitos de errar uma linha
sem ter um mp4 na maquina.

**O erro que ele existe para pegar:** digitar o nome do arquivo errado. Numa
lista de 50 linhas isso vai acontecer, e o sintoma sem este modulo seria um
video sair sem headline sem ninguem avisar. Aqui o descompasso e devolvido
**nos dois sentidos** — video sem headline e headline sem video.
"""

SEPARADOR = "|"
COMENTARIO = "#"

# As extensoes que o editor aceita. Serve para duas coisas: varrer a pasta e
# aceitar que a pessoa escreva o nome com ou sem extensao no roteiro.
EXTENSOES_DE_VIDEO = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


def _sem_extensao(nome):
    """'Abertura.MP4' -> 'abertura'. Extensao desconhecida fica como esta."""
    limpo = (nome or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    for extensao in EXTENSOES_DE_VIDEO:
        if limpo.lower().endswith(extensao):
            return limpo[: -len(extensao)].lower()
    return limpo.lower()


def ler(texto):
    """Texto do roteiro -> (entradas, problemas).

    `entradas` e uma lista de `(nome_escrito, headline)` na ordem do arquivo.
    `problemas` traz a linha crua e o motivo, para reclamar com numero de linha
    em vez de ignorar calado.

    Repetir o mesmo arquivo duas vezes e problema, nao ultima-vence: numa lista
    escrita a mao, linha duplicada quase sempre e copiar-e-colar esquecido.
    """
    entradas = []
    problemas = []
    ja_vistos = {}

    for numero, linha in enumerate((texto or "").splitlines(), start=1):
        crua = linha.strip()
        if not crua or crua.startswith(COMENTARIO):
            continue

        if SEPARADOR not in crua:
            problemas.append((numero, crua,
                              "falta o '%s' separando arquivo e texto"
                              % SEPARADOR))
            continue

        nome, headline = crua.split(SEPARADOR, 1)
        nome = nome.strip()
        headline = headline.strip()

        if not nome:
            problemas.append((numero, crua, "linha sem nome de arquivo"))
            continue
        if not headline:
            problemas.append((numero, crua, "linha sem texto de headline"))
            continue

        chave = _sem_extensao(nome)
        if chave in ja_vistos:
            problemas.append((numero, crua,
                              "'%s' ja apareceu na linha %d"
                              % (nome, ja_vistos[chave])))
            continue

        ja_vistos[chave] = numero
        entradas.append((nome, headline))

    return entradas, problemas


def parear(arquivos, entradas):
    """Casa os nomes de arquivo com as headlines. Devolve os tres resultados.

    - `pares`: `{nome_do_arquivo: headline}`, com o nome **como esta no disco**
    - `sem_headline`: video encontrado que ninguem escreveu no roteiro
    - `sem_video`: headline escrita para um arquivo que nao existe na pasta

    O pareamento ignora maiusculas e extensao, porque quem digita a lista nao
    tem obrigacao de lembrar se gravou `.mp4` ou `.MOV`.
    """
    por_chave = {}
    for nome in arquivos:
        por_chave.setdefault(_sem_extensao(nome), nome)

    pares = {}
    sem_video = []

    for nome_escrito, headline in entradas:
        chave = _sem_extensao(nome_escrito)
        if chave in por_chave:
            pares[por_chave[chave]] = headline
        else:
            sem_video.append(nome_escrito)

    sem_headline = [nome for nome in arquivos if nome not in pares]
    return pares, sem_headline, sem_video


def e_video(nome):
    """O arquivo tem cara de video? Usado para varrer a pasta."""
    return (nome or "").lower().endswith(EXTENSOES_DE_VIDEO)


def resumir_problemas(problemas, sem_video):
    """As reclamacoes em texto pronto para imprimir. Vazio = nada a dizer."""
    linhas = []
    for numero, crua, motivo in problemas:
        linhas.append("  linha %d: %s  (%s)" % (numero, crua, motivo))
    for nome in sem_video:
        linhas.append("  '%s' esta no roteiro mas nao existe na pasta" % nome)
    return linhas
