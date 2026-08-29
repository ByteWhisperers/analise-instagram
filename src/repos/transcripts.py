"""Transcrição consultável: texto, trechos e o tempo de cada palavra.

O arquivo `.json` continua em `media_assets`. Aqui fica a versão que dá para
perguntar coisas — busca no falado, gancho dos 3 primeiros segundos, e o
tempo por palavra que a legenda karaokê exige.

Refazer a transcrição com o mesmo modelo **substitui**; com outro modelo,
guarda as duas. É o que permite comparar `base` e `small` no mesmo Reel sem
perder nenhuma das duas leituras.
"""

from ._comum import dicts, exigir, id_de


def salvar(conexao, conteudo_id, transcricao, modelo, idioma="pt",
           segundos_de_audio=None, tempo_ms=None):
    """Grava texto, trechos e palavras. Devolve o id da transcrição.

    `transcricao` é o dicionário que `transcrever.py` já produz:
    `{"texto": ..., "trechos": [{"inicio","fim","texto"}],
      "palavras": [{"palavra","inicio","fim","probabilidade"}]}`

    Trechos e palavras são apagados e regravados: refazer não pode acumular
    duas versões do mesmo áudio na mesma linha do tempo.
    """
    exigir(conteudo_id, "conteudo_id")
    exigir(modelo, "modelo")

    texto = transcricao.get("texto") or ""

    cursor = conexao.execute(
        """
        INSERT INTO transcripts
            (content_id, text, language, model, audio_seconds, elapsed_ms)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_id, model) DO UPDATE SET
            text          = EXCLUDED.text,
            language      = COALESCE(EXCLUDED.language, transcripts.language),
            audio_seconds = COALESCE(EXCLUDED.audio_seconds, transcripts.audio_seconds),
            elapsed_ms    = COALESCE(EXCLUDED.elapsed_ms, transcripts.elapsed_ms),
            created_at    = now()
        RETURNING id
        """,
        (conteudo_id, texto, idioma, modelo, segundos_de_audio, tempo_ms))

    transcricao_id = id_de(cursor)

    conexao.execute("DELETE FROM transcript_segments WHERE transcript_id = %s",
                    (transcricao_id,))
    for indice, trecho in enumerate(transcricao.get("trechos") or []):
        conexao.execute(
            "INSERT INTO transcript_segments "
            "(transcript_id, idx, start_seconds, end_seconds, text) "
            "VALUES (%s, %s, %s, %s, %s)",
            (transcricao_id, indice, trecho.get("inicio") or 0.0,
             trecho.get("fim"), trecho.get("texto") or ""))

    conexao.execute("DELETE FROM transcript_words WHERE transcript_id = %s",
                    (transcricao_id,))
    for indice, palavra in enumerate(transcricao.get("palavras") or []):
        conexao.execute(
            "INSERT INTO transcript_words "
            "(transcript_id, idx, word, start_seconds, end_seconds, probability) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (transcricao_id, indice, palavra.get("palavra") or "",
             palavra.get("inicio") or 0.0, palavra.get("fim"),
             palavra.get("probabilidade")))

    return transcricao_id


def de(conexao, conteudo_id, modelo=None):
    """A transcrição de um conteúdo. Sem modelo, a mais recente."""
    colunas = ("id", "content_id", "text", "language", "model",
               "audio_seconds", "elapsed_ms", "created_at")
    sql = ("SELECT %s FROM transcripts WHERE content_id = %%s"
           % ", ".join(colunas))
    parametros = [conteudo_id]

    if modelo:
        sql += " AND model = %s"
        parametros.append(modelo)

    sql += " ORDER BY created_at DESC LIMIT 1"
    linhas = dicts(conexao.execute(sql, parametros), colunas)
    return linhas[0] if linhas else None


def trechos(conexao, transcricao_id):
    cursor = conexao.execute(
        "SELECT idx, start_seconds, end_seconds, text FROM transcript_segments "
        "WHERE transcript_id = %s ORDER BY idx", (transcricao_id,))
    return [{"indice": l[0], "inicio": l[1], "fim": l[2], "texto": l[3]}
            for l in cursor.fetchall()]


def palavras(conexao, transcricao_id):
    """As palavras com tempo, no formato que `legenda.py` consome."""
    cursor = conexao.execute(
        "SELECT word, start_seconds, end_seconds, probability "
        "FROM transcript_words WHERE transcript_id = %s ORDER BY idx",
        (transcricao_id,))
    return [{"palavra": l[0], "inicio": l[1], "fim": l[2], "probabilidade": l[3]}
            for l in cursor.fetchall()]


def gancho_falado(conexao, transcricao_id, ate_segundos=3.0):
    """O que foi dito antes dos N segundos. A definição de gancho do projeto."""
    cursor = conexao.execute(
        "SELECT text FROM transcript_segments WHERE transcript_id = %s "
        "AND start_seconds < %s ORDER BY idx",
        (transcricao_id, ate_segundos))
    return " ".join(l[0].strip() for l in cursor.fetchall() if l[0]).strip()


def procurar(conexao, termo, limite=20, nos_primeiros_segundos=None):
    """Busca no que foi FALADO, não na legenda.

    Usa `plainto_tsquery` e não `to_tsquery`: o primeiro aceita texto digitado
    por gente ("link na bio") sem exigir operadores, e não estoura com
    pontuação. `ts_rank` ordena por relevância.

    Com `nos_primeiros_segundos`, procura só nos trechos iniciais — é assim
    que se responde "quais vídeos falam 'bônus' logo no começo".
    """
    if nos_primeiros_segundos:
        sql = """
            SELECT DISTINCT ON (c.id)
                   c.platform_content_id, p.username, s.start_seconds, s.text
            FROM transcript_segments s
            JOIN transcripts t ON t.id = s.transcript_id
            JOIN contents c    ON c.id = t.content_id
            JOIN profiles p    ON p.id = c.profile_id
            WHERE s.start_seconds < %s
              AND to_tsvector('portuguese', s.text) @@ plainto_tsquery('portuguese', %s)
            ORDER BY c.id, s.start_seconds
            LIMIT %s
        """
        parametros = (nos_primeiros_segundos, termo, limite)
        return [{"post": l[0], "perfil": l[1], "segundo": l[2], "trecho": l[3]}
                for l in conexao.execute(sql, parametros)]

    sql = """
        SELECT c.platform_content_id, p.username,
               ts_rank(t.search_pt, plainto_tsquery('portuguese', %s)) AS peso,
               ts_headline('portuguese', t.text,
                           plainto_tsquery('portuguese', %s),
                           'MaxWords=18, MinWords=6') AS trecho
        FROM transcripts t
        JOIN contents c ON c.id = t.content_id
        JOIN profiles p ON p.id = c.profile_id
        WHERE t.search_pt @@ plainto_tsquery('portuguese', %s)
        ORDER BY peso DESC
        LIMIT %s
    """
    return [{"post": l[0], "perfil": l[1], "peso": round(l[2], 4), "trecho": l[3]}
            for l in conexao.execute(sql, (termo, termo, termo, limite))]
