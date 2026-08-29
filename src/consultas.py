"""As perguntas que se faz ao banco.

Cada função aqui é uma pergunta que, antes do banco, exigiria código novo.
Todas devolvem lista de dicionários, prontos para o relatório ou para a tela.

Escrita fica em `banco.py`. Aqui só se lê.
"""


def _linhas(cursor):
    return [dict(linha) for linha in cursor.fetchall()]


def hashtags_por_desempenho(conexao, minimo_de_posts=2, limite=30):
    """A pergunta central: qual hashtag anda junto com bom desempenho.

    Cruza a tag com engajamento, curtidas e visualizações. Tag que aparece
    uma vez só é ruído — daí o `minimo_de_posts`.
    """
    return _linhas(conexao.execute("""
        SELECT h.tag                              AS tag,
               COUNT(DISTINCT h.post_id)          AS posts,
               ROUND(AVG(m.engajamento), 3)       AS media_engajamento,
               CAST(AVG(p.curtidas) AS INTEGER)   AS media_curtidas,
               CAST(AVG(p.comentarios) AS INTEGER) AS media_comentarios,
               CAST(AVG(p.visualizacoes) AS INTEGER) AS media_visualizacoes,
               COUNT(DISTINCT p.usuario)          AS perfis_que_usam
          FROM hashtags h
          JOIN posts    p ON p.id = h.post_id
     LEFT JOIN metricas m ON m.post_id = h.post_id
      GROUP BY h.tag
        HAVING posts >= ?
      ORDER BY media_engajamento DESC NULLS LAST, media_curtidas DESC
         LIMIT ?
    """, (minimo_de_posts, limite)))


def melhores_posts(conexao, limite=20, usuario=None, so_video=False):
    """Os posts que mais engajaram — a fila de candidatos para editar."""
    condicoes = []
    parametros = []
    if usuario:
        condicoes.append("p.usuario = ?")
        parametros.append(usuario)
    if so_video:
        condicoes.append("p.e_video = 1")
    onde = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    parametros.append(limite)

    return _linhas(conexao.execute("""
        SELECT p.id, p.usuario, p.link, p.tipo, p.duracao, p.curtidas,
               p.comentarios, p.visualizacoes, p.hora, p.dia_semana,
               p.caminho_midia,
               m.engajamento, m.ritmo_ppm, m.gancho_falado, m.gancho_escrito,
               m.tem_cta, m.tipos_cta,
               (t.post_id IS NOT NULL) AS tem_transcricao
          FROM posts p
     LEFT JOIN metricas     m ON m.post_id = p.id
     LEFT JOIN transcricoes t ON t.post_id = p.id
          %s
      ORDER BY m.engajamento DESC NULLS LAST
         LIMIT ?
    """ % onde, parametros))


def ranking_de_perfis(conexao):
    """Quem engaja mais, proporcionalmente ao tamanho."""
    return _linhas(conexao.execute("""
        SELECT pf.usuario, pf.seguidores, pf.posts AS posts_no_perfil,
               COUNT(p.id)                        AS posts_coletados,
               ROUND(AVG(m.engajamento), 3)       AS media_engajamento,
               CAST(AVG(p.curtidas) AS INTEGER)   AS media_curtidas,
               ROUND(AVG(p.duracao), 1)           AS media_duracao
          FROM perfis pf
     LEFT JOIN posts    p ON p.usuario = pf.usuario
     LEFT JOIN metricas m ON m.post_id = p.id
      GROUP BY pf.usuario
      ORDER BY media_engajamento DESC NULLS LAST
    """))


def horarios_que_rendem(conexao):
    """Faixa de horário contra engajamento médio."""
    return _linhas(conexao.execute("""
        SELECT SUBSTR(p.hora, 1, 2) || 'h'   AS faixa,
               COUNT(*)                      AS posts,
               ROUND(AVG(m.engajamento), 3)  AS media_engajamento
          FROM posts p
     LEFT JOIN metricas m ON m.post_id = p.id
         WHERE p.hora IS NOT NULL AND p.hora <> ''
      GROUP BY faixa
      ORDER BY media_engajamento DESC NULLS LAST
    """))


