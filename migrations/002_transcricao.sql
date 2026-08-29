-- =============================================================================
-- 002 — Transcrição estruturada
--
-- POR QUE ESTA MIGRATION EXISTE
--
-- A arquitetura de 12 entidades trata transcrição como arquivo: um
-- `media_assets` com `asset_type = 'transcript'`. Isso basta para guardar,
-- mas não para consultar nem para editar:
--
--   * "quais vídeos falam 'bônus' nos primeiros 3 segundos" precisa do texto
--     indexado e do segundo de cada trecho — não de um caminho de arquivo;
--   * a legenda estilo Reels, com a palavra acendendo conforme é falada,
--     precisa do início e do fim de CADA palavra. O `editar.py` e o
--     `legenda.py` já existem e já esperam esse dado.
--
-- O arquivo continua em `media_assets`. Aqui fica a versão consultável.
--
-- FULL-TEXT: o SQLite usava FTS5. O equivalente aqui é `tsvector` com o
-- dicionário `portuguese`, gerado por coluna calculada e coberto por índice
-- GIN. Não é tabela virtual à parte — é coluna da própria tabela, o que
-- evita o problema clássico do FTS5 de sair de sincronia com a origem.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS transcripts (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id     BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    text           TEXT        NOT NULL,
    language       TEXT,
    model          TEXT        NOT NULL,
    audio_seconds  REAL,
    elapsed_ms     BIGINT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Coluna gerada: nunca sai de sincronia com `text`, porque não há um
    -- segundo lugar para atualizar.
    search_pt      TSVECTOR GENERATED ALWAYS AS
                       (to_tsvector('portuguese', coalesce(text, ''))) STORED,

    -- Uma transcrição por conteúdo e modelo. Refazer com o mesmo modelo
    -- substitui; trocar de modelo guarda as duas para poder comparar.
    CONSTRAINT transcripts_unique UNIQUE (content_id, model)
);

CREATE INDEX IF NOT EXISTS transcripts_search_idx
    ON transcripts USING gin (search_pt);
CREATE INDEX IF NOT EXISTS transcripts_content_idx ON transcripts (content_id);


-- Os trechos com o segundo em que começam. É o que responde "o que foi dito
-- nos primeiros 3 segundos", que é a definição de gancho falado no projeto.
CREATE TABLE IF NOT EXISTS transcript_segments (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transcript_id BIGINT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    start_seconds REAL    NOT NULL,
    end_seconds   REAL,
    text          TEXT    NOT NULL,
    CONSTRAINT transcript_segments_unique UNIQUE (transcript_id, idx)
);

CREATE INDEX IF NOT EXISTS transcript_segments_idx
    ON transcript_segments (transcript_id, start_seconds);


-- Uma linha por palavra falada, com início e fim.
--
-- Custa espaço — um Reel de um minuto rende umas 150 linhas —, e é o preço de
-- ter legenda sincronizada palavra a palavra sem depender de nada novo: o
-- Whisper já entrega `word_timestamps` e o formato `.ass` tem karaokê nativo.
CREATE TABLE IF NOT EXISTS transcript_words (
    transcript_id BIGINT  NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    word          TEXT    NOT NULL,
    start_seconds REAL    NOT NULL,
    end_seconds   REAL,
    probability   REAL,
    PRIMARY KEY (transcript_id, idx)
);


INSERT INTO schema_migrations (version) VALUES ('002_transcricao')
ON CONFLICT (version) DO NOTHING;

COMMIT;
