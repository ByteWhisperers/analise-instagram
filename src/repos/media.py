"""Arquivos: vídeo, thumbnail, áudio, transcrição, legenda, edição.

**O arquivo nunca entra no banco.** Aqui ficam metadado e referência; o byte
mora no storage. Banco com vídeo dentro fica intratável para copiar, para
fazer backup e para consultar.

Um conteúdo tem no máximo um asset de cada tipo por provedor — a constraint
`(content_id, asset_type, storage_provider)` é o que torna o download
idempotente sem precisar perguntar ao disco.
"""

from ._comum import dicts, exigir, id_de

TIPOS = ("video", "thumbnail", "audio", "transcript", "subtitle", "edit")
PROVEDORES = ("local", "s3", "r2", "gcs")

COLUNAS = ("id", "content_id", "asset_type", "storage_provider", "storage_key",
           "storage_url", "mime_type", "file_size", "duration_seconds",
           "checksum", "created_at")


def registrar(conexao, conteudo_id, tipo, chave, provedor="local", url=None,
              mime=None, bytes_=None, duracao=None, checksum=None):
    """Grava (ou atualiza) a referência de um arquivo. Devolve o id."""
    exigir(conteudo_id, "conteudo_id")
    exigir(chave, "chave")

    if tipo not in TIPOS:
        from ._comum import ErroDeRepositorio
        raise ErroDeRepositorio(
            "Tipo de arquivo '%s' não existe. Os válidos são: %s"
            % (tipo, ", ".join(TIPOS)))

    cursor = conexao.execute(
        """
        INSERT INTO media_assets (
            content_id, asset_type, storage_provider, storage_key, storage_url,
            mime_type, file_size, duration_seconds, checksum)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_id, asset_type, storage_provider) DO UPDATE SET
            storage_key      = EXCLUDED.storage_key,
            storage_url      = COALESCE(EXCLUDED.storage_url,      media_assets.storage_url),
            mime_type        = COALESCE(EXCLUDED.mime_type,        media_assets.mime_type),
            file_size        = COALESCE(EXCLUDED.file_size,        media_assets.file_size),
            duration_seconds = COALESCE(EXCLUDED.duration_seconds, media_assets.duration_seconds),
            checksum         = COALESCE(EXCLUDED.checksum,         media_assets.checksum)
        RETURNING id
        """,
        (conteudo_id, tipo, provedor, str(chave), url, mime, bytes_,
         duracao, checksum))

    return id_de(cursor)


def tem(conexao, conteudo_id, tipo="video", provedor="local"):
    """Se o arquivo já foi registrado. É a checagem de idempotência."""
    linha = conexao.execute(
        "SELECT 1 FROM media_assets WHERE content_id = %s AND asset_type = %s "
        "AND storage_provider = %s", (conteudo_id, tipo, provedor)).fetchone()
    return bool(linha)


def de(conexao, conteudo_id, tipo=None):
    """Os arquivos de um conteúdo, ou só os de um tipo."""
    sql = "SELECT %s FROM media_assets WHERE content_id = %%s" % ", ".join(COLUNAS)
    parametros = [conteudo_id]

    if tipo:
        sql += " AND asset_type = %s"
        parametros.append(tipo)

    sql += " ORDER BY asset_type"
    return dicts(conexao.execute(sql, parametros), COLUNAS)


def caminho_do_video(conexao, conteudo_id, provedor="local"):
    """A chave de storage do vídeo, ou None."""
    linha = conexao.execute(
        "SELECT storage_key FROM media_assets WHERE content_id = %s "
        "AND asset_type = 'video' AND storage_provider = %s",
        (conteudo_id, provedor)).fetchone()
    return linha[0] if linha else None


def total_em_disco(conexao, provedor="local"):
    """Quantos arquivos e quantos bytes. Serve para saber quando o disco aperta."""
    linha = conexao.execute(
        "SELECT count(*), COALESCE(sum(file_size), 0) FROM media_assets "
        "WHERE storage_provider = %s", (provedor,)).fetchone()
    return {"arquivos": linha[0], "bytes": int(linha[1])}


# ------------------------------------------------------------------ retencao


COLUNAS_LIBERAVEL = ("id", "content_id", "storage_key", "file_size",
                     "created_at", "username", "platform_content_id")


