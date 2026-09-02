"""Análises de conteúdo e de comentário, guardadas em JSONB versionado.

Uma coisa que merece ser dita alto: **`content_analyses` não serve só para
LLM.** O campo `model` guarda *quem* produziu a análise, e as contas
determinísticas de `metricas.py` são um produtor tão legítimo quanto um
modelo de linguagem. Gravar as duas na mesma tabela, com `model` diferente,
permite comparar uma com a outra depois — que é exatamente o teste de saber
se o LLM vale o dinheiro.

`analysis_version` + `model` existem para permitir reprocessar quando a regra
ou o modelo mudarem. Sem eles não há como saber qual análise veio de qual
prompt, e a base vira um amontoado de opiniões sem procedência.
"""

import json

from ._comum import dicts, exigir, id_de

# Quem produziu a análise. O primeiro não custa nada e não chama ninguém.
DETERMINISTICO = "metricas.py"

COLUNAS = ("id", "content_id", "analysis_version", "model", "analysis",
           "created_at")


def salvar_do_conteudo(conexao, conteudo_id, analise, modelo=DETERMINISTICO,
                       versao="v1"):
    """Grava a análise de um vídeo. Regravar com o mesmo (versão, modelo)
    substitui — reprocessar não acumula lixo."""
    exigir(conteudo_id, "conteudo_id")

    cursor = conexao.execute(
        """
        INSERT INTO content_analyses
            (content_id, analysis_version, model, analysis)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (content_id, analysis_version, model) DO UPDATE SET
            analysis = EXCLUDED.analysis, created_at = now()
        RETURNING id
        """,
        (conteudo_id, versao, modelo,
         json.dumps(analise, ensure_ascii=False, default=str)))
    return id_de(cursor)


def salvar_dos_comentarios(conexao, conteudo_id, analise, modelo,
                           versao="v1", amostrados=None):
    exigir(conteudo_id, "conteudo_id")

    cursor = conexao.execute(
        """
        INSERT INTO comment_analyses
            (content_id, analysis_version, model, analysis, comments_sampled)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (content_id, analysis_version, model) DO UPDATE SET
            analysis = EXCLUDED.analysis,
            comments_sampled = EXCLUDED.comments_sampled,
            created_at = now()
        RETURNING id
        """,
        (conteudo_id, versao, modelo,
         json.dumps(analise, ensure_ascii=False, default=str), amostrados))
    return id_de(cursor)


def do_conteudo(conexao, conteudo_id, modelo=None, versao=None):
    """A análise mais recente que casar com o filtro, ou None."""
    sql = ("SELECT %s FROM content_analyses WHERE content_id = %%s"
           % ", ".join(COLUNAS))
    parametros = [conteudo_id]

    if modelo:
        sql += " AND model = %s"
        parametros.append(modelo)
    if versao:
        sql += " AND analysis_version = %s"
        parametros.append(versao)

    sql += " ORDER BY created_at DESC LIMIT 1"
    linhas = dicts(conexao.execute(sql, parametros), COLUNAS)
    return linhas[0] if linhas else None


def campo(conexao, conteudo_id, chave, modelo=DETERMINISTICO):
    """Um campo de dentro do JSONB, sem trazer a análise inteira."""
    linha = conexao.execute(
        "SELECT analysis -> %s FROM content_analyses "
        "WHERE content_id = %s AND model = %s "
        "ORDER BY created_at DESC LIMIT 1",
        (chave, conteudo_id, modelo)).fetchone()
    return linha[0] if linha else None


def sem_analise(conexao, modelo=DETERMINISTICO, limite=200):
    """Os vídeos que ainda não foram analisados por este produtor.

    É o que alimenta a fila: analisar de novo o que já foi analisado é
    desperdício, e quando o produtor for um LLM é desperdício pago.
    """
    cursor = conexao.execute(
        """
        SELECT c.id, c.platform_content_id
        FROM contents c
        WHERE c.content_type IN ('reel', 'video')
          AND NOT EXISTS (SELECT 1 FROM content_analyses a
                          WHERE a.content_id = c.id AND a.model = %s)
        ORDER BY c.published_at DESC NULLS LAST
        LIMIT %s
        """,
        (modelo, limite))
    return [{"content_id": l[0], "codigo": l[1]} for l in cursor.fetchall()]


def todas_do_modelo(conexao, modelo, versao=None, limite=500):
    """Todas as análises deste produtor. É o que alimenta a faixa do conjunto.

    Traz o JSONB inteiro de propósito: quem agrega é função pura em Python, e
    espalhar a agregação em SQL tiraria dela o teste sem banco.
    """
    sql = ("SELECT content_id, analysis_version, analysis FROM content_analyses "
           "WHERE model = %s")
    parametros = [modelo]
    if versao:
        sql += " AND analysis_version = %s"
        parametros.append(versao)
    sql += " ORDER BY created_at DESC LIMIT %s"
    parametros.append(limite)

    return [{"conteudo_id": l[0], "versao": l[1], "analise": l[2]}
            for l in conexao.execute(sql, parametros)]


def comparar_modelos(conexao, conteudo_id):
    """As análises do mesmo vídeo, por produtor.

    Existe para responder se o LLM entrega algo que a conta determinística
    não entregava — antes de aceitar a fatura dele como permanente.
    """
    cursor = conexao.execute(
        "SELECT model, analysis_version, analysis, created_at "
        "FROM content_analyses WHERE content_id = %s ORDER BY model, created_at",
        (conteudo_id,))
    return [{"modelo": l[0], "versao": l[1], "analise": l[2], "quando": l[3]}
            for l in cursor.fetchall()]
