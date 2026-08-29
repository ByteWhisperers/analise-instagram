"""As perguntas que se faz ao banco. **Só leitura.**

Escrita mora nos outros módulos de `repos/`. Aqui nada é gravado, nada é
alterado — o que torna seguro chamar qualquer coisa daqui sem medo.

Quase tudo se apoia na view `v_content_current` (migration 003), que entrega
conteúdo + dono + a leitura mais recente das métricas, com o engajamento já
calculado e **a base dele declarada**.

Ordenação: quase toda consulta usa `NULLS LAST`. Sem isso o PostgreSQL põe
`NULL` no topo do `DESC`, e o ranking abriria com os posts sobre os quais não
se sabe nada — o oposto do que se quer ver.
"""


def _filtro_de_nicho(nicho_id, alias="v"):
    """O `JOIN` e a condição de nicho, ou nada. Evita repetir em cada consulta."""
    if not nicho_id:
        return "", "", []
    return (" JOIN niche_profiles np ON np.profile_id = %s.profile_id" % alias,
            " AND np.niche_id = %s", [nicho_id])


def hashtags_por_desempenho(conexao, minimo_de_posts=2, limite=30, nicho_id=None):
    """Qual hashtag aparece nos conteúdos que mais engajam.

    Descarta tag que aparece em um post só: com uma amostra, "média" é só o
    próprio valor, e um viral isolado colocaria uma tag aleatória em primeiro.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT h.tag,
               count(*)                        AS posts,
               round(avg(v.engagement) * 100, 3) AS engajamento_medio,
               round(avg(v.views))             AS views_medio,
               max(v.views)                    AS views_maximo
        FROM content_hashtags h
        JOIN v_content_current v ON v.content_id = h.content_id
        %s
        WHERE v.engagement IS NOT NULL %s
        GROUP BY h.tag
        HAVING count(*) >= %%s
        ORDER BY avg(v.engagement) DESC NULLS LAST
        LIMIT %%s
    """ % (juncao, condicao)

    return [{"tag": l[0], "posts": l[1], "engajamento_medio": float(l[2] or 0),
             "views_medio": int(l[3]) if l[3] is not None else None,
             "views_maximo": l[4]}
            for l in conexao.execute(sql, parametros + [minimo_de_posts, limite])]


def melhores_posts(conexao, limite=20, usuario=None, so_video=False,
                   nicho_id=None):
    """Os conteúdos de maior engajamento, com a base declarada."""
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT v.code, v.username, v.content_type, v.views, v.likes,
               v.comments_count, round(v.engagement * 100, 3), v.engagement_base,
               v.published_at, left(coalesce(v.caption, ''), 80)
        FROM v_content_current v %s
        WHERE v.engagement IS NOT NULL %s
    """ % (juncao, condicao)

    if usuario:
        sql += " AND v.username = %s"
        parametros.append(usuario)
    if so_video:
        sql += " AND v.content_type IN ('reel', 'video')"

    sql += " ORDER BY v.engagement DESC NULLS LAST LIMIT %s"
    parametros.append(limite)

    return [{"post": l[0], "perfil": l[1], "tipo": l[2], "visualizacoes": l[3],
             "curtidas": l[4], "comentarios": l[5],
             "engajamento": float(l[6] or 0), "base": l[7],
             "publicado": l[8].isoformat() if l[8] else None, "legenda": l[9]}
            for l in conexao.execute(sql, parametros)]


def ranking_de_perfis(conexao, nicho_id=None):
    """Os perfis pelo engajamento médio dos conteúdos deles.

    Note que o maior perfil raramente é o primeiro: engajamento é razão, e
    conta grande costuma ter razão menor. É de propósito.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT v.username, max(v.followers), count(*),
               round(avg(v.engagement) * 100, 3), round(avg(v.views)),
               count(*) FILTER (WHERE v.content_type IN ('reel','video'))
        FROM v_content_current v %s
        WHERE 1 = 1 %s
        GROUP BY v.username
        ORDER BY avg(v.engagement) DESC NULLS LAST
    """ % (juncao, condicao)

    return [{"perfil": l[0], "seguidores": l[1], "posts": l[2],
             "engajamento_medio": float(l[3]) if l[3] is not None else None,
             "views_medio": int(l[4]) if l[4] is not None else None,
             "videos": l[5]}
            for l in conexao.execute(sql, parametros)]


def horarios_que_rendem(conexao, nicho_id=None):
    """Faixa de horário de publicação × engajamento.

    A hora sai em `America/Sao_Paulo` e não em UTC: a pergunta é sobre o
    hábito de quem assiste, e ninguém assiste em UTC.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT EXTRACT(HOUR FROM v.published_at AT TIME ZONE 'America/Sao_Paulo')::int,
               count(*), round(avg(v.engagement) * 100, 3), round(avg(v.views))
        FROM v_content_current v %s
        WHERE v.published_at IS NOT NULL %s
        GROUP BY 1 ORDER BY 1
    """ % (juncao, condicao)

    return [{"hora": l[0], "posts": l[1],
             "engajamento_medio": float(l[2]) if l[2] is not None else None,
             "views_medio": int(l[3]) if l[3] is not None else None}
            for l in conexao.execute(sql, parametros)]


def dias_que_rendem(conexao, nicho_id=None):
    """Dia da semana × engajamento. Mesmo fuso, mesmo motivo."""
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT to_char(v.published_at AT TIME ZONE 'America/Sao_Paulo', 'Day'),
               EXTRACT(DOW FROM v.published_at AT TIME ZONE 'America/Sao_Paulo')::int,
               count(*), round(avg(v.engagement) * 100, 3)
        FROM v_content_current v %s
        WHERE v.published_at IS NOT NULL %s
        GROUP BY 1, 2 ORDER BY 2
    """ % (juncao, condicao)

    return [{"dia": l[0].strip(), "numero": l[1], "posts": l[2],
             "engajamento_medio": float(l[3]) if l[3] is not None else None}
            for l in conexao.execute(sql, parametros)]