def com_derivado_pronto(conexao, provedor="local", dias=None):
    """Vídeos cujo conteúdo já tem transcrição gravada.

    São os únicos candidatos legítimos a sumir do disco: o caro já foi
    extraído, e o mp4 é re-baixável pelo link do post. Apagar antes da
    transcrição jogaria fora a única coisa que custou tempo de CPU.

    `dias` restringe aos baixados há mais de N dias — quem quer margem para
    conferir o resultado antes de perder o original.
    """
    sql = """
        SELECT a.id, a.content_id, a.storage_key, a.file_size, a.created_at,
               p.username, c.platform_content_id
        FROM media_assets a
        JOIN contents c ON c.id = a.content_id
        JOIN profiles p ON p.id = c.profile_id
        WHERE a.asset_type = 'video'
          AND a.storage_provider = %s
          AND EXISTS (SELECT 1 FROM transcripts t WHERE t.content_id = a.content_id)
    """
    parametros = [provedor]

    if dias is not None:
        sql += " AND a.created_at < now() - make_interval(days => %s)"
        parametros.append(int(dias))

    sql += " ORDER BY a.file_size DESC NULLS LAST"
    return dicts(conexao.execute(sql, parametros), COLUNAS_LIBERAVEL)


def por_tipo(conexao, provedor="local"):
    """Quantos arquivos e quantos bytes em cada `asset_type`.

    Responde "para onde o disco foi" sem abrir uma pasta sequer.
    """
    cursor = conexao.execute(
        "SELECT asset_type, count(*), COALESCE(sum(file_size), 0) "
        "FROM media_assets WHERE storage_provider = %s "
        "GROUP BY asset_type ORDER BY 3 DESC", (provedor,))
    return [{"tipo": t, "arquivos": n, "bytes": int(b)}
            for t, n, b in cursor.fetchall()]


def por_perfil(conexao, provedor="local", limite=5):
    """Os perfis que mais ocupam disco."""
    cursor = conexao.execute(
        """
        SELECT p.username, count(*), COALESCE(sum(a.file_size), 0)
        FROM media_assets a
        JOIN contents c ON c.id = a.content_id
        JOIN profiles p ON p.id = c.profile_id
        WHERE a.storage_provider = %s
        GROUP BY p.username
        ORDER BY 3 DESC
        LIMIT %s
        """, (provedor, limite))
    return [{"perfil": u, "arquivos": n, "bytes": int(b)}
            for u, n, b in cursor.fetchall()]


def chaves_registradas(conexao, provedor="local"):
    """Todo caminho que o banco acha que existe no disco.

    Serve para a reconciliação: o que está aqui e não está no disco é registro
    órfão; o que está no disco e não está aqui é arquivo que ninguém pediu.
    """
    cursor = conexao.execute(
        "SELECT storage_key FROM media_assets WHERE storage_provider = %s",
        (provedor,))
    return [linha[0] for linha in cursor.fetchall()]


def esquecer(conexao, asset_id):
    """Apaga o registro do arquivo. **O byte é problema de quem chamou.**

    Por que apagar a linha, e não marcá-la: `tem()` é a checagem de
    idempotência do download. Uma linha que aponta para arquivo inexistente
    faz o sistema afirmar que tem um vídeo que não tem — e aí a etapa de
    transcrição falha lá na frente, longe da causa.

    O job em `processing_jobs` continua `done`, então isto **não** devolve o
    vídeo para a fila. Há teste para essa afirmação.
    """
    cursor = conexao.execute(
        "DELETE FROM media_assets WHERE id = %s RETURNING storage_key",
        (asset_id,))
    linha = cursor.fetchone()
    return linha[0] if linha else None


def registros_da_chave(conexao, chave, provedor="local"):
    """Os registros que apontam para um caminho. Normalmente um só.

    Serve para a reconciliação: quando o arquivo sumiu do disco, é por aqui
    que se acha a linha que ficou mentindo.
    """
    cursor = conexao.execute(
        "SELECT id, content_id, asset_type, storage_key FROM media_assets "
        "WHERE storage_key = %s AND storage_provider = %s", (str(chave), provedor))
    return dicts(cursor, ("id", "content_id", "asset_type", "storage_key"))
