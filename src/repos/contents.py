"""Conteúdos (Reels e posts), suas hashtags e menções.

Traduz o `post.json` em português que `coletor.py` produz para as colunas em
inglês. A chave natural é `(platform, platform_content_id)` — o shortcode —,
e é ela que faz recoletar não duplicar.

**Hashtag e menção são tabelas, não JSONB.** Caberiam em `raw_data`, mas
"qual hashtag aparece nos vídeos que mais engajam" é consulta central do
projeto, e varrer JSON para responder isso seria desperdício declarado.
"""

import json

from ._comum import booleano, dicts, exigir, id_de

PLATAFORMA_PADRAO = "instagram"

# O tipo vem do coletor em português; a coluna tem CHECK em inglês.
TIPOS = {"reel": "reel", "video": "video", "carrossel": "carousel",
         "foto": "image", "story": "story"}

COLUNAS = ("id", "profile_id", "platform", "platform_content_id",
           "content_url", "content_type", "caption", "published_at",
           "duration_seconds", "thumbnail_url", "source_video_url",
           "language", "audio_id", "audio_title", "audio_author",
           "is_original_audio", "location_id", "location_name",
           "first_seen_at", "last_seen_at")


def _tipo(post):
    """Tipo do coletor -> valor que o CHECK aceita. Desconhecido vira 'other'."""
    bruto = (post.get("tipo") or "").lower()
    if bruto in TIPOS:
        return TIPOS[bruto]
    return "video" if post.get("e_video") else "other"


def salvar(conexao, post, perfil_id, plataforma=PLATAFORMA_PADRAO,
           guardar_bruto=None):
    """Insere ou atualiza pelo shortcode. Devolve o id.

    Como em `profiles`, tudo entra por `COALESCE`: campo que a fonte não
    trouxe nesta rodada não apaga o que já estava gravado.
    """
    codigo = exigir(post.get("id"), "id")
    exigir(perfil_id, "perfil_id")

    cursor = conexao.execute(
        """
        INSERT INTO contents (
            profile_id, platform, platform_content_id, content_url,
            content_type, caption, published_at, duration_seconds,
            thumbnail_url, source_video_url, audio_id, audio_title,
            audio_author, is_original_audio, location_id, location_name,
            raw_data, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, now())
        ON CONFLICT (platform, platform_content_id) DO UPDATE SET
            content_url      = COALESCE(EXCLUDED.content_url,      contents.content_url),
            content_type     = COALESCE(EXCLUDED.content_type,     contents.content_type),
            caption          = COALESCE(EXCLUDED.caption,          contents.caption),
            published_at     = COALESCE(EXCLUDED.published_at,     contents.published_at),
            duration_seconds = COALESCE(EXCLUDED.duration_seconds, contents.duration_seconds),
            thumbnail_url    = COALESCE(EXCLUDED.thumbnail_url,    contents.thumbnail_url),
            source_video_url = COALESCE(EXCLUDED.source_video_url, contents.source_video_url),
            audio_id         = COALESCE(EXCLUDED.audio_id,         contents.audio_id),
            audio_title      = COALESCE(EXCLUDED.audio_title,      contents.audio_title),
            audio_author     = COALESCE(EXCLUDED.audio_author,     contents.audio_author),
            is_original_audio= COALESCE(EXCLUDED.is_original_audio,contents.is_original_audio),
            location_id      = COALESCE(EXCLUDED.location_id,      contents.location_id),
            location_name    = COALESCE(EXCLUDED.location_name,    contents.location_name),
            raw_data         = COALESCE(EXCLUDED.raw_data,         contents.raw_data),
            last_seen_at     = now()
        RETURNING id
        """,
        (perfil_id, plataforma, codigo,
         post.get("link"),
         _tipo(post),
         post.get("legenda"),
         post.get("data_utc"),
         post.get("duracao_segundos"),
         post.get("thumbnail_url"),
         post.get("video_url"),
         post.get("audio_id"),
         post.get("audio_titulo"),
         post.get("audio_autor"),
         booleano(post.get("audio_original")),
         post.get("local_id"),
         post.get("local_nome"),
         json.dumps(guardar_bruto, ensure_ascii=False) if guardar_bruto else None))

    conteudo_id = id_de(cursor)
    _gravar_tags(conexao, conteudo_id, post)
    return conteudo_id


