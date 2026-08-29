"""O banco de dados do projeto — esquema e escrita.

Um arquivo só: `dados/analise.db`. SQLite vem dentro do Python; nada é instalado.

**Nenhum outro módulo escreve SQL.** Quem precisa gravar chama uma função daqui.
Quem precisa perguntar usa `consultas.py`.

Os arquivos de vídeo continuam em disco. Aqui fica o caminho, nunca o vídeo.
"""

import json
import sqlite3
from datetime import datetime

import config

ARQUIVO = "analise.db"
VERSAO_DO_ESQUEMA = 3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS buscas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    termo       TEXT    NOT NULL,
    data        TEXT    NOT NULL,
    criterios   TEXT
);

CREATE TABLE IF NOT EXISTS perfis (
    usuario       TEXT PRIMARY KEY,
    nome          TEXT,
    bio           TEXT,
    seguidores    INTEGER,
    seguindo      INTEGER,
    posts         INTEGER,
    privado       INTEGER DEFAULT 0,
    verificado    INTEGER DEFAULT 0,
    link_externo  TEXT,
    lido_em       TEXT,
    perfil_id     TEXT,
    link_perfil   TEXT,
    nicho         TEXT,
    categoria     TEXT,
    relevancia    REAL
);

-- De qual busca cada perfil veio, e por qual fonte.
CREATE TABLE IF NOT EXISTS busca_perfis (
    busca_id  INTEGER NOT NULL REFERENCES buscas(id) ON DELETE CASCADE,
    usuario   TEXT    NOT NULL,
    origem    TEXT,
    PRIMARY KEY (busca_id, usuario)
);

