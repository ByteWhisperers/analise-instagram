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
