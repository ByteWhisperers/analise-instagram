"""A série temporal das métricas de conteúdo.

A tabela mais importante do sistema, e a razão é uma só: **velocidade e
aceleração são diferença entre duas leituras.** Guardar só o valor corrente
responde "quantas views tem"; guardar a série responde "está subindo, e quão
rápido" — que é a pergunta que interessa.

Nada de métrica derivada aqui. `views_per_hour` não é coluna porque o valor
depende de *quando* foi medido: congelá-lo guardaria uma resposta que
envelhece. Grava-se o número cru com a hora, e a conta é de leitura.

E a regra que atravessa o projeto: **métrica que a plataforma não publica é
NULL, nunca 0.** `shares = 0` afirma que ninguém compartilhou; `NULL` admite
que o Instagram não conta isso em público. Confundir os dois envenena toda
média calculada depois.
"""

from ._comum import exigir


def gravar_snapshot(conexao, conteudo_id, post, horas_desde_post=None,
                    job_id=None, medido_em=None):
    """Uma leitura dos números. Duas no mesmo instante não viram duas linhas."""
    exigir(conteudo_id, "conteudo_id")

    conexao.execute(
        """
        INSERT INTO content_metric_snapshots (
            content_id, collected_at, hours_since_published,
            views, likes, comments_count, shares, saves, plays, job_id)
        VALUES (%s, COALESCE(%s, now()), %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_id, collected_at) DO UPDATE SET
            hours_since_published = EXCLUDED.hours_since_published,
            views          = EXCLUDED.views,
            likes          = EXCLUDED.likes,
            comments_count = EXCLUDED.comments_count,
            shares         = EXCLUDED.shares,
            saves          = EXCLUDED.saves,
            plays          = EXCLUDED.plays
        """,
        (conteudo_id, medido_em, horas_desde_post,
         post.get("visualizacoes"),
         post.get("curtidas"),
         post.get("comentarios"),
         post.get("compartilhamentos"),
         post.get("salvamentos"),
         post.get("plays"),
         job_id))


def historico(conexao, conteudo_id):
    """As leituras, da mais velha para a mais nova."""
    cursor = conexao.execute(
        """
        SELECT collected_at, hours_since_published, views, likes,
               comments_count, shares, saves
        FROM content_metric_snapshots WHERE content_id = %s
        ORDER BY collected_at
        """,
        (conteudo_id,))
    return [{"medido_em": linha[0].isoformat(), "horas": linha[1],
             "visualizacoes": linha[2], "curtidas": linha[3],
             "comentarios": linha[4], "compartilhamentos": linha[5],
             "salvamentos": linha[6]}
            for linha in cursor.fetchall()]


def ultima(conexao, conteudo_id):
    """A leitura mais recente, ou None se nunca houve nenhuma."""
    linhas = historico(conexao, conteudo_id)
    return linhas[-1] if linhas else None


def para_desempenho(conexao, conteudo_ids=None, nicho_id=None, limite=500):
    """Os posts no formato que `desempenho.py` consome.

    Junta o último snapshot de cada conteúdo com os dados do post e do dono.
    As chaves saem em português de propósito: `desempenho.py` é código de
    domínio e não conhece o esquema do banco.

    `DISTINCT ON` é específico do PostgreSQL e é o jeito barato de pegar "a
    linha mais recente por grupo" sem subconsulta correlacionada.
    """
    sql = """
        SELECT DISTINCT ON (c.id)
               c.id, c.platform_content_id, c.caption, c.published_at,
               c.content_type, c.duration_seconds, c.audio_title,
               p.username, p.followers,
               s.views, s.likes, s.comments_count, s.shares, s.saves
        FROM contents c
        JOIN profiles p ON p.id = c.profile_id
        LEFT JOIN content_metric_snapshots s ON s.content_id = c.id
    """
    condicoes, parametros = ["c.content_type IN ('reel', 'video')"], []

    if conteudo_ids:
        condicoes.append("c.id = ANY(%s)")
        parametros.append(list(conteudo_ids))

    if nicho_id:
        sql += " JOIN niche_profiles np ON np.profile_id = p.id "
        condicoes.append("np.niche_id = %s")
        parametros.append(nicho_id)

    sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY c.id, s.collected_at DESC NULLS LAST LIMIT %s"
    parametros.append(limite)

    saida = []
    for linha in conexao.execute(sql, parametros).fetchall():
        (cid, codigo, legenda, publicado, tipo, duracao, audio,
         usuario, seguidores, views, curtidas, comentarios, shares, saves) = linha
        saida.append({
            "id": codigo,
            "content_id": cid,
            "perfil": usuario,
            "seguidores": seguidores,
            "legenda": legenda or "",
            "data_utc": publicado.isoformat() if publicado else None,
            "tipo": tipo,
            "duracao_segundos": duracao,
            "audio_titulo": audio,
            "visualizacoes": views,
            "curtidas": curtidas,
            "comentarios": comentarios,
            "compartilhamentos": shares,
            "salvamentos": saves,
        })
    return saida


def cobertura(conexao):
    """Onde a esteira parou. Serve de diagnóstico rápido."""
    perguntas = {
        "nichos": "SELECT count(*) FROM niches",
        "perfis": "SELECT count(*) FROM profiles",
        "conteudos": "SELECT count(*) FROM contents",
        "videos": "SELECT count(*) FROM contents "
                  "WHERE content_type IN ('reel','video')",
        "com_metrica": "SELECT count(DISTINCT content_id) "
                       "FROM content_metric_snapshots",
        "com_views": "SELECT count(DISTINCT content_id) "
                     "FROM content_metric_snapshots WHERE views IS NOT NULL",
        "medicoes": "SELECT count(*) FROM content_metric_snapshots",
        "baixados": "SELECT count(*) FROM media_assets WHERE asset_type = 'video'",
    }
    return {chave: conexao.execute(sql).fetchone()[0]
            for chave, sql in perguntas.items()}