CREATE TABLE IF NOT EXISTS posts (
    id             TEXT PRIMARY KEY,
    usuario        TEXT NOT NULL REFERENCES perfis(usuario) ON DELETE CASCADE,
    link           TEXT,
    tipo           TEXT,
    typename       TEXT,
    e_video        INTEGER DEFAULT 0,
    duracao        REAL,
    visualizacoes  INTEGER,
    legenda        TEXT,
    curtidas       INTEGER,
    comentarios    INTEGER,
    data_utc       TEXT,
    data_local     TEXT,
    dia_semana     TEXT,
    hora           TEXT,
    caminho_midia  TEXT,
    baixado_em     TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_usuario ON posts(usuario);
CREATE INDEX IF NOT EXISTS idx_posts_tipo    ON posts(tipo);

-- Uma linha por par (post, tag). É o que permite agrupar por hashtag
-- numa consulta, em vez de varrer o texto da legenda.
CREATE TABLE IF NOT EXISTS hashtags (
    post_id  TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (post_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_hashtags_tag ON hashtags(tag);

CREATE TABLE IF NOT EXISTS mencoes (
    post_id  TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    perfil   TEXT NOT NULL,
    PRIMARY KEY (post_id, perfil)
);

CREATE TABLE IF NOT EXISTS transcricoes (
    post_id            TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    texto              TEXT,
    gancho_falado      TEXT,
    duracao_audio      REAL,
    tempo_transcricao  REAL,
    modelo             TEXT,
    idioma             TEXT,
    transcrito_em      TEXT
);

-- Busca por palavra dentro de todas as transcrições de uma vez.
CREATE VIRTUAL TABLE IF NOT EXISTS transcricoes_fts USING fts5(
    post_id UNINDEXED,
    texto
);

-- Os trechos, para montar a estrutura do vídeo no tempo.
CREATE TABLE IF NOT EXISTS segmentos (
    post_id  TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    indice   INTEGER NOT NULL,
    inicio   REAL,
    fim      REAL,
    texto    TEXT,
    PRIMARY KEY (post_id, indice)
);

-- Cada palavra com seu segundo. Nasce da análise e alimenta a legenda
-- palavra-por-palavra da edição.
CREATE TABLE IF NOT EXISTS palavras (
    post_id  TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    indice   INTEGER NOT NULL,
    palavra  TEXT,
    inicio   REAL,
    fim      REAL,
    PRIMARY KEY (post_id, indice)
);

-- Derivado: pode ser apagado e recalculado sem perder coleta.
CREATE TABLE IF NOT EXISTS metricas (
    post_id             TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    engajamento         REAL,
    ritmo_ppm           REAL,
    gancho_falado       TEXT,
    gancho_escrito      TEXT,
    hashtags_qtd        INTEGER,
    legenda_caracteres  INTEGER,
    legenda_linhas      INTEGER,
    legenda_emojis      INTEGER,
    tem_cta             INTEGER DEFAULT 0,
    tipos_cta           TEXT,
    calculado_em        TEXT
);

CREATE INDEX IF NOT EXISTS idx_metricas_engajamento ON metricas(engajamento DESC);

CREATE TABLE IF NOT EXISTS edicoes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id      TEXT REFERENCES posts(id) ON DELETE SET NULL,
    entrada      TEXT NOT NULL,
    template     TEXT,
    saida        TEXT,
    feito_em     TEXT
);

-- ------------------------------------------------------------------ pipeline

-- Uma rodada do coletor. Existe para responder "quanto custou" com número,
-- não com estimativa — é a base das métricas de custo por perfil e por vídeo.
CREATE TABLE IF NOT EXISTS coletas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nicho         TEXT    NOT NULL,
    coletor       TEXT    NOT NULL,
    run_id        TEXT,
    itens         INTEGER DEFAULT 0,
    perfis        INTEGER DEFAULT 0,
    videos        INTEGER DEFAULT 0,
    custo_usd     REAL,
    status        TEXT    NOT NULL DEFAULT 'rodando',
    iniciada_em   TEXT    NOT NULL,
    terminada_em  TEXT,
    duracao_ms    INTEGER,
    erro          TEXT
);

-- A máquina de estados do download.
--
-- Separada de `posts` pelo mesmo critério que já separou `metricas`: o que o
-- Instagram afirma fica em `posts`; o que NÓS fizemos fica aqui.
--
-- Esta tabela É a fila. Não há broker: `status='queued'` é o que espera vez.
CREATE TABLE IF NOT EXISTS downloads (
    post_id       TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    usuario       TEXT    NOT NULL,
    instagram_url TEXT    NOT NULL,
    video_url     TEXT,
    status        TEXT    NOT NULL DEFAULT 'discovered',
    tentativas    INTEGER NOT NULL DEFAULT 0,
    erro          TEXT,
    storage_path  TEXT,
    bytes         INTEGER,
    duracao_ms    INTEGER,
    coleta_id     INTEGER REFERENCES coletas(id) ON DELETE SET NULL,
    criado_em     TEXT    NOT NULL,
    atualizado_em TEXT,
    baixado_em    TEXT
);

CREATE INDEX IF NOT EXISTS idx_downloads_status  ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_downloads_usuario ON downloads(usuario);

-- ------------------------------------------------- serie temporal (v3)

-- Uma foto do perfil a cada coleta.
--
-- **Sem esta tabela, followers_growth_7d e impossivel.** `perfis` guarda o
-- estado de agora e sobrescreve na proxima coleta; crescimento e a diferenca
-- entre duas leituras, e diferenca precisa de duas linhas.
CREATE TABLE IF NOT EXISTS perfis_historico (
    usuario     TEXT    NOT NULL REFERENCES perfis(usuario) ON DELETE CASCADE,
    medido_em   TEXT    NOT NULL,
    seguidores  INTEGER,
    seguindo    INTEGER,
    posts       INTEGER,
    coleta_id   INTEGER REFERENCES coletas(id) ON DELETE SET NULL,
    PRIMARY KEY (usuario, medido_em)
);

CREATE INDEX IF NOT EXISTS idx_hist_perfil ON perfis_historico(usuario, medido_em);

-- Uma foto dos numeros de um post a cada coleta.
--
-- Guardar `views_per_hour` como coluna seria errado: o valor depende de quando
-- foi medido. Guarda-se a medicao crua com a hora; a velocidade vira conta na
-- consulta e continua correta para sempre.
CREATE TABLE IF NOT EXISTS metricas_historico (
    post_id           TEXT    NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    medido_em         TEXT    NOT NULL,
    horas_desde_post  REAL,
    visualizacoes     INTEGER,
    curtidas          INTEGER,
    comentarios       INTEGER,
    compartilhamentos INTEGER,
    salvamentos       INTEGER,
    coleta_id         INTEGER REFERENCES coletas(id) ON DELETE SET NULL,
    PRIMARY KEY (post_id, medido_em)
);

CREATE INDEX IF NOT EXISTS idx_mhist_post ON metricas_historico(post_id, medido_em);
"""


def caminho():
    return config.DADOS / ARQUIVO


def conectar(criar=True):
    """Abre o banco. Cria o arquivo e o esquema se ainda não existirem."""
    config.garantir_pastas()
    conexao = sqlite3.connect(str(caminho()))
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA journal_mode = WAL")
    if criar:
        criar_esquema(conexao)
    return conexao


# Colunas acrescentadas depois que o banco já existia. `CREATE TABLE IF NOT
# EXISTS` não mexe em tabela pronta, então elas entram por ALTER TABLE.
COLUNAS_ACRESCENTADAS = {
    "perfis": {
        "perfil_id": "TEXT",
        "link_perfil": "TEXT",
        "nicho": "TEXT",
        "categoria": "TEXT",
        "relevancia": "REAL",
        "avatar_url": "TEXT",
        "categoria_negocio": "TEXT",
        "aprovado": "INTEGER",
        "classificado_em": "TEXT",
    },
    "posts": {
        "thumbnail_url": "TEXT",
        "video_url": "TEXT",
        # Instagram NAO publica compartilhamento nem salvamento. As colunas
        # existem porque o Actor pode passar a devolver; enquanto nao devolver,
        # ficam NULL — e NULL e honesto, zero seria mentira.
        "compartilhamentos": "INTEGER",
        "salvamentos": "INTEGER",
        "audio_id": "TEXT",
        "audio_titulo": "TEXT",
        "audio_autor": "TEXT",
        "audio_original": "INTEGER",
        "local_nome": "TEXT",
        "local_id": "TEXT",
    },
}


def _colunas_de(conexao, tabela):
    return {linha["name"] for linha in conexao.execute(
        "PRAGMA table_info(%s)" % tabela)}


def _migrar(conexao):
    """Acrescenta coluna que faltar. Banco criado numa versão velha continua
    abrindo, em vez de estourar com 'no such column'."""
    for tabela, colunas in COLUNAS_ACRESCENTADAS.items():
        existentes = _colunas_de(conexao, tabela)
        for nome, tipo in colunas.items():
            if nome not in existentes:
                conexao.execute("ALTER TABLE %s ADD COLUMN %s %s"
                                % (tabela, nome, tipo))


def criar_esquema(conexao):
    """Idempotente: rodar de novo não apaga nem duplica nada."""
    conexao.executescript(ESQUEMA)
    _migrar(conexao)
    conexao.execute("PRAGMA user_version = %d" % VERSAO_DO_ESQUEMA)
    conexao.commit()


def _agora():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- escrita


def salvar_busca(conexao, termo, criterios, perfis):
    """Grava a busca e de onde cada perfil veio. Devolve o id da busca."""
    cursor = conexao.execute(
        "INSERT INTO buscas (termo, data, criterios) VALUES (?, ?, ?)",
        (termo, _agora(), json.dumps(criterios, ensure_ascii=False)))
    busca_id = cursor.lastrowid

    for perfil in perfis:
        conexao.execute(
            "INSERT OR REPLACE INTO busca_perfis (busca_id, usuario, origem) "
            "VALUES (?, ?, ?)",
            (busca_id, perfil["usuario"], ",".join(perfil.get("origem", []))))

    conexao.commit()
    return busca_id


def salvar_perfil(conexao, perfil):
    """Insere ou atualiza. Os seguidores ficam sendo os da última leitura."""
    conexao.execute(
        "INSERT INTO perfis (usuario, nome, bio, seguidores, seguindo, posts, "
        "                    privado, verificado, link_externo, lido_em, "
        "                    perfil_id, link_perfil, nicho, categoria, relevancia) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(usuario) DO UPDATE SET "
        "  nome=excluded.nome, bio=excluded.bio, seguidores=excluded.seguidores, "
        "  seguindo=excluded.seguindo, posts=excluded.posts, "
        "  privado=excluded.privado, verificado=excluded.verificado, "
        "  link_externo=excluded.link_externo, lido_em=excluded.lido_em, "
        "  perfil_id=COALESCE(excluded.perfil_id, perfis.perfil_id), "
        "  link_perfil=COALESCE(excluded.link_perfil, perfis.link_perfil), "
        "  nicho=COALESCE(excluded.nicho, perfis.nicho), "
        "  categoria=COALESCE(excluded.categoria, perfis.categoria), "
        "  relevancia=COALESCE(excluded.relevancia, perfis.relevancia)",
        (perfil["usuario"], perfil.get("nome"), perfil.get("bio"),
         perfil.get("seguidores"), perfil.get("seguindo"), perfil.get("posts"),
         int(bool(perfil.get("privado"))), int(bool(perfil.get("verificado"))),
         perfil.get("link_externo"), perfil.get("lido_em") or _agora(),
         perfil.get("perfil_id"), perfil.get("link_perfil"),
         perfil.get("nicho"), perfil.get("categoria"), perfil.get("relevancia")))
    conexao.commit()


def salvar_post(conexao, post, caminho_midia=None):
    """Insere ou atualiza o post e suas hashtags e menções."""
    conexao.execute(
        "INSERT INTO posts (id, usuario, link, tipo, typename, e_video, duracao, "
        "                   visualizacoes, legenda, curtidas, comentarios, "
        "                   data_utc, data_local, dia_semana, hora, "
        "                   caminho_midia, baixado_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "  curtidas=excluded.curtidas, comentarios=excluded.comentarios, "
        "  visualizacoes=excluded.visualizacoes, legenda=excluded.legenda, "
        "  caminho_midia=COALESCE(excluded.caminho_midia, posts.caminho_midia)",
        (post["id"], post["perfil"], post.get("link"), post.get("tipo"),
         post.get("typename"), int(bool(post.get("e_video"))),
         post.get("duracao_segundos"), post.get("visualizacoes"),
         post.get("legenda"), post.get("curtidas"), post.get("comentarios"),
         post.get("data_utc"), post.get("data_local"),
         post.get("dia_da_semana"), post.get("hora"),
         str(caminho_midia) if caminho_midia else None,
         post.get("baixado_em") or _agora()))

    conexao.execute("DELETE FROM hashtags WHERE post_id = ?", (post["id"],))
    for tag in set(post.get("hashtags") or []):
        conexao.execute("INSERT INTO hashtags (post_id, tag) VALUES (?, ?)",
                        (post["id"], tag.lower()))

    conexao.execute("DELETE FROM mencoes WHERE post_id = ?", (post["id"],))
    for perfil in set(post.get("mencoes") or []):
        conexao.execute("INSERT INTO mencoes (post_id, perfil) VALUES (?, ?)",
                        (post["id"], perfil.lower()))

    conexao.commit()


def salvar_transcricao(conexao, post_id, transcricao):
    """Grava texto, trechos e palavras. Refazer substitui, não duplica."""
    conexao.execute(
        "INSERT INTO transcricoes (post_id, texto, gancho_falado, duracao_audio, "
        "                          tempo_transcricao, modelo, idioma, transcrito_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(post_id) DO UPDATE SET "
        "  texto=excluded.texto, gancho_falado=excluded.gancho_falado, "
        "  duracao_audio=excluded.duracao_audio, "
        "  tempo_transcricao=excluded.tempo_transcricao, "
        "  modelo=excluded.modelo, transcrito_em=excluded.transcrito_em",
        (post_id, transcricao.get("texto"), transcricao.get("gancho_falado"),
         transcricao.get("duracao_audio_segundos"),
         transcricao.get("tempo_de_transcricao_segundos"),
         transcricao.get("modelo"), transcricao.get("idioma"),
         transcricao.get("transcrito_em") or _agora()))

    conexao.execute("DELETE FROM transcricoes_fts WHERE post_id = ?", (post_id,))
    conexao.execute("INSERT INTO transcricoes_fts (post_id, texto) VALUES (?, ?)",
                    (post_id, transcricao.get("texto") or ""))

    conexao.execute("DELETE FROM segmentos WHERE post_id = ?", (post_id,))
    for indice, segmento in enumerate(transcricao.get("segmentos") or []):
        conexao.execute(
            "INSERT INTO segmentos (post_id, indice, inicio, fim, texto) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_id, indice, segmento.get("inicio"), segmento.get("fim"),
             segmento.get("texto")))

    conexao.execute("DELETE FROM palavras WHERE post_id = ?", (post_id,))
    for indice, palavra in enumerate(transcricao.get("palavras") or []):
        conexao.execute(
            "INSERT INTO palavras (post_id, indice, palavra, inicio, fim) "
            "VALUES (?, ?, ?, ?, ?)",
            (post_id, indice, palavra.get("palavra"), palavra.get("inicio"),
             palavra.get("fim")))

    conexao.commit()


def salvar_metricas(conexao, post_id, analise):
    """Grava o que foi calculado. Pode ser apagado e refeito sem perder coleta."""
    legenda = analise.get("legenda") or {}
    chamadas = analise.get("chamadas_para_acao") or {}
    gancho = analise.get("gancho") or {}

    conexao.execute(
        "INSERT INTO metricas (post_id, engajamento, ritmo_ppm, gancho_falado, "
        "                      gancho_escrito, hashtags_qtd, legenda_caracteres, "
        "                      legenda_linhas, legenda_emojis, tem_cta, tipos_cta, "
        "                      calculado_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(post_id) DO UPDATE SET "
        "  engajamento=excluded.engajamento, ritmo_ppm=excluded.ritmo_ppm, "
        "  gancho_falado=excluded.gancho_falado, "
        "  gancho_escrito=excluded.gancho_escrito, "
        "  hashtags_qtd=excluded.hashtags_qtd, "
        "  legenda_caracteres=excluded.legenda_caracteres, "
        "  legenda_linhas=excluded.legenda_linhas, "
        "  legenda_emojis=excluded.legenda_emojis, "
        "  tem_cta=excluded.tem_cta, tipos_cta=excluded.tipos_cta, "
        "  calculado_em=excluded.calculado_em",
        (post_id,
         (analise.get("engajamento") or {}).get("taxa_percentual"),
         analise.get("ritmo_palavras_por_minuto"),
         gancho.get("falado"), gancho.get("escrito"),
         (analise.get("hashtags") or {}).get("quantas"),
         legenda.get("caracteres"), legenda.get("linhas"), legenda.get("emojis"),
         int(bool(chamadas)),
         json.dumps(sorted(chamadas.keys()), ensure_ascii=False),
         _agora()))
    conexao.commit()


def registrar_edicao(conexao, entrada, saida, template, post_id=None):
    """Histórico do que já foi produzido."""
    conexao.execute(
        "INSERT INTO edicoes (post_id, entrada, template, saida, feito_em) "
        "VALUES (?, ?, ?, ?, ?)",
        (post_id, str(entrada), template, str(saida), _agora()))
    conexao.commit()


# ------------------------------------------------------- serie temporal


def _gravar_extras(conexao, tabela, coluna_chave, chave, valores):
    """UPDATE so das colunas que vieram preenchidas.

    Campo ausente nao vira zero nem string vazia: fica NULL. A diferenca
    importa — `compartilhamentos = 0` afirma que ninguem compartilhou;
    `NULL` admite que o Instagram nao conta isso em publico.
    """
    presentes = {c: v for c, v in valores.items() if v is not None}
    if not presentes:
        return

    atribuicoes = ", ".join("%s = ?" % coluna for coluna in presentes)
    conexao.execute(
        "UPDATE %s SET %s WHERE %s = ?" % (tabela, atribuicoes, coluna_chave),
        (*presentes.values(), chave))


def salvar_snapshot_perfil(conexao, perfil, coleta_id=None, medido_em=None):
    """Uma linha por leitura. E o que torna crescimento calculavel.

    `INSERT OR REPLACE` na chave (usuario, medido_em): ler duas vezes no mesmo
    segundo nao cria duas linhas.
    """
    conexao.execute(
        "INSERT OR REPLACE INTO perfis_historico "
        "  (usuario, medido_em, seguidores, seguindo, posts, coleta_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (perfil["usuario"], medido_em or _agora(), perfil.get("seguidores"),
         perfil.get("seguindo"), perfil.get("posts"), coleta_id))
    conexao.commit()


def salvar_snapshot_metricas(conexao, post, horas_desde_post=None,
                             coleta_id=None, medido_em=None):
    """Os numeros do post no momento em que foram lidos.

    Guarda o cru mais a hora. Velocidade (views por hora) e conta de leitura,
    nao coluna — porque o valor depende de quando se mediu, e coluna
    congelaria uma resposta que envelhece.
    """
    conexao.execute(
        "INSERT OR REPLACE INTO metricas_historico "
        "  (post_id, medido_em, horas_desde_post, visualizacoes, curtidas, "
        "   comentarios, compartilhamentos, salvamentos, coleta_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (post["id"], medido_em or _agora(), horas_desde_post,
         post.get("visualizacoes"), post.get("curtidas"),
         post.get("comentarios"), post.get("compartilhamentos"),
         post.get("salvamentos"), coleta_id))
    conexao.commit()


def salvar_extras_do_perfil(conexao, perfil):
    """As colunas que a descoberta traz alem do basico."""
    _gravar_extras(conexao, "perfis", "usuario", perfil["usuario"], {
        "avatar_url": perfil.get("avatar_url"),
        "categoria_negocio": perfil.get("categoria_negocio"),
    })
    conexao.commit()


def salvar_extras_do_post(conexao, post):
    """Audio, local, thumbnail e as metricas que podem nao vir."""
    _gravar_extras(conexao, "posts", "id", post["id"], {
        "thumbnail_url": post.get("thumbnail_url"),
        "video_url": post.get("video_url"),
        "compartilhamentos": post.get("compartilhamentos"),
        "salvamentos": post.get("salvamentos"),
        "audio_id": post.get("audio_id"),
        "audio_titulo": post.get("audio_titulo"),
        "audio_autor": post.get("audio_autor"),
        "audio_original": None if post.get("audio_original") is None
                          else int(bool(post.get("audio_original"))),
        "local_nome": post.get("local_nome"),
        "local_id": post.get("local_id"),
    })
    conexao.commit()


def classificar_perfil(conexao, usuario, categoria=None, relevancia=None,
                       aprovado=None, nicho=None):
    """A etapa de categorizacao do pipeline, gravada com data.

    Existe separada de `salvar_perfil` porque classificacao e julgamento, nao
    coleta: recoletar o perfil nao pode apagar o que voce decidiu sobre ele.
    """
    _gravar_extras(conexao, "perfis", "usuario", usuario, {
        "categoria": categoria,
        "relevancia": relevancia,
        "nicho": nicho,
        "aprovado": None if aprovado is None else int(bool(aprovado)),
        "classificado_em": _agora(),
    })
    conexao.commit()


# ------------------------------------------------------- máquina de estados

# Os seis estados do pipeline. A coluna `status` da tabela `downloads` é a
# fila do sistema — não existe broker, e `queued` é o que está esperando vez.
DESCOBERTO = "discovered"   # sabemos que o post existe; não é vídeo, ou ainda não queremos
NA_FILA    = "queued"       # é vídeo e queremos baixar
BAIXANDO   = "downloading"  # o downloader pegou este
BAIXADO    = "downloaded"   # o arquivo está no storage
PROCESSADO = "processed"    # transcrito e analisado
FALHOU     = "failed"       # deu erro; `tentativas` diz quantas vezes

STATUS_VALIDOS = (DESCOBERTO, NA_FILA, BAIXANDO, BAIXADO, PROCESSADO, FALHOU)

# Estados em que ainda faz sentido atualizar a URL do CDN. Depois de baixado,
# mexer na linha seria reescrever história.
STATUS_ABERTOS = (DESCOBERTO, NA_FILA, FALHOU)


class EstadoInvalido(ValueError):
    """Tentativa de gravar um status que não existe."""


def _validar_status(status):
    if status not in STATUS_VALIDOS:
        raise EstadoInvalido(
            "Status '%s' não existe. Os válidos são: %s"
            % (status, ", ".join(STATUS_VALIDOS)))
    return status


# --------------------------------------------------------------- coletas


def abrir_coleta(conexao, nicho, coletor, run_id=None):
    """Marca o início de uma rodada. Devolve o id para fechar depois."""
    cursor = conexao.execute(
        "INSERT INTO coletas (nicho, coletor, run_id, iniciada_em) "
        "VALUES (?, ?, ?, ?)",
        (nicho, coletor, run_id, _agora()))
    conexao.commit()
    return cursor.lastrowid


def fechar_coleta(conexao, coleta_id, itens=0, perfis=0, videos=0,
                  custo_usd=None, duracao_ms=None, status="ok", erro=None):
    """Fecha a rodada com o que ela custou de verdade.

    `itens` é a unidade de cobrança da Apify: um resultado, um item pago.
    Sem este número as métricas de custo do pipeline viram chute.
    """
    conexao.execute(
        "UPDATE coletas SET itens=?, perfis=?, videos=?, custo_usd=?, "
        "  duracao_ms=?, status=?, erro=?, terminada_em=? WHERE id=?",
        (itens, perfis, videos, custo_usd, duracao_ms, status, erro,
         _agora(), coleta_id))
    conexao.commit()


# -------------------------------------------------------------- downloads


def registrar_para_download(conexao, post_id, usuario, instagram_url,
                            video_url=None, status=NA_FILA, coleta_id=None):
    """Coloca um conteúdo na fila. Devolve True se entrou agora.

    Idempotente de propósito: rodar o pipeline duas vezes não reenfileira o
    que já foi baixado. Se a linha existe e ainda está aberta, só a URL do
    CDN é atualizada — ela vence, e a nova vale mais que a velha.
    """
    _validar_status(status)

    ja_existe = conexao.execute(
        "SELECT 1 FROM downloads WHERE post_id = ?", (post_id,)).fetchone()

    if ja_existe:
        conexao.execute(
            "UPDATE downloads SET video_url = COALESCE(?, video_url), "
            "  atualizado_em = ? "
            "WHERE post_id = ? AND status IN (%s)"
            % ",".join("?" * len(STATUS_ABERTOS)),
            (video_url, _agora(), post_id, *STATUS_ABERTOS))
        conexao.commit()
        return False

    conexao.execute(
        "INSERT INTO downloads (post_id, usuario, instagram_url, video_url, "
        "                       status, coleta_id, criado_em, atualizado_em) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (post_id, usuario, instagram_url, video_url, status, coleta_id,
         _agora(), _agora()))
    conexao.commit()
    return True


def proximos_da_fila(conexao, limite=10, usuario=None):
    """Os próximos a baixar. **Esta consulta é a fila.**

    Ordem: o mais antigo primeiro, para nada ficar para trás para sempre.
    """
    sql = ("SELECT post_id, usuario, instagram_url, video_url, tentativas "
           "FROM downloads WHERE status = ?")
    parametros = [NA_FILA]

    if usuario:
        sql += " AND usuario = ?"
        parametros.append(usuario)

    sql += " ORDER BY criado_em LIMIT ?"
    parametros.append(limite)

    return [dict(linha) for linha in conexao.execute(sql, parametros)]


def marcar_status(conexao, post_id, status, erro=None):
    """Troca o estado de um item. Único caminho para mexer em `status`."""
    _validar_status(status)
    conexao.execute(
        "UPDATE downloads SET status=?, erro=?, atualizado_em=? WHERE post_id=?",
        (status, erro, _agora(), post_id))
    conexao.commit()


def marcar_baixando(conexao, post_id):
    """Reserva o item e conta a tentativa antes de tentar, não depois.

    Contar antes é o que impede um item que trava o processo de ser tentado
    para sempre: se o programa morrer no meio, a tentativa já está registrada.
    """
    conexao.execute(
        "UPDATE downloads SET status=?, tentativas=tentativas+1, "
        "  atualizado_em=? WHERE post_id=?",
        (BAIXANDO, _agora(), post_id))
    conexao.commit()


def marcar_baixado(conexao, post_id, storage_path, bytes_=None, duracao_ms=None):
    """Sucesso: guarda onde o arquivo ficou e quanto tempo levou."""
    agora = _agora()
    conexao.execute(
        "UPDATE downloads SET status=?, storage_path=?, bytes=?, duracao_ms=?, "
        "  erro=NULL, atualizado_em=?, baixado_em=? WHERE post_id=?",
        (BAIXADO, str(storage_path), bytes_, duracao_ms, agora, agora, post_id))
    conexao.execute(
        "UPDATE posts SET caminho_midia=? WHERE id=?", (str(storage_path), post_id))
    conexao.commit()


def marcar_falha(conexao, post_id, erro):
    """Falha registrada com o motivo. A tentativa já foi contada na reserva."""
    marcar_status(conexao, post_id, FALHOU, str(erro)[:2000])


def reenfileirar_falhas(conexao, max_tentativas=3):
    """Devolve à fila o que falhou e ainda tem crédito. Devolve quantos voltaram.

    O teto existe para o pipeline não insistir eternamente num vídeo que foi
    apagado ou ficou privado.
    """
    cursor = conexao.execute(
        "UPDATE downloads SET status=?, atualizado_em=? "
        "WHERE status=? AND tentativas < ?",
        (NA_FILA, _agora(), FALHOU, max_tentativas))
    conexao.commit()
    return cursor.rowcount


def destravar_orfaos(conexao):
    """Devolve à fila o que ficou preso em `downloading`.

    Acontece quando o processo é interrompido no meio — desligar o PC, Ctrl+C.
    Sem isso, o item ficaria reservado para sempre e nunca mais seria baixado.
    """
    cursor = conexao.execute(
        "UPDATE downloads SET status=?, atualizado_em=? WHERE status=?",
        (NA_FILA, _agora(), BAIXANDO))
    conexao.commit()
    return cursor.rowcount


def resumo(conexao):
    """Quantas linhas há em cada tabela. Serve para conferir de relance."""
    tabelas = ["buscas", "perfis", "posts", "hashtags", "transcricoes",
               "segmentos", "palavras", "metricas", "edicoes"]
    return {
        tabela: conexao.execute("SELECT COUNT(*) FROM %s" % tabela).fetchone()[0]
        for tabela in tabelas
    }