def _gravar_tags(conexao, conteudo_id, post):
    """Hashtags e menções, substituídas por inteiro.

    Apagar antes de inserir não é preguiça: se a legenda foi editada e uma
    hashtag saiu, ela precisa sair do banco também. Acumular daria a resposta
    errada em "quais tags este perfil usa".
    """
    hashtags = post.get("hashtags")
    if hashtags is not None:
        conexao.execute("DELETE FROM content_hashtags WHERE content_id = %s",
                        (conteudo_id,))
        for tag in sorted({t.strip().lstrip("#").lower()
                           for t in hashtags if t and t.strip()}):
            conexao.execute(
                "INSERT INTO content_hashtags (content_id, tag) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING", (conteudo_id, tag))

    mencoes = post.get("mencoes")
    if mencoes is not None:
        conexao.execute("DELETE FROM content_mentions WHERE content_id = %s",
                        (conteudo_id,))
        for usuario in sorted({m.strip().lstrip("@").lower()
                               for m in mencoes if m and m.strip()}):
            conexao.execute(
                "INSERT INTO content_mentions (content_id, username) "
                "VALUES (%s, %s) ON CONFLICT DO NOTHING", (conteudo_id, usuario))


def por_codigo(conexao, codigo, plataforma=PLATAFORMA_PADRAO):
    cursor = conexao.execute(
        "SELECT %s FROM contents WHERE platform = %%s AND platform_content_id = %%s"
        % ", ".join(COLUNAS), (plataforma, codigo))
    linhas = dicts(cursor, COLUNAS)
    return linhas[0] if linhas else None


def id_por_codigo(conexao, codigo, plataforma=PLATAFORMA_PADRAO):
    linha = conexao.execute(
        "SELECT id FROM contents WHERE platform = %s AND platform_content_id = %s",
        (plataforma, codigo)).fetchone()
    return linha[0] if linha else None


def hashtags_de(conexao, conteudo_id):
    cursor = conexao.execute(
        "SELECT tag FROM content_hashtags WHERE content_id = %s ORDER BY tag",
        (conteudo_id,))
    return [linha[0] for linha in cursor.fetchall()]


def mencoes_de(conexao, conteudo_id):
    cursor = conexao.execute(
        "SELECT username FROM content_mentions WHERE content_id = %s "
        "ORDER BY username", (conteudo_id,))
    return [linha[0] for linha in cursor.fetchall()]


def videos_do_perfil(conexao, perfil_id, limite=50):
    """Só os que têm vídeo — é o que a esteira de download e análise usa."""
    cursor = conexao.execute(
        "SELECT %s FROM contents WHERE profile_id = %%s "
        "AND content_type IN ('reel', 'video') "
        "ORDER BY published_at DESC NULLS LAST LIMIT %%s"
        % ", ".join(COLUNAS), (perfil_id, limite))
    return dicts(cursor, COLUNAS)


def dados_para_download(conexao, conteudo_ids):
    """O que o downloader precisa saber: link do post e dono.

    Devolve um dicionário indexado pelo id do conteúdo, para o pipeline não
    fazer uma consulta por item da fila.

    Note que o que sai é o `content_url` (o link do post), e nunca o
    `source_video_url`: a URL do CDN vence, e quem resolve na hora é o yt-dlp.
    """
    if not conteudo_ids:
        return {}

    cursor = conexao.execute(
        """
        SELECT c.id, c.platform_content_id, c.content_url, p.username
        FROM contents c JOIN profiles p ON p.id = c.profile_id
        WHERE c.id = ANY(%s)
        """,
        (list(conteudo_ids),))

    return {l[0]: {"content_id": l[0], "codigo": l[1], "url": l[2],
                   "usuario": l[3]} for l in cursor.fetchall()}