def formatos_que_rendem(conexao, nicho_id=None):
    """Reel, carrossel ou foto: qual engaja mais."""
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT v.content_type, count(*), round(avg(v.engagement) * 100, 3),
               round(avg(v.views)), round(avg(v.duration_seconds)::numeric, 1)
        FROM v_content_current v %s
        WHERE 1 = 1 %s
        GROUP BY v.content_type
        ORDER BY avg(v.engagement) DESC NULLS LAST
    """ % (juncao, condicao)

    return [{"tipo": l[0], "posts": l[1],
             "engajamento_medio": float(l[2]) if l[2] is not None else None,
             "views_medio": int(l[3]) if l[3] is not None else None,
             "duracao_media": float(l[4]) if l[4] is not None else None}
            for l in conexao.execute(sql, parametros)]


def audios_em_alta(conexao, minimo_de_perfis=2, limite=20, nicho_id=None):
    """Qual áudio aparece em vários perfis do mesmo nicho.

    Sinal forte de tendência: um som que dois ou três concorrentes usam na
    mesma semana costuma anteceder o pico, e não segui-lo.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT v.audio_title, v.audio_id,
               count(DISTINCT v.username) AS perfis, count(*) AS posts,
               round(avg(v.engagement) * 100, 3)
        FROM v_content_current v %s
        WHERE v.audio_id IS NOT NULL %s
        GROUP BY v.audio_title, v.audio_id
        HAVING count(DISTINCT v.username) >= %%s
        ORDER BY count(DISTINCT v.username) DESC, avg(v.engagement) DESC NULLS LAST
        LIMIT %%s
    """ % (juncao, condicao)

    return [{"audio": l[0], "audio_id": l[1], "perfis": l[2], "posts": l[3],
             "engajamento_medio": float(l[4]) if l[4] is not None else None}
            for l in conexao.execute(sql,
                                     parametros + [minimo_de_perfis, limite])]


def hashtags_compartilhadas(conexao, minimo_de_perfis=2, limite=30,
                            nicho_id=None):
    """Quais tags mais de um perfil usa — quem copia quem."""
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT h.tag, count(DISTINCT v.username) AS perfis, count(*) AS posts,
               string_agg(DISTINCT v.username, ', ' ORDER BY v.username)
        FROM content_hashtags h
        JOIN v_content_current v ON v.content_id = h.content_id
        %s
        WHERE 1 = 1 %s
        GROUP BY h.tag
        HAVING count(DISTINCT v.username) >= %%s
        ORDER BY count(DISTINCT v.username) DESC, count(*) DESC
        LIMIT %%s
    """ % (juncao, condicao)

    return [{"tag": l[0], "perfis": l[1], "posts": l[2], "quem": l[3]}
            for l in conexao.execute(sql,
                                     parametros + [minimo_de_perfis, limite])]