def formatos_que_rendem(conexao):
    """Reels, carrossel ou foto — qual engaja mais."""
    return _linhas(conexao.execute("""
        SELECT p.tipo,
               COUNT(*)                      AS posts,
               ROUND(AVG(m.engajamento), 3)  AS media_engajamento,
               ROUND(AVG(p.duracao), 1)      AS media_duracao
          FROM posts p
     LEFT JOIN metricas m ON m.post_id = p.id
      GROUP BY p.tipo
      ORDER BY media_engajamento DESC NULLS LAST
    """))


def procurar_no_falado(conexao, termo, limite=20):
    """Busca uma palavra dentro de todas as transcrições de uma vez (FTS5).

    Ex.: quais vídeos falam "bônus", e quanto eles engajaram.
    """
    return _linhas(conexao.execute("""
        SELECT f.post_id, p.usuario, p.link, m.engajamento,
               snippet(transcricoes_fts, 1, '[', ']', '...', 12) AS trecho
          FROM transcricoes_fts f
          JOIN posts    p ON p.id = f.post_id
     LEFT JOIN metricas m ON m.post_id = f.post_id
         WHERE transcricoes_fts MATCH ?
      ORDER BY m.engajamento DESC NULLS LAST
         LIMIT ?
    """, (termo, limite)))


def ganchos_dos_melhores(conexao, limite=15):
    """O que é dito nos primeiros segundos dos vídeos que mais engajaram."""
    return _linhas(conexao.execute("""
        SELECT p.usuario, p.link, m.engajamento, m.gancho_falado, m.gancho_escrito,
               p.duracao
          FROM metricas m
          JOIN posts p ON p.id = m.post_id
         WHERE m.gancho_falado IS NOT NULL AND m.gancho_falado <> ''
      ORDER BY m.engajamento DESC NULLS LAST
         LIMIT ?
    """, (limite,)))


def hashtags_compartilhadas(conexao, minimo_de_perfis=2, limite=30):
    """Tags que mais de um perfil usa — quem está copiando quem."""
    return _linhas(conexao.execute("""
        SELECT h.tag,
               COUNT(DISTINCT p.usuario) AS perfis,
               COUNT(DISTINCT h.post_id) AS posts,
               GROUP_CONCAT(DISTINCT p.usuario) AS quais
          FROM hashtags h
          JOIN posts p ON p.id = h.post_id
      GROUP BY h.tag
        HAVING perfis >= ?
      ORDER BY perfis DESC, posts DESC
         LIMIT ?
    """, (minimo_de_perfis, limite)))


def chamadas_que_rendem(conexao):
    """Post com chamada para ação engaja mais do que post sem?"""
    return _linhas(conexao.execute("""
        SELECT CASE m.tem_cta WHEN 1 THEN 'com chamada' ELSE 'sem chamada' END AS grupo,
               COUNT(*)                      AS posts,
               ROUND(AVG(m.engajamento), 3)  AS media_engajamento,
               CAST(AVG(p.comentarios) AS INTEGER) AS media_comentarios
          FROM metricas m
          JOIN posts p ON p.id = m.post_id
      GROUP BY m.tem_cta
      ORDER BY media_engajamento DESC NULLS LAST
    """))


def palavras_do_post(conexao, post_id):
    """Cada palavra com seu segundo — é o que a legenda animada consome."""
    return _linhas(conexao.execute("""
        SELECT indice, palavra, inicio, fim
          FROM palavras
         WHERE post_id = ?
      ORDER BY indice
    """, (post_id,)))


def cobertura(conexao):
    """O que já foi feito e o que falta. Serve para saber onde a esteira parou."""
    linha = conexao.execute("""
        SELECT (SELECT COUNT(*) FROM perfis)                       AS perfis,
               (SELECT COUNT(*) FROM posts)                        AS posts,
               (SELECT COUNT(*) FROM posts WHERE e_video = 1)      AS videos,
               (SELECT COUNT(*) FROM transcricoes)                 AS transcritos,
               (SELECT COUNT(*) FROM metricas)                     AS analisados,
               (SELECT COUNT(*) FROM edicoes)                      AS editados,
               (SELECT COUNT(*) FROM posts
                 WHERE visualizacoes IS NOT NULL)                  AS com_visualizacoes
    """).fetchone()
    return dict(linha)
