"""Peças compartilhadas pelos repositórios.

Um repositório aqui é um módulo de funções, não uma classe. O motivo é
consistência: o resto do projeto (`banco.py`, `metricas.py`, `consultas.py`)
já é feito de funções que recebem a conexão, e inventar hierarquia de classes
só nesta camada tornaria o código mais estranho, não mais organizado.

**A fronteira de idioma mora aqui.** O código Python fala português, o banco
fala inglês. Quem traduz é o repositório — nenhum outro módulo escreve SQL,
e nenhum módulo de domínio precisa saber que a coluna se chama `followers`.
"""


class ErroDeRepositorio(Exception):
    """Operação inválida antes de chegar ao banco. Mensagem pronta."""


def um(cursor):
    """A primeira linha, ou None. Poupa o `.fetchone()` repetido."""
    linha = cursor.fetchone()
    return linha


def id_de(cursor):
    """O `id` devolvido por um RETURNING. Erro claro se não veio nada."""
    linha = cursor.fetchone()
    if linha is None:
        raise ErroDeRepositorio(
            "A gravação não devolveu id. Quase sempre é um ON CONFLICT que "
            "não casou com nenhuma constraint — confira a chave natural.")
    return linha[0]


def dicts(cursor, colunas):
    """Linhas como dicionários, com os nomes de coluna informados."""
    return [dict(zip(colunas, linha)) for linha in cursor.fetchall()]


def exigir(valor, campo):
    """Campo obrigatório que veio vazio vira erro nomeado, não NOT NULL cru."""
    if valor in (None, ""):
        raise ErroDeRepositorio("O campo '%s' é obrigatório e veio vazio." % campo)
    return valor


def booleano(valor):
    """None continua None. **Isto importa.**

    `bool(None)` é `False`, e `False` afirma "não é verificado". `None` diz
    "não sabemos". Num banco onde metade dos campos pode não vir da fonte, a
    diferença entre as duas afirmações é o projeto inteiro.
    """
    return None if valor is None else bool(valor)
