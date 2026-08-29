"""Nichos monitorados.

Um nicho é o ponto de partida do funil: você informa um, e dele saem perfis,
conteúdos e tudo o mais. É a única entidade que nasce de decisão humana e não
de coleta.
"""

from ._comum import dicts, exigir, id_de

COLUNAS = ("id", "name", "description", "keywords", "language", "country",
           "status", "created_at", "updated_at")


def obter_ou_criar(conexao, nome, descricao=None, palavras_chave=None,
                   idioma=None, pais=None):
    """Devolve o id do nicho, criando se ainda não existir.

    Idempotente pelo nome: rodar a descoberta duas vezes com o mesmo termo
    não cria dois nichos. O `DO UPDATE` existe só para o `RETURNING` sempre
    devolver linha — com `DO NOTHING`, um conflito devolveria vazio.
    """
    exigir(nome, "nome")

    cursor = conexao.execute(
        """
        INSERT INTO niches (name, description, keywords, language, country)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            description = COALESCE(EXCLUDED.description, niches.description),
            keywords    = CASE WHEN cardinality(EXCLUDED.keywords) > 0
                               THEN EXCLUDED.keywords ELSE niches.keywords END,
            language    = COALESCE(EXCLUDED.language, niches.language),
            country     = COALESCE(EXCLUDED.country, niches.country)
        RETURNING id
        """,
        (nome, descricao, list(palavras_chave or []), idioma, pais))

    return id_de(cursor)


def por_nome(conexao, nome):
    """O nicho inteiro, ou None."""
    cursor = conexao.execute(
        "SELECT %s FROM niches WHERE name = %%s" % ", ".join(COLUNAS), (nome,))
    linhas = dicts(cursor, COLUNAS)
    return linhas[0] if linhas else None


def listar(conexao, status="active"):
    """Os nichos, do mais novo para o mais antigo. `status=None` traz todos."""
    sql = "SELECT %s FROM niches" % ", ".join(COLUNAS)
    parametros = ()

    if status:
        sql += " WHERE status = %s"
        parametros = (status,)

    sql += " ORDER BY created_at DESC"
    return dicts(conexao.execute(sql, parametros), COLUNAS)


def mudar_status(conexao, nicho_id, status):
    """`active`, `paused` ou `archived`. Outro valor o CHECK recusa."""
    conexao.execute("UPDATE niches SET status = %s WHERE id = %s",
                    (status, nicho_id))


def contar_perfis(conexao, nicho_id):
    linha = conexao.execute(
        "SELECT count(*) FROM niche_profiles WHERE niche_id = %s",
        (nicho_id,)).fetchone()
    return linha[0]