def ganchos_dos_melhores(conexao, limite=15, nicho_id=None):
    """A primeira linha da legenda e o falado nos 3 primeiros segundos.

    A primeira linha importa porque é a única que o Instagram mostra sem
    clicar em "mais".
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT v.code, v.username, round(v.engagement * 100, 3),
               split_part(coalesce(v.caption, ''), E'\\n', 1),
               -- UMA transcrição, a mais recente. Sem este `LIMIT 1`, um
               -- vídeo transcrito com dois modelos somaria os trechos dos
               -- dois e devolveria o gancho repetido.
               (SELECT string_agg(s.text, ' ' ORDER BY s.idx)
                  FROM transcript_segments s
                 WHERE s.start_seconds < 3.0
                   AND s.transcript_id = (SELECT t.id FROM transcripts t
                                           WHERE t.content_id = v.content_id
                                           ORDER BY t.created_at DESC, t.id DESC
                                           LIMIT 1))
        FROM v_content_current v %s
        WHERE v.engagement IS NOT NULL %s
        ORDER BY v.engagement DESC NULLS LAST
        LIMIT %%s
    """ % (juncao, condicao)

    return [{"post": l[0], "perfil": l[1], "engajamento": float(l[2] or 0),
             "gancho_escrito": (l[3] or "").strip(),
             "gancho_falado": (l[4] or "").strip()}
            for l in conexao.execute(sql, parametros + [limite])]


def chamadas_que_rendem(conexao, nicho_id=None, modelo="metricas.py"):
    """Tipo de chamada para ação × engajamento.

    Lê de `content_analyses`, onde a análise determinística grava o que
    encontrou. Se ainda não houve análise, devolve lista vazia — e não zero,
    que fingiria que nenhum post tem CTA.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id)

    sql = """
        SELECT jsonb_array_elements_text(a.analysis -> 'chamadas') AS chamada,
               count(*), round(avg(v.engagement) * 100, 3)
        FROM content_analyses a
        JOIN v_content_current v ON v.content_id = a.content_id
        %s
        WHERE a.model = %%s
          AND jsonb_typeof(a.analysis -> 'chamadas') = 'array' %s
        GROUP BY 1
        ORDER BY avg(v.engagement) DESC NULLS LAST
    """ % (juncao, condicao)

    return [{"chamada": l[0], "posts": l[1],
             "engajamento_medio": float(l[2]) if l[2] is not None else None}
            for l in conexao.execute(sql, [modelo] + parametros)]


def crescimento_dos_perfis(conexao, nicho_id=None, dias=7):
    """Crescimento de seguidores no período, por perfil.

    Só aparece quem tem **duas** leituras no intervalo. Perfil com uma
    leitura só é omitido em vez de aparecer com zero — zero afirmaria que
    não cresceu, e a verdade é que não se sabe.
    """
    juncao, condicao, parametros = _filtro_de_nicho(nicho_id, alias="p2")
    juncao = juncao.replace("p2.profile_id", "p.id")

    sql = """
        WITH janela AS (
            SELECT s.profile_id,
                   first_value(s.followers) OVER w AS antes,
                   last_value(s.followers)  OVER w AS agora,
                   count(*)                 OVER (PARTITION BY s.profile_id) AS leituras
            FROM profile_snapshots s
            WHERE s.collected_at >= now() - make_interval(days => %%s)
              AND s.followers IS NOT NULL
            WINDOW w AS (PARTITION BY s.profile_id ORDER BY s.collected_at
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        )
        SELECT DISTINCT p.username, j.antes, j.agora, j.agora - j.antes,
               round(100.0 * (j.agora - j.antes) / NULLIF(j.antes, 0), 2),
               j.leituras
        FROM janela j
        JOIN profiles p ON p.id = j.profile_id
        %s
        WHERE j.leituras >= 2 %s
        ORDER BY 4 DESC NULLS LAST
    """ % (juncao, condicao)

    return [{"perfil": l[0], "antes": l[1], "agora": l[2], "ganho": l[3],
             "percentual": float(l[4]) if l[4] is not None else None,
             "leituras": l[5]}
            for l in conexao.execute(sql, [dias] + parametros)]


def cobertura(conexao):
    """Onde a esteira parou, de ponta a ponta."""
    perguntas = {
        "nichos": "SELECT count(*) FROM niches",
        "perfis": "SELECT count(*) FROM profiles",
        "perfis_aprovados": "SELECT count(*) FROM profiles WHERE is_approved",
        "conteudos": "SELECT count(*) FROM contents",
        "videos": "SELECT count(*) FROM contents "
                  "WHERE content_type IN ('reel','video')",
        "com_metrica": "SELECT count(DISTINCT content_id) "
                       "FROM content_metric_snapshots",
        "com_views": "SELECT count(DISTINCT content_id) "
                     "FROM content_metric_snapshots WHERE views IS NOT NULL",
        "baixados": "SELECT count(*) FROM media_assets WHERE asset_type='video'",
        "transcritos": "SELECT count(DISTINCT content_id) FROM transcripts",
        "analisados": "SELECT count(DISTINCT content_id) FROM content_analyses",
        "com_comentarios": "SELECT count(DISTINCT content_id) FROM comments",
        "na_fila": "SELECT count(*) FROM processing_jobs WHERE status='queued'",
    }
    return {chave: conexao.execute(sql).fetchone()[0]
            for chave, sql in perguntas.items()}
